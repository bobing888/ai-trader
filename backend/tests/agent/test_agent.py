"""Tests for backend.app.agent.agent — TrendAgent 主类（Task 6）.

覆盖（spec §3 + plan Task 6）：
  - analyze(pair, timeframe) orchestrate perceive → reason → persist
  - LLM 失败重试 2 次（指数退避 1s/3s）
  - 30s 超时
  - Perceive 失败 → raise (不重试)
  - Reason 失败 → 重试 2 次 → 仍失败返回 FALLBACK report + persist
  - Persist 失败 → raise
  - 成功路径 → SUCCESS report + persist
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.agent import TrendAgent
from app.agent.perceiver import PerceivedContext
from app.agent.schemas import AnalysisReport, AnalysisStatus


# === Fixtures ===

def make_perceived_ctx() -> PerceivedContext:
    """真实 PerceivedContext（不是 mock）"""
    from app.signals.regime import Regime, RegimeInfo
    from app.signals.cost_model import CostEstimate

    return PerceivedContext(
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


def make_success_report() -> AnalysisReport:
    return AnalysisReport(
        pair="BTC-USDT",
        timeframe="1h",
        regime="bull",
        regime_confidence=0.75,
        reasoning="BTC 1h 处于多头格局。",
    )


def make_fallback_report() -> AnalysisReport:
    return AnalysisReport(
        pair="BTC-USDT",
        timeframe="1h",
        regime="bull",
        regime_confidence=0.7,
        reasoning="LLM 推理服务不可用（已降级）。",
        analysis_status=AnalysisStatus.FALLBACK,
    )


# === Tests ===

class TestTrendAgentHappyPath:
    @pytest.mark.asyncio
    async def test_analyze_returns_success_report(self):
        """Happy path: SUCCESS 报告 + persist"""
        mock_perceiver = AsyncMock()
        mock_perceiver.perceive = AsyncMock(return_value=make_perceived_ctx())

        mock_reasoner = AsyncMock()
        mock_reasoner.reason = AsyncMock(return_value=make_success_report())

        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.flush = MagicMock()

        agent = TrendAgent(
            perceiver=mock_perceiver,
            reasoner=mock_reasoner,
            session=mock_session,
        )
        report = await agent.analyze("BTC-USDT", "1h")

        assert report.analysis_status == AnalysisStatus.SUCCESS
        assert report.pair == "BTC-USDT"
        assert report.timeframe == "1h"
        # Persist 调了
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()
        # Reasoner 只调 1 次
        assert mock_reasoner.reason.await_count == 1


class TestTrendAgentRetry:
    @pytest.mark.asyncio
    async def test_llm_failure_retries_twice_then_fallback(self):
        """LLM 失败 2 次 → 第 3 次返回 FALLBACK"""
        mock_perceiver = AsyncMock()
        mock_perceiver.perceive = AsyncMock(return_value=make_perceived_ctx())

        # reasoner 失败 2 次后改成 FALLBACK 报告
        mock_reasoner = AsyncMock()
        mock_reasoner.reason = AsyncMock(side_effect=[
            Exception("timeout 1"),
            Exception("timeout 2"),
            make_fallback_report(),  # 第三次成功
        ])

        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.flush = MagicMock()

        agent = TrendAgent(
            perceiver=mock_perceiver,
            reasoner=mock_reasoner,
            session=mock_session,
            max_retries=2,
            initial_backoff=0.01,  # 测试时短
        )
        report = await agent.analyze("BTC-USDT", "1h")

        # reasoner 调 3 次（2 retry + 1 final）
        assert mock_reasoner.reason.await_count == 3
        # 最终报告是 FALLBACK
        assert report.analysis_status == AnalysisStatus.FALLBACK
        # FALLBACK 也 persist
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_all_retries_fail_returns_fallback(self):
        """LLM 失败超过 max_retries → 仍返回 FALLBACK（不抛）"""
        mock_perceiver = AsyncMock()
        mock_perceiver.perceive = AsyncMock(return_value=make_perceived_ctx())

        mock_reasoner = AsyncMock()
        mock_reasoner.reason = AsyncMock(side_effect=Exception("always fails"))

        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.flush = MagicMock()

        agent = TrendAgent(
            perceiver=mock_perceiver,
            reasoner=mock_reasoner,
            session=mock_session,
            max_retries=2,
            initial_backoff=0.01,
        )
        report = await agent.analyze("BTC-USDT", "1h")

        # reasoner 调 max_retries + 1 = 3 次
        assert mock_reasoner.reason.await_count == 3
        # 仍是 FALLBACK（不抛异常）
        assert report.analysis_status == AnalysisStatus.FALLBACK


class TestTrendAgentPerceiveFailure:
    @pytest.mark.asyncio
    async def test_perceive_failure_raises(self):
        """Perceive 失败 → raise（不重试，Perceive 失败 = 数据问题）"""
        mock_perceiver = AsyncMock()
        mock_perceiver.perceive = AsyncMock(side_effect=Exception("network error"))

        mock_reasoner = AsyncMock()
        mock_session = MagicMock()

        agent = TrendAgent(
            perceiver=mock_perceiver,
            reasoner=mock_reasoner,
            session=mock_session,
        )

        with pytest.raises(Exception, match="network error"):
            await agent.analyze("BTC-USDT", "1h")

        # reasoner 没被调
        assert mock_reasoner.reason.await_count == 0
        # session 没被 add
        mock_session.add.assert_not_called()


class TestTrendAgentScopeEnforcement:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("pair", ["SOL-USDT", "DOGE-USDT", "XRP-USDT"])
    async def test_non_btc_eth_rejected_at_perceive(self, pair):
        """Perceiver 内部拒接非 BTC/ETH，TrendAgent 也拒"""
        mock_perceiver = AsyncMock()
        mock_perceiver.perceive = AsyncMock(side_effect=ValueError(
            f"{pair} 不在分析范围"
        ))

        mock_reasoner = AsyncMock()
        mock_session = MagicMock()

        agent = TrendAgent(
            perceiver=mock_perceiver,
            reasoner=mock_reasoner,
            session=mock_session,
        )

        with pytest.raises(ValueError, match="不在分析范围"):
            await agent.analyze(pair, "1h")


class TestTrendAgentTimeout:
    @pytest.mark.asyncio
    async def test_reasoner_timeout_caught_as_fallback(self):
        """asyncio.TimeoutError 被识别为 LLM 失败 → FALLBACK"""
        import asyncio

        mock_perceiver = AsyncMock()
        mock_perceiver.perceive = AsyncMock(return_value=make_perceived_ctx())

        mock_reasoner = AsyncMock()
        mock_reasoner.reason = AsyncMock(side_effect=asyncio.TimeoutError())

        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.flush = MagicMock()

        agent = TrendAgent(
            perceiver=mock_perceiver,
            reasoner=mock_reasoner,
            session=mock_session,
            max_retries=1,  # 加速测试
            initial_backoff=0.01,
        )
        report = await agent.analyze("BTC-USDT", "1h")

        # 2 次调用（1 retry + 1 终止）
        assert mock_reasoner.reason.await_count == 2
        assert report.analysis_status == AnalysisStatus.FALLBACK


class TestTrendAgentDependencies:
    @pytest.mark.asyncio
    async def test_default_perceiver_reasoner_session_lazy_init(self):
        """不传 deps 时应该懒初始化（占位 — 实际不跑网络）"""
        # 这个测试只验证 TrendAgent 可以不传 deps 构造
        agent = TrendAgent()
        assert agent._perceiver is None
        assert agent._reasoner is None
        assert agent._session is None