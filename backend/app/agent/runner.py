"""AgentRunner — Agent 后台调度器（Task 7）

设计：
  - 用 asyncio.create_task + while True + asyncio.sleep
  - 不引 apscheduler 依赖（项目现有模式 — regime_shift_engine / github_sync）
  - 5m 循环（spec §6.2：576 calls/day = ¥173/月）
  - 8 calls per cycle: 2 pairs (BTC/ETH) × 4 timeframes (5m/15m/1h/1d)
  - 并发跑（asyncio.gather） — 单个失败不阻塞其他
  - start() / stop() lifecycle

参考 spec: docs/superpowers/specs/2026-10-03-trend-analysis-agent.md §6.2
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agent.agent import TrendAgent

logger = logging.getLogger(__name__)


# === Constants ===

AGENT_PAIRS = ("BTC-USDT", "ETH-USDT")
AGENT_TIMEFRAMES = ("5m", "15m", "1h", "1d")
DEFAULT_INTERVAL_SECONDS = 300  # 5 分钟


class AgentRunner:
    """TrendAgent 后台调度器"""

    def __init__(
        self,
        agent: "TrendAgent | None" = None,
        interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
        pairs: tuple[str, ...] = AGENT_PAIRS,
        timeframes: tuple[str, ...] = AGENT_TIMEFRAMES,
    ) -> None:
        self._agent = agent
        self._interval = interval_seconds
        self._pairs = pairs
        self._timeframes = timeframes
        self._task: asyncio.Task | None = None
        self._running = False

    def set_agent(self, agent: "TrendAgent") -> None:
        """DI 注入 agent（在 lifespan 阶段调用）"""
        self._agent = agent

    def start(self) -> None:
        """启动后台循环（fire-and-forget）"""
        if self._running:
            logger.debug("[agent_runner] already running, skip start()")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            f"[agent_runner] started: interval={self._interval}s, "
            f"pairs={self._pairs}, timeframes={self._timeframes}"
        )

    async def stop(self) -> None:
        """停止后台循环"""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("[agent_runner] stopped")

    async def _loop(self) -> None:
        """主循环：每 interval_seconds 跑一次 cycle"""
        # 首次启动延后 5s（等 app 起来 + db init）
        await asyncio.sleep(5)
        while self._running:
            try:
                await self.run_once()
            except Exception as e:
                logger.error(f"[agent_runner] cycle failed: {e}", exc_info=True)
            await asyncio.sleep(self._interval)

    async def run_once(self) -> list:
        """手动触发 1 个 cycle（测试用 + API 端点用）

        Returns:
            list of AnalysisReport（可能含 FALLBACK — 不抛异常）
        """
        if self._agent is None:
            raise RuntimeError(
                "AgentRunner._agent 未配置。请通过 AgentRunner(agent=...) 注入或调 set_agent()"
            )

        # 并发跑 8 次 analyze
        tasks = [
            self._safe_analyze(pair, tf)
            for pair in self._pairs
            for tf in self._timeframes
        ]
        reports = await asyncio.gather(*tasks, return_exceptions=False)
        success_count = sum(
            1 for r in reports if r is not None and not isinstance(r, Exception)
        )
        logger.info(
            f"[agent_runner] cycle done: {success_count}/{len(tasks)} succeeded"
        )
        return reports

    async def _safe_analyze(self, pair: str, timeframe: str):
        """单次 analyze + 异常捕获（不阻塞其他并发任务）"""
        try:
            return await self._agent.analyze(pair, timeframe)
        except Exception as e:
            logger.error(
                f"[agent_runner] analyze({pair}, {timeframe}) failed: {e}",
                exc_info=True,
            )
            return None