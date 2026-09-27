"""Tests for strategies CRUD + GitHub sync endpoints"""

import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal, init_db
from app.db.models import Strategy
from app.main import app
from app.signals.strategy_pool import StrategyId, STRATEGY_INSTANCES, ConfluenceStrategy


@pytest.fixture(scope="module", autouse=True)
def _setup_db():
    init_db()
    yield


@pytest.fixture()
def client():
    return TestClient(app)


def test_list_strategies_empty(client):
    r = client.get("/api/strategies")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_create_strategy(client):
    payload = {
        "name": "TestMomentum",
        "description": "EMA cross strategy",
        "strategy_type": "custom",
        "parameters": {"fast": 9, "slow": 21},
        "code": "def evaluate(candles, volumes, regime): pass",
    }
    r = client.post("/api/strategies", json=payload)
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "TestMomentum"
    assert data["source"] == "manual"
    assert "id" in data
    return data["id"]


def test_get_update_delete(client):
    payload = {"name": "TmpX", "description": "tmp"}
    r = client.post("/api/strategies", json=payload)
    sid = r.json()["id"]

    r2 = client.get(f"/api/strategies/{sid}")
    assert r2.status_code == 200
    assert r2.json()["name"] == "TmpX"

    r3 = client.put(f"/api/strategies/{sid}", json={"name": "TmpX-Edited", "weight": 0.5})
    assert r3.status_code == 200
    assert r3.json()["name"] == "TmpX-Edited"
    assert r3.json()["weight"] == 0.5

    r4 = client.delete(f"/api/strategies/{sid}")
    assert r4.status_code == 204


def test_clone(client):
    payload = {"name": "OrigS", "description": "src"}
    r = client.post("/api/strategies", json=payload)
    sid = r.json()["id"]

    r2 = client.post(f"/api/strategies/{sid}/clone")
    assert r2.status_code == 201
    assert r2.json()["name"] == "OrigS (copy)"
    assert r2.json()["source"] == "manual"


def test_export_import_roundtrip(client):
    payload = {"name": "ExportSrc", "parameters": {"k": 14}, "code": "x = 1"}
    r = client.post("/api/strategies", json=payload)
    sid = r.json()["id"]

    r2 = client.get(f"/api/strategies/{sid}/export")
    assert r2.status_code == 200
    assert "attachment" in r2.headers.get("content-disposition", "")
    body = json.loads(r2.content)
    assert body["name"] == "ExportSrc"
    assert body["schema_version"] == "1.0"

    r3 = client.post("/api/strategies/import", json=body)
    assert r3.status_code == 201
    assert r3.json()["name"] == "ExportSrc"
    assert r3.json()["source"] == "import"


def test_sync_github_status(client):
    r = client.get("/api/strategies/sync-github/status")
    assert r.status_code == 200
    data = r.json()
    assert "enabled" in data
    assert "interval_hours" in data
    assert "github_strategies_count" in data


def test_get_404(client):
    r = client.get("/api/strategies/99999")
    assert r.status_code == 404


# ── ConfluenceStrategy tests ────────────────────────────────────────────────────


def test_confluence_strategy_in_pool():
    """验证 StrategyId.CONFLUENCE 已加入 STRATEGY_INSTANCES。"""
    assert StrategyId.CONFLUENCE in STRATEGY_INSTANCES
    instance = STRATEGY_INSTANCES[StrategyId.CONFLUENCE]
    assert isinstance(instance, ConfluenceStrategy)


def test_confluence_strategy_confidence_bounds():
    """不同 confluence_score 输入下 confidence 边界正确。"""
    # 构建一个 mock candles dict，构造已知 confluent score 场景
    # 通过直接 patch multi_indicator_confluence 来控制 score
    from app.analytics.trend import multi_indicator_confluence
    import app.analytics.trend as trend_module
    import unittest.mock

    rng = np.random.default_rng(42)
    close = np.cumsum(rng.normal(0, 1, 200)) + 100
    high = close + rng.uniform(0.1, 1.0, 200)
    low = close - rng.uniform(0.1, 1.0, 200)
    volume = rng.uniform(100, 500, 200)
    candles = {"symbol": "BTCUSDT", "timeframe": "1h", "close": close, "high": high, "low": low}
    volumes = volume.astype(np.float64)

    # score >= 75 → confidence 0.85
    with unittest.mock.patch.object(trend_module, "multi_indicator_confluence", return_value={"confluence_score": 80, "macd": {"status": "above_zero"}, "price_vs_ma30": "above", "adx14": {"adx": 30, "pdi": 30, "ndi": 10}}):
        strat = ConfluenceStrategy()
        result = strat.evaluate(candles, volumes, "bull")
        assert result.direction in ("long", "short")
        assert result.confidence == 0.85

    # 60 <= score < 75 → confidence 0.70
    with unittest.mock.patch.object(trend_module, "multi_indicator_confluence", return_value={"confluence_score": 65, "macd": {"status": "above_zero"}, "price_vs_ma30": "above", "adx14": {"adx": 20, "pdi": 15, "ndi": 15}}):
        strat = ConfluenceStrategy()
        result = strat.evaluate(candles, volumes, "bull")
        assert result.confidence == 0.70

    # 45 <= score < 60 → confidence 0.55
    with unittest.mock.patch.object(trend_module, "multi_indicator_confluence", return_value={"confluence_score": 50, "macd": {"status": "above_zero"}, "price_vs_ma30": "above", "adx14": {"adx": 15, "pdi": 10, "ndi": 10}}):
        strat = ConfluenceStrategy()
        result = strat.evaluate(candles, volumes, "bull")
        assert result.confidence == 0.55


def test_confluence_no_signal_when_score_low():
    """score < 45 时 direction is None。"""
    from app.analytics import trend as trend_module
    import unittest.mock

    rng = np.random.default_rng(42)
    close = np.cumsum(rng.normal(0, 1, 200)) + 100
    high = close + rng.uniform(0.1, 1.0, 200)
    low = close - rng.uniform(0.1, 1.0, 200)
    volume = rng.uniform(100, 500, 200)
    candles = {"symbol": "BTCUSDT", "timeframe": "1h", "close": close, "high": high, "low": low}
    volumes = volume.astype(np.float64)

    with unittest.mock.patch.object(trend_module, "multi_indicator_confluence", return_value={"confluence_score": 30, "macd": {"status": "below_zero"}, "price_vs_ma30": "below", "adx14": {"adx": 10, "pdi": 5, "ndi": 5}}):
        strat = ConfluenceStrategy()
        result = strat.evaluate(candles, volumes, "choppy")
        assert result.direction is None
        assert result.confidence == 0.0
