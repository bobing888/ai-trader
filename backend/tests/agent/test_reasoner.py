"""Tests for backend.app.agent.reasoner — LLM 推理层（Task 4）.

覆盖（spec §3 + plan Task 4）：
  - Reasoner.reason() 把 PerceivedContext 转成 AnalysisReport
  - 调 LLMProvider.complete() 拿 raw response
  - Pydantic 强 schema 解析（成功路径）
  - 解析失败 → PARSE_ERROR status + raw_response 保留
  - LLM 调用失败 → FALLBACK status（重试在 Task 6 实现）
  - prompt 包含中文金融推理（system + user）
  - DeepSeek 实际可被 mock
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.reasoner import Reasoner
from app.agent.schemas import AnalysisReport, AnalysisStatus


# === Fixtures ===

def make_perceived_context() -> MagicMock:
    """Mock 一个 PerceivedContext，简化测试"""
    from datetime import datetime, timezone
    ctx = MagicMock()
    ctx.pair = "BTC-USDT"
    ctx.timeframe = "1h"
    ctx.data_completeness = 1.0
    ctx.ohlcv = [{"c": 50000.0, "h": 50100.0, "l": 49900.0, "o": 50000.0, "vol": 100.0, "timestamp": 1234567890000} for _ in range(100)]
    ctx.regime = MagicMock()
    ctx.regime.regime.value = "bull"
    ctx.regime.confidence = 0.75
    ctx.regime.adx = 28.5
    ctx.regime.hurst = 0.62
    ctx.regime.description = "强趋势 + 正收益"
    ctx.strategy_signals = []
    ctx.cost_estimate = MagicMock()
    ctx.cost_estimate.total_round_trip_pct = 0.002
    # 关键：fetched_at 必须是真实 datetime (prompt json.dumps 会序列化)
    ctx.fetched_at = datetime(2026, 10, 3, 20, 0, 0, tzinfo=timezone.utc)
    return ctx


def make_valid_llm_response() -> str:
    """模拟 DeepSeek 返回的合规 JSON"""
    return json.dumps({
        "regime": "bull",
        "regime_confidence": 0.75,
        "reasoning": "BTC 1h 处于强多头格局，ADX 28 表明趋势明确，Hurst 0.62 表明持续性较强。MACD 金叉形成，成交量温和放大。建议关注回调做多机会。",
        "key_observations": [
            "ADX 升至 28，趋势强度增加",
            "Hurst 0.62 表明价格序列持续性较强",
            "成交量温和放大配合价格上涨"
        ],
        "risks": [
            "若 ADX 回落至 20 以下需警惕趋势减弱",
            "近期上方阻力位在 51500 附近"
        ]
    }, ensure_ascii=False)


# === Tests ===

class TestReasonerSuccessPath:
    @pytest.mark.asyncio
    async def test_reason_returns_analysis_report(self):
        """Happy path: 解析成功 → AnalysisReport"""
        mock_response = make_valid_llm_response()
        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(return_value=mock_response)

        reasoner = Reasoner(provider=mock_provider)
        ctx = make_perceived_context()
        report = await reasoner.reason(ctx)

        assert isinstance(report, AnalysisReport)
        assert report.pair == "BTC-USDT"
        assert report.timeframe == "1h"
        assert report.regime == "bull"
        assert report.analysis_status == AnalysisStatus.SUCCESS
        assert len(report.reasoning) >= 10
        assert mock_provider.complete.await_count == 1


class TestReasonerParseError:
    @pytest.mark.asyncio
    async def test_invalid_json_returns_parse_error(self):
        """LLM 返回非 JSON → PARSE_ERROR 状态"""
        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(return_value="这不是 JSON，是一段中文")

        reasoner = Reasoner(provider=mock_provider)
        ctx = make_perceived_context()
        report = await reasoner.reason(ctx)

        assert report.analysis_status == AnalysisStatus.PARSE_ERROR
        assert report.raw_llm_response == "这不是 JSON，是一段中文"
        assert report.regime in ("bull", "bear", "choppy", "crisis")  # fallback
        assert len(report.reasoning) >= 10  # 必有降级 reason

    @pytest.mark.asyncio
    async def test_invalid_schema_returns_parse_error(self):
        """LLM 返回 JSON 但 Pydantic 不合规 → PARSE_ERROR"""
        bad_json = json.dumps({"regime": "invalid_regime"})  # 缺 confidence + reasoning
        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(return_value=bad_json)

        reasoner = Reasoner(provider=mock_provider)
        ctx = make_perceived_context()
        report = await reasoner.reason(ctx)

        assert report.analysis_status == AnalysisStatus.PARSE_ERROR
        assert report.raw_llm_response == bad_json


class TestReasonerFallback:
    @pytest.mark.asyncio
    async def test_llm_exception_returns_fallback(self):
        """LLM 调用抛异常 → FALLBACK 状态"""
        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(side_effect=Exception("API timeout"))

        reasoner = Reasoner(provider=mock_provider)
        ctx = make_perceived_context()
        report = await reasoner.reason(ctx)

        assert report.analysis_status == AnalysisStatus.FALLBACK
        assert "降级" in report.reasoning or "fallback" in report.reasoning.lower()
        assert report.regime in ("bull", "bear", "choppy", "crisis")
        assert report.raw_llm_response is None


class TestReasonerPrompt:
    @pytest.mark.asyncio
    async def test_prompt_contains_market_data(self):
        """Prompt 必须包含市场数据（regime + price + ohlcv 摘要）"""
        mock_response = make_valid_llm_response()
        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(return_value=mock_response)

        reasoner = Reasoner(provider=mock_provider)
        ctx = make_perceived_context()
        await reasoner.reason(ctx)

        # 抓取传给 provider 的 prompt
        call_args = mock_provider.complete.call_args
        system_prompt = call_args.kwargs.get("system", call_args.args[0] if call_args.args else "")
        user_prompt = call_args.kwargs.get("user", call_args.args[1] if len(call_args.args) > 1 else "")

        # System 必须是中文金融推理
        assert "BTC" in system_prompt or "ETH" in system_prompt or "市场" in system_prompt or "趋势" in system_prompt
        # User prompt 包含 pair + timeframe + regime
        user_combined = str(user_prompt) + str(system_prompt)
        assert "BTC-USDT" in user_combined
        assert "1h" in user_combined
        assert "bull" in user_combined


class TestReasonerProviderProtocol:
    @pytest.mark.asyncio
    async def test_accepts_any_provider_with_complete_method(self):
        """Reasoner 应该接受任何有 .complete() 异步方法的对象（Protocol 风格）"""
        class CustomProvider:
            def __init__(self):
                self.called = False

            async def complete(self, system, user, **kw):
                self.called = True
                return make_valid_llm_response()

        provider = CustomProvider()
        reasoner = Reasoner(provider=provider)
        ctx = make_perceived_context()
        report = await reasoner.reason(ctx)

        assert provider.called
        assert report.analysis_status == AnalysisStatus.SUCCESS