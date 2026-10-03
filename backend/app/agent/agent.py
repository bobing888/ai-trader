"""TrendAgent — Agent 主类（Task 6）

职责：
  1. perceive(pair, timeframe) → PerceivedContext
  2. reason(ctx) → AnalysisReport (with retry)
  3. persist(report) → 写 DB
  4. analyze(pair, timeframe) → orchestrate 1+2+3

错误处理（spec §7）：
  - Perceive 失败 → 抛（数据问题，不重试）
  - Reason 失败 → 重试 max_retries 次（指数退避）→ 最终 FALLBACK
  - Persist 失败 → 抛（DB 问题，必须知道）
  - LLM 30s 超时 → 视为 LLM 失败

不做什么：
  - 不调 LLM（reasoner 调）
  - 不感知 signals/*（perceiver 调）
  - 不做调度（runner 调，Task 7）

参考 spec: docs/superpowers/specs/2026-10-03-trend-analysis-agent.md §3
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.agent.perceiver import PerceivedContext, Perceiver
from app.agent.persistence import AnalysisRepository
from app.agent.reasoner import Reasoner
from app.agent.schemas import AnalysisReport, AnalysisStatus

logger = logging.getLogger(__name__)


# === Constants ===

DEFAULT_MAX_RETRIES = 2
DEFAULT_INITIAL_BACKOFF_SECONDS = 1.0
DEFAULT_BACKOFF_MULTIPLIER = 3.0  # 1s, 3s, 9s, ...
DEFAULT_TIMEOUT_SECONDS = 30.0


class TrendAgent:
    """Trend Analysis Agent 主类"""

    def __init__(
        self,
        perceiver: Perceiver | None = None,
        reasoner: Reasoner | None = None,
        session: Any = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_backoff: float = DEFAULT_INITIAL_BACKOFF_SECONDS,
        backoff_multiplier: float = DEFAULT_BACKOFF_MULTIPLIER,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._perceiver = perceiver
        self._reasoner = reasoner
        self._session = session
        self._max_retries = max_retries
        self._initial_backoff = initial_backoff
        self._backoff_multiplier = backoff_multiplier
        self._timeout = timeout

    async def analyze(self, pair: str, timeframe: str) -> AnalysisReport:
        """主入口 — orchestrate perceive → reason → persist

        Returns:
            AnalysisReport（SUCCESS / FALLBACK 之一）

        Raises:
            ValueError: pair/timeframe 非法（来自 Perceiver）
            Exception: Perceive 失败 或 Persist 失败
        """
        # Lazy init
        if self._perceiver is None:
            self._perceiver = Perceiver()
        if self._reasoner is None:
            # 实际部署时通过 set_reasoner / DI 注入，懒初始化仅作 fallback
            raise RuntimeError(
                "TrendAgent.reasoner 未配置。请通过 TrendAgent(reasoner=...) 注入。"
            )

        # 1. Perceive（失败 → raise，数据问题不重试）
        ctx = await self._perceiver.perceive(pair, timeframe)

        # 2. Reason（带 retry + 30s timeout）
        report = await self._reason_with_retry(ctx)

        # 3. Persist（失败 → raise，DB 问题必须知道）
        AnalysisRepository.save(self._session, report)
        # 不 commit — 让外层事务管理

        return report

    async def _reason_with_retry(self, ctx: PerceivedContext) -> AnalysisReport:
        """调 reasoner，失败重试 max_retries 次（指数退避）"""
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                report = await asyncio.wait_for(
                    self._reasoner.reason(ctx), timeout=self._timeout
                )
                return report
            except asyncio.TimeoutError as e:
                last_error = e
                logger.warning(
                    f"Reasoner timeout (attempt {attempt + 1}/{self._max_retries + 1})"
                )
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Reasoner failed (attempt {attempt + 1}/{self._max_retries + 1}): {e}"
                )

            # Backoff（除了最后一次）
            if attempt < self._max_retries:
                backoff = self._initial_backoff * (self._backoff_multiplier ** attempt)
                await asyncio.sleep(backoff)

        # 全部 retry 失败 → 构造 FALLBACK report（不抛，因为 LLM 不可用不该阻塞 aggregator）
        return self._build_emergency_fallback(ctx, last_error)

    def _build_emergency_fallback(
        self, ctx: PerceivedContext, error: Exception | None
    ) -> AnalysisReport:
        """全 retry 失败的最终降级（emergency fallback）"""
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
            reasoning=(
                f"Agent 推理服务多次失败（{self._max_retries + 1} 次），"
                f"已降级为 signals/regime 直出。建议人工 review。"
            ),
            key_observations=["Agent 推理服务暂时不可用"],
            risks=[f"LLM 错误: {str(error)[:200]}" if error else "未知错误"],
            analysis_status=AnalysisStatus.FALLBACK,
        )