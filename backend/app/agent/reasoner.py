"""Reasoner — LLM 推理层（Task 4）

职责：
  1. 拼装 prompt（system + user）
  2. 调 LLM provider
  3. 解析返回为 AnalysisReport
  4. 处理 3 种降级路径：
     - SUCCESS：Pydantic 解析成功
     - PARSE_ERROR：JSON 解析失败 / schema 不合规
     - FALLBACK：LLM 调用异常（5xx / timeout / 缺 key）

不做什么：
  - 不写 DB（Task 5）
  - 不做 retry（Task 6 由 TrendAgent 主类实现）
  - 不感知 signals/*（只接 PerceivedContext）

参考 spec: docs/superpowers/specs/2026-10-03-trend-analysis-agent.md §3
"""

from __future__ import annotations

import logging
from typing import Any

from app.agent.llm_client import LLMProvider, extract_json_from_response
from app.agent.perceiver import PerceivedContext
from app.agent.prompts import SYSTEM_PROMPT_TEMPLATE, build_user_prompt
from app.agent.schemas import AnalysisReport, AnalysisStatus

logger = logging.getLogger(__name__)


# === Fallback reasonings (per regime) ===

_FALLBACK_REASONING = {
    "bull": "LLM 推理服务不可用（已降级）。基于 signals/regime 判断当前为多头格局，趋势类策略可能有效，建议结合其他周期确认。",
    "bear": "LLM 推理服务不可用（已降级）。基于 signals/regime 判断当前为空头格局，反弹做空为主，建议关注关键阻力位。",
    "choppy": "LLM 推理服务不可用（已降级）。基于 signals/regime 判断当前为震荡市，均值回归类策略可能有效，建议低仓位。",
    "crisis": "LLM 推理服务不可用（已降级）。基于 signals/regime 判断当前为危机状态，波动率策略可能有效，建议减仓观望。",
}

_PARSE_ERROR_REASONING = (
    "LLM 返回内容无法解析为合规 JSON。请检查 LLM 服务可用性，或人工 review raw_response 字段。"
)


class Reasoner:
    """Reasoner — PerceivedContext → AnalysisReport"""

    def __init__(self, provider: LLMProvider, timeout: int = 30) -> None:
        self._provider = provider
        self._timeout = timeout

    async def reason(self, ctx: PerceivedContext) -> AnalysisReport:
        """主入口

        Returns:
            AnalysisReport（含 analysis_status 标记降级路径）
        """
        system_prompt = SYSTEM_PROMPT_TEMPLATE
        user_prompt = build_user_prompt(ctx)

        # 1. 调 LLM
        try:
            raw_response = await self._provider.complete(
                system=system_prompt, user=user_prompt
            )
        except Exception as e:
            # FALLBACK 路径
            logger.warning(f"LLM 调用失败 → FALLBACK: {e}")
            return self._build_fallback(ctx, error_msg=str(e))

        # 2. 解析 JSON
        parsed = extract_json_from_response(raw_response)
        if parsed is None:
            logger.warning(f"LLM 返回非 JSON → PARSE_ERROR: {raw_response[:200]}")
            return self._build_parse_error(ctx, raw_response)

        # 3. Pydantic 解析
        try:
            report = AnalysisReport(
                pair=ctx.pair,
                timeframe=ctx.timeframe,
                regime=parsed.get("regime", ctx.regime.regime.value),
                regime_confidence=float(parsed.get("regime_confidence", 0.5)),
                reasoning=parsed.get("reasoning", ""),
                key_observations=parsed.get("key_observations", []),
                risks=parsed.get("risks", []),
                analysis_status=AnalysisStatus.SUCCESS,
            )
            return report
        except Exception as e:
            # Schema 不合规
            logger.warning(f"LLM 返回 schema 不合规 → PARSE_ERROR: {e}")
            return self._build_parse_error(ctx, raw_response)

    def _build_fallback(self, ctx: PerceivedContext, error_msg: str) -> AnalysisReport:
        """LLM 调用失败 → FALLBACK"""
        regime_value = (
            ctx.regime.regime.value
            if hasattr(ctx.regime.regime, "value")
            else str(ctx.regime.regime)
        )
        return AnalysisReport(
            pair=ctx.pair,
            timeframe=ctx.timeframe,
            regime=regime_value,
            regime_confidence=ctx.regime.confidence,
            reasoning=_FALLBACK_REASONING.get(
                regime_value, "LLM 推理服务不可用，已降级为规则引擎建议。"
            ),
            key_observations=["Agent 推理服务暂时不可用"],
            risks=[f"LLM 错误: {error_msg[:200]}"],
            analysis_status=AnalysisStatus.FALLBACK,
        )

    def _build_parse_error(
        self, ctx: PerceivedContext, raw_response: str
    ) -> AnalysisReport:
        """JSON 解析失败 / schema 不合规 → PARSE_ERROR"""
        regime_value = (
            ctx.regime.regime.value
            if hasattr(ctx.regime.regime, "value")
            else str(ctx.regime.regime)
        )
        return AnalysisReport(
            pair=ctx.pair,
            timeframe=ctx.timeframe,
            regime=regime_value,
            regime_confidence=ctx.regime.confidence,
            reasoning=_PARSE_ERROR_REASONING,
            key_observations=[],
            risks=[],
            analysis_status=AnalysisStatus.PARSE_ERROR,
            raw_llm_response=raw_response[:5000],  # 截断防爆
        )