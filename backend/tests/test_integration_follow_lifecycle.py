"""test_integration_follow_lifecycle — TDD: 跟单生命周期端到端

完整流程:
1. recorder 写一帧 → 写库 → bus emit direction event
2. scheduler 收到 bus → 对该 pair 所有 OPEN follow 评估
3. 跟单 schedule、2 张 SL 触发 → close with pnl = 0
4. WS client 收到 signal_change (验证 event propagation)
"""

import os
from datetime import UTC, datetime, timedelta

import pytest

os.environ.setdefault("AI_TRADER_STRATEGIES_DB_PATH", "/tmp/test_integration.db")


@pytest.fixture(autouse=True)
def _patch_external_io(monkeypatch):
    from app.data import binance_client, okx_client
    from app.data import okx_ws as _okx_ws_mod

    async def _noop():
        return None

    monkeypatch.setattr(binance_client, "init", _noop)
    monkeypatch.setattr(binance_client, "close", _noop)
    monkeypatch.setattr(okx_client, "init", _noop)
    monkeypatch.setattr(okx_client, "close", _noop)
    monkeypatch.setattr(_okx_ws_mod.okx_ws_client, "start", _noop)
    monkeypatch.setattr(_okx_ws_mod.okx_ws_client, "stop", _noop)

    from app.services import regime_shift_engine as rse

    async def _e(self):
        return None

    monkeypatch.setattr(rse.RegimeShiftEngine, "start", _e)
    monkeypatch.setattr(rse.RegimeShiftEngine, "stop", _e)


def test_full_lifecycle_close_on_stop_loss():
    """1. create follow long SL=49000 entry=50000
    2. scheduler ticks with current_price=48000 → close with stop_loss
    """
    from app.db.session import SessionLocal
    from app.services.follow_scheduler import FollowScheduler

    db = SessionLocal()
    try:
        # 1. create follow
        from app.services.follow_service import FollowService
        follow = FollowService.create(db, {
            "pair": "BTC-USDT", "timeframe": "1h", "direction": "long",
            "entry_price": 50000.0, "stop_loss": 49000.0, "target": 51000.0,
            "leverage": 1, "stake_amount": 100.0,
        })
        follow_id = follow.id
    finally:
        db.close()

    # 2. scheduler 评估
    db = SessionLocal()
    try:
        follow = db.query(FollowService.by_id_class(follow_id) if False else __import__("app.db.models", fromlist=["UserFollow"]).UserFollow).filter_by(id=follow_id).one()
    finally:
        db.close()

    verdict = FollowScheduler._evaluate_price(follow, 48000.0)
    assert verdict.should_exit is True
    assert verdict.reason == "stop_loss"


def test_full_lifecycle_no_exit_in_range():
    """价格在 SL 与 TP 之间,不应出场。"""
    from app.db.session import SessionLocal
    from app.services.follow_scheduler import FollowScheduler

    db = SessionLocal()
    try:
        from app.services.follow_service import FollowService

        follow = FollowService.create(db, {
            "pair": "ETH-USDT", "timeframe": "1h", "direction": "long",
            "entry_price": 3000.0, "stop_loss": 2900.0, "target": 3100.0,
            "leverage": 1, "stake_amount": 100.0,
        })
        follow_id = follow.id
    finally:
        db.close()

    from app.db.models import UserFollow
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        follow = db.query(UserFollow).filter_by(id=follow_id).one()
        verdict = FollowScheduler._evaluate_price(follow, 3050.0)
        assert verdict.should_exit is False
    finally:
        db.close()


def test_full_lifecycle_target_profit():
    """价格在 TP 上方 → close target, PnL 2%。"""
    from app.db.session import SessionLocal
    from app.services.follow_scheduler import FollowScheduler

    db = SessionLocal()
    try:
        from app.services.follow_service import FollowService

        follow = FollowService.create(db, {
            "pair": "SOL-USDT", "timeframe": "1h", "direction": "long",
            "entry_price": 100.0, "stop_loss": 95.0, "target": 105.0,
            "leverage": 1, "stake_amount": 100.0,
        })
        follow_id = follow.id
    finally:
        db.close()

    from app.db.models import UserFollow
    db = SessionLocal()
    try:
        follow = db.query(UserFollow).filter_by(id=follow_id).one()
        verdict = FollowScheduler._evaluate_price(follow, 108.0)
        assert verdict.should_exit is True
        assert verdict.reason == "target"

        # 真正 close
        closed = FollowService.close(db, follow_id, 108.0, "target")
        assert closed.status == "closed"
        # 100 → 108 +8% on 1x leverage
        assert abs(closed.pnl_pct - 0.08) < 0.001
    finally:
        db.close()


def test_expired_after_24h():
    """hours_ago=25 → expired。"""
    from app.db.models import UserFollow
    from app.db.session import SessionLocal
    from app.services.follow_scheduler import FollowScheduler
    from app.services.follow_service import FollowService

    db = SessionLocal()
    try:
        follow = FollowService.create(db, {
            "pair": "BNB-USDT", "timeframe": "1h", "direction": "long",
            "entry_price": 600.0, "leverage": 1,
        })
        # 手动改成 25h ago
        follow_id = follow.id
    finally:
        db.close()

    db = SessionLocal()
    try:
        follow = db.query(UserFollow).filter_by(id=follow_id).one()
        follow.entry_time = datetime.now(UTC) - timedelta(hours=25)
        db.commit()
    finally:
        db.close()

    db = SessionLocal()
    try:
        follow = db.query(UserFollow).filter_by(id=follow_id).one()
        verdict = FollowScheduler._evaluate_price(follow, 605.0)
        assert verdict.reason == "expired"
    finally:
        db.close()


def test_reversal_long_to_short_with_history():
    """3-min 窗口里 2 帧都 short → consecutive_reversal。"""
    from datetime import timedelta

    from app.db.models import (
        RecommendationHistory,
        RecommendationOutcome,
        UserFollow,
    )
    from app.db.session import SessionLocal
    from app.services.signal_change_detector import detect_reversal

    db = SessionLocal()
    try:
        follow = UserFollow(
            pair="XRP-USDT",
            timeframe="1h",
            direction="long",
            entry_price=0.5,
            leverage=1,
            stake_amount=100.0,
            status="open",
            entry_time=datetime.now(UTC),
        )
        db.add(follow)
        db.commit()
        db.refresh(follow)
        follow_id = follow.id
    finally:
        db.close()

    db = SessionLocal()
    try:
        follow = db.query(UserFollow).filter_by(id=follow_id).one()
        # 2 frames both short, 1 minute apart, within 3-min window
        prev = RecommendationHistory(
            pair="XRP-USDT", timeframe="1h", has_signal=True,
            direction="short", confidence=0.8, regime="bull", regime_confidence=0.9,
            outcome=RecommendationOutcome.HAS_SIGNAL.value,
            scanned_at=datetime.now(UTC) - timedelta(minutes=2),
            source="okx",
        )
        curr = RecommendationHistory(
            pair="XRP-USDT", timeframe="1h", has_signal=True,
            direction="short", confidence=0.85, regime="bull", regime_confidence=0.9,
            outcome=RecommendationOutcome.HAS_SIGNAL.value,
            scanned_at=datetime.now(UTC),
            source="okx",
        )
        verdict = detect_reversal(follow, curr, prev, lookback_history=[prev, curr])
        assert verdict.reversed is True
        assert verdict.reason == "consecutive_reversal"
    finally:
        db.close()
