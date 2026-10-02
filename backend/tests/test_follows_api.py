"""test_follows_api — TDD: 5 endpoints"""

import os

import pytest

os.environ.setdefault("AI_TRADER_STRATEGIES_DB_PATH", "/tmp/test_follows_api.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _patch_external_io(monkeypatch):
    """旁路 lifespan 真实 IO。"""
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


def test_create_follow():
    with TestClient(app) as client:
        resp = client.post("/api/follows", json={
            "pair": "BTC-USDT", "timeframe": "1h", "direction": "long",
            "entry_price": 50000.0, "stop_loss": 49000.0, "target": 51000.0,
            "leverage": 2,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["pair"] == "BTC-USDT"
        assert data["stake_amount"] == 100.0
        assert data["status"] == "open"
        assert data["id"] is not None


def test_list_follows():
    with TestClient(app) as client:
        resp = client.get("/api/follows")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data


def test_close_follow():
    with TestClient(app) as client:
        create = client.post("/api/follows", json={
            "pair": "ETH-USDT", "timeframe": "1h", "direction": "long",
            "entry_price": 3000.0, "leverage": 1,
        }).json()
        follow_id = create["id"]
        resp = client.post(f"/api/follows/{follow_id}/close", json={"exit_price": 3100.0})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "closed"
        assert data["exit_price"] == 3100.0
        assert data["pnl_pct"] is not None
        assert abs(data["pnl_pct"] - 0.0333) < 0.01


def test_cancel_follow():
    with TestClient(app) as client:
        create = client.post("/api/follows", json={
            "pair": "SOL-USDT", "timeframe": "1h", "direction": "short",
            "entry_price": 100.0, "leverage": 1,
        }).json()
        follow_id = create["id"]
        resp = client.post(f"/api/follows/{follow_id}/cancel", json={"reason": "manual_cancel"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "cancelled"
        assert data["exit_reason"] == "manual_cancel"


def test_close_already_closed_returns_409():
    with TestClient(app) as client:
        create = client.post("/api/follows", json={
            "pair": "XRP-USDT", "timeframe": "1h", "direction": "long",
            "entry_price": 0.5, "leverage": 1,
        }).json()
        follow_id = create["id"]
        client.post(f"/api/follows/{follow_id}/close", json={"exit_price": 0.6})
        resp = client.post(f"/api/follows/{follow_id}/close", json={"exit_price": 0.7})
        assert resp.status_code == 409


def test_get_single_follow():
    with TestClient(app) as client:
        create = client.post("/api/follows", json={
            "pair": "BNB-USDT", "timeframe": "1h", "direction": "long",
            "entry_price": 600.0, "leverage": 1,
        }).json()
        resp = client.get(f"/api/follows/{create['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == create["id"]
        assert data["pair"] == "BNB-USDT"


def test_get_follow_404():
    with TestClient(app) as client:
        resp = client.get("/api/follows/99999")
        assert resp.status_code == 404
