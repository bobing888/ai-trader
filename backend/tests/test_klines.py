"""K 线端点测试"""

from fastapi.testclient import TestClient


def test_klines_default_returns_500_candles(client: TestClient) -> None:
    """GET /api/klines/BTCUSDT → 200 + 500 根 K 线"""
    response = client.get("/api/klines/BTCUSDT")
    assert response.status_code == 200

    data = response.json()
    assert data["symbol"] == "BTCUSDT"
    assert data["timeframe"] == "1h"
    assert data["count"] == 500
    assert len(data["candles"]) == 500


def test_klines_lowercase_normalized(client: TestClient) -> None:
    """symbol 自动转大写"""
    response = client.get("/api/klines/btcusdt")
    assert response.status_code == 200
    assert response.json()["symbol"] == "BTCUSDT"


def test_klines_custom_timeframe(client: TestClient) -> None:
    """不同 timeframe 都可用"""
    for tf in ["1m", "5m", "15m", "1h", "4h", "1d"]:
        response = client.get(f"/api/klines/ETHUSDT?timeframe={tf}&limit=100")
        assert response.status_code == 200
        data = response.json()
        assert data["timeframe"] == tf
        assert data["count"] == 100


def test_klines_limit_validation(client: TestClient) -> None:
    """limit 必须 1-5000"""
    response = client.get("/api/klines/BTCUSDT?limit=0")
    assert response.status_code == 422

    response = client.get("/api/klines/BTCUSDT?limit=10000")
    assert response.status_code == 422


def test_klines_invalid_timeframe(client: TestClient) -> None:
    """非法 timeframe 返回 422"""
    response = client.get("/api/klines/BTCUSDT?timeframe=invalid")
    assert response.status_code == 422


def test_klines_candle_structure(client: TestClient) -> None:
    """K 线结构正确（time/open/high/low/close/volume）"""
    response = client.get("/api/klines/BTCUSDT?limit=10")
    data = response.json()

    candle = data["candles"][0]
    assert "time" in candle
    assert "open" in candle
    assert "high" in candle
    assert "low" in candle
    assert "close" in candle
    assert "volume" in candle

    assert candle["high"] >= candle["low"]
    assert candle["high"] >= max(candle["open"], candle["close"])
    assert candle["low"] <= min(candle["open"], candle["close"])


def test_klines_time_ascending(client: TestClient) -> None:
    """K 线时间升序"""
    response = client.get("/api/klines/BTCUSDT?limit=10")
    candles = response.json()["candles"]
    times = [c["time"] for c in candles]
    assert times == sorted(times)
