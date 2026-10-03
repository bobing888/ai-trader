"""Tests for backend.app.api.agent — Agent API 端点（Task 8）.

覆盖：
  - GET  /api/agent/reports?pair=&timeframe=&limit=
  - GET  /api/agent/recommendations?pair=&timeframe=&limit=
  - POST /api/agent/analyze
  - POST /api/agent/analyze/once
  - pair 必须 BTC/ETH
  - 400 / 503 错误处理

测试策略：用 httpx.AsyncClient + ASGITransport（不跑 lifespan）
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client():
    """httpx AsyncClient + override get_db（不启动 lifespan）"""
    from app.main import app
    from app.db.session import get_db

    async def override_get_db():
        mock_session = MagicMock()
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db

    # ASGITransport 不跑 lifespan（lifespan 会启动 WS / background tasks，测试不想要）
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


# === GET /api/agent/reports ===

@pytest.mark.asyncio
class TestGetReports:
    async def test_get_reports_returns_list(self, client: AsyncClient):
        """GET /api/agent/reports 返回最近 N 条研判报告"""
        with patch("app.agent.persistence.AnalysisRepository.list_recent") as mock_list:
            mock_list.return_value = []
            response = await client.get("/api/agent/reports?pair=BTC-USDT&timeframe=1h&limit=10")
            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert data["items"] == []
            assert data["total"] == 0

    async def test_get_reports_requires_pair(self, client: AsyncClient):
        """pair 缺失 → 422"""
        response = await client.get("/api/agent/reports")
        assert response.status_code == 422

    async def test_get_reports_rejects_non_btc_eth(self, client: AsyncClient):
        """非 BTC/ETH pair → 400"""
        response = await client.get("/api/agent/reports?pair=SOL-USDT")
        assert response.status_code == 400

    async def test_get_reports_rejects_bad_timeframe(self, client: AsyncClient):
        """非法 timeframe → 400"""
        response = await client.get("/api/agent/reports?pair=BTC-USDT&timeframe=4h")
        assert response.status_code == 400

    async def test_get_reports_works_with_eth(self, client: AsyncClient):
        """ETH 应该接受"""
        with patch("app.agent.persistence.AnalysisRepository.list_recent") as mock_list:
            mock_list.return_value = []
            response = await client.get("/api/agent/reports?pair=ETH-USDT")
            assert response.status_code == 200


# === GET /api/agent/recommendations ===

@pytest.mark.asyncio
class TestGetRecommendations:
    async def test_get_recommendations_returns_list(self, client: AsyncClient):
        with patch("app.agent.persistence.RecommendationRepository.list_recent") as mock_list:
            mock_list.return_value = []
            response = await client.get("/api/agent/recommendations?pair=ETH-USDT&timeframe=15m")
            assert response.status_code == 200
            data = response.json()
            assert "items" in data

    async def test_get_recommendations_rejects_non_btc_eth(self, client: AsyncClient):
        response = await client.get("/api/agent/recommendations?pair=LINK-USDT")
        assert response.status_code == 400


# === POST /api/agent/analyze ===

@pytest.mark.asyncio
class TestPostAnalyze:
    async def test_post_analyze_returns_503_when_not_configured(self, client: AsyncClient):
        """Agent 未配置 → 503 (有清晰错误信息)"""
        response = await client.post("/api/agent/analyze")
        assert response.status_code == 503

    async def test_post_analyze_rejects_non_btc_eth(self, client: AsyncClient):
        response = await client.post("/api/agent/analyze?pair=DOGE-USDT")
        assert response.status_code == 400

    async def test_post_analyze_rejects_bad_timeframe(self, client: AsyncClient):
        response = await client.post("/api/agent/analyze?pair=BTC-USDT&timeframe=4h")
        assert response.status_code == 400


# === POST /api/agent/analyze/once ===

@pytest.mark.asyncio
class TestPostAnalyzeOnce:
    async def test_post_analyze_once_returns_503_when_not_configured(self, client: AsyncClient):
        response = await client.post("/api/agent/analyze/once?pair=BTC-USDT&timeframe=1h")
        assert response.status_code == 503

    async def test_post_analyze_once_requires_pair(self, client: AsyncClient):
        response = await client.post("/api/agent/analyze/once?timeframe=1h")
        assert response.status_code == 422

    async def test_post_analyze_once_requires_timeframe(self, client: AsyncClient):
        response = await client.post("/api/agent/analyze/once?pair=BTC-USDT")
        assert response.status_code == 422

    async def test_post_analyze_once_rejects_non_btc_eth(self, client: AsyncClient):
        response = await client.post("/api/agent/analyze/once?pair=SOL-USDT&timeframe=1h")
        assert response.status_code == 400