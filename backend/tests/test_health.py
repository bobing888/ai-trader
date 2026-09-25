"""Health 端点测试"""

from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    """GET /api/health → 200 + status ok"""
    response = client.get("/api/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"
    assert "app_name" in data
    assert "version" in data
    assert "freqtrade_db_configured" in data


def test_ping_returns_pong(client: TestClient) -> None:
    """GET /api/ping → 200 + pong"""
    response = client.get("/api/ping")
    assert response.status_code == 200
    assert response.json() == {"pong": "true"}


def test_openapi_docs_available(client: TestClient) -> None:
    """GET /docs → 200 (Swagger UI)"""
    response = client.get("/docs")
    assert response.status_code == 200


def test_openapi_json_available(client: TestClient) -> None:
    """GET /openapi.json → 200 + 包含 health 端点"""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    assert "/api/health" in spec["paths"]
    assert "/api/ping" in spec["paths"]
    assert "/api/klines/{symbol}" in spec["paths"]
    assert "/api/trades" in spec["paths"]
