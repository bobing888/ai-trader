"""trades 端点测试"""

from fastapi.testclient import TestClient


def test_trades_returns_mock_data(client: TestClient) -> None:
    """GET /api/trades → mock 数据（因为没有 freqtrade DB）"""
    response = client.get("/api/trades?limit=50")
    assert response.status_code == 200

    data = response.json()
    assert data["source"] == "mock"
    assert data["total_count"] == 50
    assert len(data["trades"]) == 50


def test_trades_filter_by_pair(client: TestClient) -> None:
    """按 pair 过滤"""
    response = client.get("/api/trades?limit=50&pair=BTC/USDT")
    assert response.status_code == 200

    data = response.json()
    assert all(t["pair"] == "BTC/USDT" for t in data["trades"])


def test_trades_filter_by_strategy(client: TestClient) -> None:
    """按 strategy 过滤"""
    response = client.get("/api/trades?limit=50&strategy=DoubleEMACrossover")
    assert response.status_code == 200

    data = response.json()
    assert all(t["strategy"] == "DoubleEMACrossover" for t in data["trades"])


def test_trades_summary(client: TestClient) -> None:
    """GET /api/trades/stats/summary → 统计概览"""
    response = client.get("/api/trades/stats/summary")
    assert response.status_code == 200

    data = response.json()
    assert "total_trades" in data
    assert "winning_trades" in data
    assert "losing_trades" in data
    assert "win_rate" in data
    assert "total_profit_abs" in data
    assert "profit_factor" in data
    assert "source" in data
    assert data["source"] == "mock"


def test_trade_by_id(client: TestClient) -> None:
    """GET /api/trades/{id} → 单笔交易"""
    response = client.get("/api/trades/1")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1


def test_trade_by_id_not_found(client: TestClient) -> None:
    """GET /api/trades/{id} 不存在 → 404"""
    response = client.get("/api/trades/99999")
    assert response.status_code == 404


def test_trade_structure(client: TestClient) -> None:
    """交易结构正确"""
    response = client.get("/api/trades?limit=1")
    trade = response.json()["trades"][0]

    required_fields = [
        "id", "pair", "is_open", "open_date",
        "stake_amount", "exit_reason", "strategy",
    ]
    for field in required_fields:
        assert field in trade
