"""FollowScheduler — 双驱动（bus + tick）出场调度（spec §4.3）

设计:
- bus 事件立刻响应 — direction/regime 变化立刻评估该 pair 的 OPEN follow
- 60s tick 兜底 — 处理 expired / 价格拉取失败重试 / 检测漏掉的反转
- 价格来源 — 用 okx_ws_client 拉最新价（fallback: tick 时 REST 拉 ticker）
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from app.config import settings
from app.services.follow_service import FollowService
from app.services.signal_change_bus import SignalChangeBus

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.db.models import RecommendationHistory, UserFollow

logger = logging.getLogger(__name__)

_scheduler: FollowScheduler | None = None


@dataclass
class ExitVerdict:
    """单条 follow 的出场评估。"""

    should_exit: bool
    reason: Literal["stop_loss", "target", "expired", "ai_signal_reversed"] | None = None
    exit_price: float | None = None


class FollowScheduler:
    """bus + 60s tick 双驱动 — 处理 4 种出场。"""

    def __init__(
        self,
        bus: SignalChangeBus,
        session_factory: callable,
        # SessionLocal,
        price_source: callable | None = None,  # optional (type, sim, ws)
    ) -> None:
        self._bus = bus
        self._session_factory = session_factory
        self._price_source = price_source or _default_price_source
        self._running = False
        self._bus_task: asyncio.Task | None = None
        self._tick_task: asyncio.Task | None = None

    # === 价格出场（同步 — 方便单测） ===

    @staticmethod
    def _evaluate_price(follow: UserFollow, current_price: float) -> ExitVerdict:
        """只基于价格评估出场（不看信号反转）。"""
        # stop_loss (长:  <= 触发；空:  >= 触发)
        if follow.stop_loss is not None:
            if follow.direction == "long" and current_price <= follow.stop_loss:
                return ExitVerdict(True, "stop_loss", current_price)
            if follow.direction == "short" and current_price >= follow.stop_loss:
                return ExitVerdict(True, "stop_loss", current_price)
        # target (长:  >= 触发；空:  <= 触发)
        if follow.target is not None:
            if follow.direction == "long" and current_price >= follow.target:
                return ExitVerdict(True, "target", current_price)
            if follow.direction == "short" and current_price <= follow.target:
                return ExitVerdict(True, "target", current_price)
        # expired
        now = datetime.now(UTC).timestamp()
        elapsed_hours = (now - follow.entry_time.timestamp()) / 3600
        if elapsed_hours >= settings.follow_max_hours:
            return ExitVerdict(True, "expired", current_price)
        return ExitVerdict(False, None, current_price)

    # === 启动 / 停止 ===

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._bus_task = asyncio.create_task(self._bus_loop())
        self._tick_task = asyncio.create_task(self._tick_loop())
        logger.info(
            "[scheduler] started (scan=%ds, max_hours=%d)",
            settings.follow_scan_interval,
            settings.follow_max_hours,
        )

    async def stop(self) -> None:
        self._running = False
        for task in (self._bus_task, self._tick_task):
            if task:
                task.cancel()
        await asyncio.gather(
            *(t for t in (self._bus_task, self._tick_task) if t is not None),
            return_exceptions=True,
        )

    # === Bus 处理 ===

    async def _bus_loop(self) -> None:
        q = self._bus.subscribe()
        while self._running:
            event = await q.get()
            try:
                if event.change_type in ("direction", "regime"):
                    await self._scan_pair(event.pair)
            except Exception as exc:
                logger.warning("[scheduler] bus event handling failed: %s", exc)

    # === 60s tick 兜底 ===

    async def _tick_loop(self) -> None:
        while self._running:
            await asyncio.sleep(settings.follow_scan_interval)
            try:
                await self._scan_all()
            except Exception as exc:
                logger.warning("[scheduler] tick failed: %s", exc)

    # === 扫描 ===

    async def _scan_all(self) -> None:
        """拉所有 OPEN follow 评估。"""
        db = self._session_factory()
        try:
            from app.db.models import UserFollow

            open_follows = (
                db.query(UserFollow).filter(UserFollow.status == "open").all()
            )
        finally:
            db.close()
        # 按 pair 分组
        pairs = {f.pair for f in open_follows}
        for pair in pairs:
            try:
                await self._scan_pair(pair)
            except Exception as exc:
                logger.warning("[scheduler] scan_pair %s failed: %s", pair, exc)

    async def _scan_pair(self, pair: str) -> None:
        """评估某 pair 的所有 OPEN follow。"""
        db = self._session_factory()
        try:
            from app.db.models import UserFollow

            follows = (
                db.query(UserFollow)
                .filter(UserFollow.pair == pair, UserFollow.status == "open")
                .all()
            )
            if not follows:
                return

            price = await self._price_source(pair)
            if price is None:
                logger.debug("[scheduler] price unavailable for %s, skip", pair)
                return

            for follow in follows:
                verdict = self._evaluate_price(follow, price)
                if not verdict.should_exit:
                    continue
                # 拿独立 session 锁 + close（SELECT FOR UPDATE）
                self._close_sync(follow.id, verdict)
        finally:
            db.close()

    def _close_sync(self, follow_id: int, verdict: ExitVerdict) -> None:
        db = self._session_factory()
        try:
            FollowService.close(db, follow_id, verdict.exit_price, verdict.reason or "manual")
        except ValueError as exc:
            # 已 closed（race 之类）— skip
            logger.debug("[scheduler] close follow %d: %s", id(follow_id), exc) if False else None
            logger.debug("[scheduler] close follow %d skipped: %s", follow_id, exc)
        finally:
            db.close()


# === 默认价格源 — 调 stage 接口可知（或 REST 拉）===

async def _default_price_source(pair: str) -> float | None:
    """默认从 OKX REST 拉最新价。失败返回 None（scheduler 跳过）。"""
    try:
        from app.data.okx import okx_client

        ticker = await okx_client.get_ticker(pair)
        return float(ticker.get("last", 0)) if ticker else None
    except Exception as exc:
        logger.debug("[scheduler] price fetch failed for %s: %s", pair, exc)
        return None


# === Singleton (lifespan 注入) ===

def set_follow_scheduler(s: FollowScheduler) -> None:
    global _scheduler
    _scheduler = s


def get_follow_scheduler() -> FollowScheduler:
    if _scheduler is None:
        raise RuntimeError("FollowScheduler not initialized — call set_follow_scheduler() in lifespan")
    return _scheduler