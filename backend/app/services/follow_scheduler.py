"""FollowScheduler — 双驱动（bus + tick）出场调度（spec §4.3）

设计:
- bus 事件立刻响应 — direction/regime 变化立刻评估该 pair 的 OPEN follow
- 60s tick 兜底 — 处理 expired / 价格拉取失败重试 / 检测漏掉的反转
- 价格来源 — 用 okx_ws_client 拉最新价（fallback: tick 时 REST 拉 ticker）

Step 3-A: detect_reversal 接入 — 对每个 OPEN follow 也评估「信号反转」,
         命中 → close with reason=ai_signal_reversed（spec §4.2 + §6.2 #5）
Step 3-B: 加 observability — 每次 scan_pair 出 INFO 日志，便于线上追踪。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal

from app.config import settings
from app.services.follow_service import FollowService
from app.services.signal_change_bus import SignalChangeBus
from app.services.signal_change_detector import detect_reversal

if TYPE_CHECKING:
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

    # === 信号反转出场（同步 — 方便单测） ===

    @staticmethod
    def _evaluate_signal_reversal(
        follow: UserFollow,
        current: RecommendationHistory | None,
        previous: RecommendationHistory | None,
        lookback_history: list[RecommendationHistory],
    ) -> ExitVerdict:
        """Step 3-A: 把 detect_reversal 的判定包装成 ExitVerdict。

        - current=None → 不触发（让 price 评估兜底，DB 没数据别误关）
        - reversed=True → ai_signal_reversed（exit_price=None，由调度器下一步 fetch）
        - reversed=False → 不出场
        """
        if current is None:
            return ExitVerdict(False, None, None)
        verdict = detect_reversal(follow, current, previous, lookback_history)
        if verdict.reversed:
            return ExitVerdict(True, "ai_signal_reversed", None)
        return ExitVerdict(False, None, None)

    @staticmethod
    def _load_pair_recent_recos(
        db, pair: str, timeframe: str, window_seconds: int = 180
    ) -> tuple[RecommendationHistory | None, RecommendationHistory | None, list[RecommendationHistory]]:
        """从 DB 加载 pair 当前帧 + 上一帧 + 3 分钟窗口（spec §4.2）。

        返回: (current, previous, lookback_history)
        - 缺 history 时 current=None（让 price 兜底评估）
        - lookback_history 保留供未来扩展（variance / agreement 变化等）
        """
        from app.db.models import RecommendationHistory  # noqa: N817

        recent = (
            db.query(RecommendationHistory)
            .filter(RecommendationHistory.pair == pair, RecommendationHistory.timeframe == timeframe)
            .order_by(RecommendationHistory.scanned_at.desc())
            .limit(20)
            .all()
        )
        if not recent:
            return None, None, []
        current = recent[0]
        previous = recent[1] if len(recent) > 1 else None
        window_start = current.scanned_at - timedelta(seconds=window_seconds)
        lookback = [r for r in recent if r.scanned_at >= window_start]
        return current, previous, lookback

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
        """评估某 pair 的所有 OPEN follow。

        Step 3-A: 先评估「信号反转」（close with reason=ai_signal_reversed），
                  再评估价格出场（SL/TP/expired）。信号反转优先 — 防止错失反转退出。
        Step 3-B: 加 INFO 日志：扫描数 + close 数 + close 原因分布。
        """
        db = self._session_factory()
        closed_reasons: dict[str, int] = {}
        try:
            from app.db.models import UserFollow

            follows = (
                db.query(UserFollow)
                .filter(UserFollow.pair == pair, UserFollow.status == "open")
                .all()
            )
            if not follows:
                logger.debug("[scheduler] %s: no open follows", pair)
                return

            price = await self._price_source(pair)
            if price is None:
                logger.warning("[scheduler] %s: price unavailable, skip", pair)
                return

            # 一次性加载 recent recos（避免循环里 N 次查询）
            # 用任一 follow 的 timeframe（同一 pair 多 timeframe 的场景 v2 再说）
            timeframe = follows[0].timeframe
            current, previous, lookback = self._load_pair_recent_recos(db, pair, timeframe)
            logger.info(
                "[scheduler] %s tf=%s: scanned=%d price=%.2f has_recos=%s",
                pair,
                timeframe,
                len(follows),
                price,
                current is not None,
            )

            for follow in follows:
                # Step 3-A: 信号反转优先
                rev_verdict = self._evaluate_signal_reversal(follow, current, previous, lookback)
                if rev_verdict.should_exit:
                    # exit_price 用当前市场价
                    self._close_sync(follow.id, ExitVerdict(True, "ai_signal_reversed", price))
                    closed_reasons["ai_signal_reversed"] = closed_reasons.get("ai_signal_reversed", 0) + 1
                    continue
                # 价格出场
                verdict = self._evaluate_price(follow, price)
                if not verdict.should_exit:
                    continue
                # 拿独立 session 锁 + close（SELECT FOR UPDATE）
                self._close_sync(follow.id, verdict)
                if verdict.reason:
                    closed_reasons[verdict.reason] = closed_reasons.get(verdict.reason, 0) + 1
        finally:
            db.close()

        if closed_reasons:
            logger.info(
                "[scheduler] %s: closed=%s",
                pair,
                ", ".join(f"{k}={v}" for k, v in closed_reasons.items()),
            )

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
