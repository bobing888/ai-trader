"""SignalChangeBus — 进程内 asyncio pub/sub（spec §4.0）

recorder emit SignalChangeEvent → FollowScheduler + WS endpoint fanout 给订阅者。

设计要点：
- 模块级 singleton + set_signal_bus()/get_signal_bus() 注入（避免循环 import — 跟 notification_service 一致）
- subscribe() 返回独立 queue（maxsize=1024）
- emit() 用 put_nowait — 满了 log + skip（避免阻塞 recorder）
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.db.models import RecommendationHistory

logger = logging.getLogger(__name__)

# module-level singleton
_bus: SignalChangeBus | None = None


@dataclass
class SignalChangeEvent:
    """一次信号变化事件（recorder → bus → consumer）。"""

    pair: str
    timeframe: str
    previous: RecommendationHistory | None
    current: RecommendationHistory  # type: ignore[assignment]
    change_type: Literal[
        "direction", "regime", "confidence", "no_signal", "first_emit", "no_change"
    ]


class SignalChangeBus:
    """asyncio 事件总线 — 进程内 fanout。"""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[SignalChangeEvent]] = []

    def subscribe(self) -> asyncio.Queue[SignalChangeEvent]:
        """新订阅 — 每个 subscriber 一个独立 queue。"""
        q: asyncio.Queue[SignalChangeEvent] = asyncio.Queue(maxsize=1024)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[SignalChangeEvent]) -> None:
        """取消订阅（WS 断开时清理）。"""
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    async def emit(self, event: SignalChangeEvent) -> None:
        """Fanout 给所有 subscriber — 满了丢弃。"""
        if not self._subscribers:
            return
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "[bus] subscriber queue full, dropping event pair=%s tf=%s",
                    event.pair,
                    event.timeframe,
                )


# === singleton pattern (跟 notification_service 一致) ===

def set_signal_bus(bus: SignalChangeBus) -> None:
    """lifespan 注入入口。"""
    global _bus
    _bus = bus


def get_signal_bus() -> SignalChangeBus:
    """消费方获取入口；未初始化时抛 503。"""
    if _bus is None:
        raise RuntimeError("SignalChangeBus not initialized — call set_signal_bus() in lifespan")
    return _bus
