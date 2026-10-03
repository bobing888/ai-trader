"""test_recommendations_horizon — TDD: /api/recommendations/latest filter by horizon + new fields"""

import os
from datetime import UTC, datetime

import pytest

os.environ.setdefault("AI_TRADER_STRATEGIES_DB_PATH", "/tmp/test_horizon.db")

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


def test_recommendation_latest_filters_by_horizon(client):
    """GET /latest?horizon=P0_long returns record with new fields."""
    from app.db.session import SessionLocal

    with TestClient(app) as c:
        db = SessionLocal()
        try:
            # 清理旧数据
            from app.db.models import RecommendationHistory

            db.query(RecommendationHistory).filter_by(
                pair="BTC-USDT", timeframe="1h"
            ).delete()
            db.commit()

            _write_history(
                db,
                pair="BTC-USDT",
                timeframe="1h",
                direction="long",
                confidence=0.88,
                scanned_at=datetime.now(UTC),
            )
        finally:
            db.close()

        r = c.get("/api/recommendations/latest?pair=BTC-USDT&timeframe=1h&horizon=P0_long")
        assert r.status_code == 200
        data = r.json()
        assert data["pair"] == "BTC-USDT"
        assert data["timeframe"] == "1h"
        assert "horizon_tier" in data
        assert "leverage" in data
        assert "expires_at" in data


def test_recommendation_latest_without_horizon_returns_default(client):
    """GET /latest without ?horizon= defaults to P1_short for backward compat."""
    from app.db.session import SessionLocal

    with TestClient(app) as c:
        db = SessionLocal()
        try:
            from app.db.models import RecommendationHistory

            db.query(RecommendationHistory).filter_by(
                pair="ETH-USDT", timeframe="1h"
            ).delete()
            db.commit()

            _write_history(
                db,
                pair="ETH-USDT",
                timeframe="1h",
                direction="short",
                confidence=0.75,
                scanned_at=datetime.now(UTC),
            )
        finally:
            db.close()

        r = c.get("/api/recommendations/latest?pair=ETH-USDT&timeframe=1h")
        assert r.status_code == 200
        data = r.json()
        assert data["pair"] == "ETH-USDT"
        # 默认 horizon_tier = P1_short（向后兼容现有前端）
        assert data["horizon_tier"] == "P1_short"


def test_recommendation_latest_horizon_tier_values(client):
    """horizon_tier must be one of the defined tiers."""
    from app.db.session import SessionLocal

    valid_tiers = {
        "P0_long",
        "P0_cross_month",
        "P1_mid",
        "P1_short",
        "P2_ultra",
        "P3_uhf",
    }

    with TestClient(app) as c:
        db = SessionLocal()
        try:
            from app.db.models import RecommendationHistory

            db.query(RecommendationHistory).filter_by(
                pair="SOL-USDT", timeframe="1h"
            ).delete()
            db.commit()

            _write_history(
                db,
                pair="SOL-USDT",
                timeframe="1h",
                scanned_at=datetime.now(UTC),
            )
        finally:
            db.close()

        r = c.get("/api/recommendations/latest?pair=SOL-USDT&timeframe=1h&horizon=P1_mid")
        assert r.status_code == 200
        data = r.json()
        assert data["horizon_tier"] in valid_tiers
