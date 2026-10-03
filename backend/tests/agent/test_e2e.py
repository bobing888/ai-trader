"""End-to-end integration test for Trend Analysis Agent (Task 11)

跑完整 cycle：mock LLM → TrendAgent.analyze → DB 写入 → API 响应
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def in_memory_db_session():
    """in-memory SQLite + Agent ORM"""
    from app.agent.persistence import init_agent_tables
    engine = create_engine("sqlite:///:memory:")
    Base = init_agent_tables()
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def mock_llm_provider():
    """Mock LLM Provider 返回合规 JSON"""
    provider = AsyncMock()

    async def complete(system, user, **kw):
        return json.dumps({
            "regime": "bull",
            "regime_confidence": 0.7,
            "reasoning": "BTC 1h 处于多头格局，ADX 28 表明趋势明确，Hurst 0.62 表明持续性较强。MACD 金叉形成，成交量温和放大。建议关注回调做多机会。",
            "key_observations": ["ADX 28 趋势强度增加", "Hurst 0.62 持续性较强"],
            "risks": ["阻力位 51500"]
        }, ensure_ascii=False)

    provider.complete = AsyncMock(side_effect=complete)
    return provider


class TestAgentE2E:
    @pytest.mark.asyncio
    async def test_full_cycle_writes_to_db(
        self, in_memory_db_session, mock_llm_provider
    ):
        """完整 cycle: Perceive → Reason → Persist，DB 应有 1 条 AiTrendAnalysis"""

        from app.agent.agent import TrendAgent
        from app.agent.reasoner import Reasoner
        from app.agent.persistence import AnalysisRepository
        from app.agent.schemas import AnalysisStatus

        reasoner = Reasoner(provider=mock_llm_provider)
        agent = TrendAgent(reasoner=reasoner, session=in_memory_db_session)

        # mock Perceiver — 跳过真实 OKX HTTP
        from app.agent.perceiver import PerceivedContext
        from app.signals.regime import Regime, RegimeInfo
        from app.signals.cost_model import CostEstimate

        fake_ctx = PerceivedContext(
            pair="BTC-USDT",
            timeframe="1h",
            ohlcv=[{"c": 50000.0, "h": 50100.0, "l": 49900.0, "o": 50000.0, "vol": 100.0, "timestamp": 1234567890000} for _ in range(100)],
            regime=RegimeInfo(
                regime=Regime.BULL,
                confidence=0.7,
                regime_probs={r: 0.25 for r in Regime},
                description="强趋势",
                adx=28.0,
                hurst=0.62,
            ),
            strategy_signals=[],
            cost_estimate=CostEstimate(
                entry_fee_pct=0.001,
                exit_fee_pct=0.001,
                slippage_pct=0.001,
                total_round_trip_pct=0.003,
            ),
            data_completeness=1.0,
        )

        with patch.object(agent._perceiver if hasattr(agent, "_perceiver") else MagicMock(),
                         "perceive", new_callable=AsyncMock) if False else \
             patch("app.agent.perceiver.Perceiver.perceive", new_callable=AsyncMock) as mock_perceive:
            # 实际：TrendAgent 默认 _perceiver=None, 会 lazy init → 真 Perceiver
            # patch Perceiver class 让它返回 mock
            with patch("app.agent.agent.Perceiver") as MockPerceiver:
                mock_perceiver_instance = MagicMock()
                mock_perceiver_instance.perceive = AsyncMock(return_value=fake_ctx)
                MockPerceiver.return_value = mock_perceiver_instance

                # 重置 agent 让它 lazy init 新的 mock perceiver
                agent._perceiver = None

                report = await agent.analyze("BTC-USDT", "1h")

        assert report.analysis_status == AnalysisStatus.SUCCESS
        assert report.pair == "BTC-USDT"

        # Persist 验证：DB 应有 1 条
        in_memory_db_session.commit()
        rows = AnalysisRepository.list_recent(in_memory_db_session, "BTC-USDT", "1h", limit=10)
        assert len(rows) == 1
        assert rows[0].regime == "bull"
        assert rows[0].analysis_status == "success"

    @pytest.mark.asyncio
    async def test_fallback_writes_to_db_with_fallback_status(
        self, in_memory_db_session
    ):
        """LLM 失败 → FALLBACK 报告 + 仍 persist"""
        from app.agent.agent import TrendAgent
        from app.agent.reasoner import Reasoner
        from app.agent.schemas import AnalysisStatus

        failing_provider = AsyncMock()
        failing_provider.complete = AsyncMock(side_effect=Exception("API timeout"))
        reasoner = Reasoner(provider=failing_provider)
        agent = TrendAgent(
            reasoner=reasoner, session=in_memory_db_session,
            max_retries=1, initial_backoff=0.01,  # 加速测试
        )

        # patch Perceiver
        from app.agent.perceiver import PerceivedContext
        from app.signals.regime import Regime, RegimeInfo
        from app.signals.cost_model import CostEstimate

        fake_ctx = PerceivedContext(
            pair="ETH-USDT",
            timeframe="15m",
            ohlcv=[{"c": 3000.0, "h": 3010.0, "l": 2990.0, "o": 3000.0, "vol": 50.0, "timestamp": 1234567890000} for _ in range(100)],
            regime=RegimeInfo(
                regime=Regime.CHOPPY,
                confidence=0.4,
                regime_probs={r: 0.25 for r in Regime},
                description="震荡",
                adx=15.0,
                hurst=0.5,
            ),
            strategy_signals=[],
            cost_estimate=CostEstimate(
                entry_fee_pct=0.001,
                exit_fee_pct=0.001,
                slippage_pct=0.001,
                total_round_trip_pct=0.003,
            ),
            data_completeness=1.0,
        )

        with patch("app.agent.agent.Perceiver") as MockPerceiver:
            mock_perceiver_instance = MagicMock()
            mock_perceiver_instance.perceive = AsyncMock(return_value=fake_ctx)
            MockPerceiver.return_value = mock_perceiver_instance
            agent._perceiver = None

            report = await agent.analyze("ETH-USDT", "15m")

        assert report.analysis_status == AnalysisStatus.FALLBACK
        assert "降级" in report.reasoning or "不可用" in report.reasoning

        in_memory_db_session.commit()
        from app.agent.persistence import AnalysisRepository
        rows = AnalysisRepository.list_recent(in_memory_db_session, "ETH-USDT", "15m", limit=10)
        assert len(rows) == 1
        assert rows[0].analysis_status == "fallback"