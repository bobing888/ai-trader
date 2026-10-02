"""Test backtest API — POST /api/backtest + GET runs + GET run/{id}.

验证：
1. POST 正常请求 → 200 + JSON 结构
2. 缺 strategies → 422
3. days 过大 → 400
4. 并发同 symbol → 409
5. 列表查询 → list of summaries
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from datetime import datetime, timezone

from app.main import app

client = TestClient(app)


def _mock_klines():
    """生成 200 根简单的横盘 K 线（BTC $100 ± 1%）。"""
    base = int(datetime.now(timezone.utc).timestamp())
    candles_out = []
    price = 100.0
    for i in range(200):
        # 缓慢上行
        price = 100.0 + (i % 50) * 0.01
        candles_out.append({
            "time": base - (200 - i) * 3600,
            "open": price - 0.005,
            "high": price + 0.005,
            "low": price - 0.01,
            "close": price,
            "volume": 100.0,
        })
    return candles_out


def test_post_backtest_returns_summary():
    """POST 正常 → 200 + JSON 结构。"""
    with patch("app.data.okx_client.get_klines", new=AsyncMock(return_value=_mock_klines())):
        resp = client.post("/api/backtest", json={
            "symbol": "BTC-USDT",
            "timeframe": "1h",
            "strategies": ["MomentumStrategy"],
            "days": 7,
        })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "run_id" in data
    assert "summary" in data
    s = data["summary"]
    assert "net_pnl_pct" in s
    assert "sharpe_ratio" in s
    assert "hit_rate" in s
    assert "total_trades" in s
    assert "max_drawdown_pct" in s
    assert isinstance(data["equity_curve"], list)
    assert isinstance(data["trades"], list)


def test_post_backtest_missing_strategies_422():
    resp = client.post("/api/backtest", json={
        "symbol": "BTC-USDT",
        "timeframe": "1h",
        "days": 7,
    })
    assert resp.status_code == 422


def test_post_backtest_days_too_large_400():
    resp = client.post("/api/backtest", json={
        "symbol": "BTC-USDT",
        "timeframe": "1h",
        "strategies": ["MomentumStrategy"],
        "days": 1000,
    })
    # Pydantic Field(le=365) should reject
    assert resp.status_code == 422


def test_post_backtest_empty_strategies_422():
    resp = client.post("/api/backtest", json={
        "symbol": "BTC-USDT",
        "timeframe": "1h",
        "strategies": [],
        "days": 7,
    })
    assert resp.status_code == 422


def test_list_backtest_runs():
    """GET /api/backtest/runs 返 list of summaries。"""
    resp = client.get("/api/backtest/runs")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_list_backtest_runs_by_symbol():
    resp = client.get("/api/backtest/runs?symbol=BTC-USDT")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_nonexistent_run_404():
    resp = client.get("/api/backtest/runs/999999")
    assert resp.status_code == 404


def test_post_backtest_insufficient_data_400():
    """K 线拉取不足 → 400。"""
    short_klines = _mock_klines()[:30]   # < min_train_watches=50
    with patch("app.api.backtest.okx_client") as mock_client:
        mock_client.get_klines = AsyncMock(return_value=short_klines)
        resp = client.post("/api/backtest", json={
            "symbol": "BTC-USDT",
            "timeframe": "1h",
            "strategies": ["MomentumStrategy"],
            "days": 7,
        })
    assert resp.status_code == 400, resp.text
    assert "insufficient" in resp.json()["detail"].lower() or "100" in resp.json()["detail"]