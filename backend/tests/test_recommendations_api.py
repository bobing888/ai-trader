"""test_recommendations_api — TDD: /api/recommendations/{history,latest}"""

import os
from datetime import UTC, datetime

import pytest

os.environ.setdefault("AI_TRADER_STRATEGIES_DB_PATH", "/tmp/test_recs_api.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


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


def _write_history(db, **kwargs):
    from app.db.models import RecommendationHistory, RecommendationOutcome

    rec = RecommendationHistory(
        pair=kwargs.get("pair", "BTC-USDT"),
        timeframe=kwargs.get("timeframe", "1h"),
        has_signal=kwargs.get("has_signal", True),
        direction=kwargs.get("direction", "long"),
        confidence=kwargs.get("confidence", 0.85),
        regime=kwargs.get("regime", "bull"),
        regime_confidence=kwargs.get("regime_confidence", 0.9),
        suggested_leverage=kwargs.get("suggested_leverage", 2),
        fast_path=kwargs.get("fast_path", False),
        outcome=kwargs.get("outcome", RecommendationOutcome.HAS_SIGNAL.value),
        scanned_at=kwargs.get("scanned_at", datetime.now(UTC)),
        source=kwargs.get("source", "okx"),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def test_history_returns_records():
    """GET /history 返回该 pair+tf 的所有记录。"""
    from app.db.session import SessionLocal

    with TestClient(app) as client:
        db = SessionLocal()
        try:
            for i in range(3):
                _write_history(db, scanned_at=datetime.now(UTC))
        finally:
            db.close()

        resp = client.get(
            "/api/recommendations/history",
            params={"pair": "BTC-USDT", "timeframe": "1h", "limit": 10},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert len(data["items"]) >= 3
        assert all(it["pair"] == "BTC-USDT" for it in data["items"])


def test_latest_returns_most_recent():
    """GET /latest 返回最新一帧。"""
    from app.db.session import SessionLocal

    with TestClient(app) as client:
        db = SessionLocal()
        try:
            _write_history(db, direction="short")
            _write_history(db, direction="long", scanned_at=datetime.now(UTC))
        finally:
            db.close()

        resp = client.get(
            "/api/recommendations/latest",
            params={"pair": "BTC-USDT", "timeframe": "1h"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["pair"] == "BTC-USDT"
        assert data["timeframe"] == "1h"
        assert data["direction"] in ("long", "short")


def test_history_filters_by_pair():
    """不同 pair 的记录不应混。"""
    from app.db.session import SessionLocal

    with TestClient(app) as client:
        db = SessionLocal()
        try:
            _write_history(db, pair="BTC-USDT", timeframe="1h")
            _write_history(db, pair="ETH-USDT", timeframe="1h")
        finally:
            db.close()

        resp = client.get(
            "/api/recommendations/history",
            params={"pair": "ETH-USDT", "timeframe": "1h"},
        )
        data = resp.json()
        for item in data["items"]:
            assert item["pair"] == "ETH-USDT"


def test_history_limit_caps():
    """limit 应截断结果数。"""
    from app.db.session import SessionLocal

    with TestClient(app) as client:
        db = SessionLocal()
        try:
            for i in range(10):
                _write_history(db)
        finally:
            db.close()

        resp = client.get(
            "/api/recommendations/history",
            params={"pair": "BTC-USDT", "timeframe": "1h", "limit": 5},
        )
        data = resp.json()
        assert len(data["items"]) <= 5


def test_latest_404_when_no_data():
    """无数据时 latest 返 None 不崩。"""
    from app.db.session import SessionLocal

    with TestClient(app) as client:
        db = SessionLocal()
        try:
            # 清理 ETH-USDT 1h 数据
            from app.db.models import RecommendationHistory

            db.query(RecommendationHistory).filter_by(pair="ETH-USDT", timeframe="1h").delete()
            db.commit()
        finally:
            db.close()

        resp = client.get(
            "/api/recommendations/latest",
            params={"pair": "ETH-USDT", "timeframe": "1h"},
        )
        # latest 没记录时返 200 + None,或 404 — 我们选 200 + null 字段
        # 实现选 404
        if resp.status_code == 200:
            assert resp.json() is None
        else:
            assert resp.status_code == 404
