"""Notification Service — in-memory queue backed by regime-shift engine events.

Responsibilities
----------------
- Maintain an in-memory deque of recent Notification objects (max_queue_size).
- Attach to a RegimeShiftEngine and consume its stream().
- Provide recent(limit) and acknowledge(id) for the REST API.
- Auto-build human-readable title + body from a RegimeShiftEvent.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.services.regime_shift_engine import RegimeShiftEvent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic model (exposed to REST API)
# ---------------------------------------------------------------------------

ShiftTypeLiteral = Literal[
    "volatility_spike", "volume_surge", "trend_break", "correlation_breakdown"
]
SeverityLiteral = Literal["low", "medium", "high"]


class Notification(BaseModel):
    id: str
    created_at: datetime
    shift_type: ShiftTypeLiteral
    severity: SeverityLiteral
    title: str
    body: str
    context: dict[str, Any]
    acknowledged: bool = False

    model_config = {"use_enum_values": True}


class RecentNotificationsResponse(BaseModel):
    items: list[Notification]


# ---------------------------------------------------------------------------
# Title / body builders
# ---------------------------------------------------------------------------

_SHIFT_TYPE_LABELS: dict[str, str] = {
    "volatility_spike": "波动率飙升",
    "volume_surge": "成交量暴增",
    "trend_break": "趋势突破",
    "correlation_breakdown": "相关性崩塌",
}

_SEVERITY_LABELS: dict[str, str] = {
    "low": "低",
    "medium": "中",
    "high": "高",
}


def _build_title(event: RegimeShiftEvent) -> str:
    inst = event.inst_id
    label = _SHIFT_TYPE_LABELS.get(event.shift_type, event.shift_type)
    z = f"z={event.z_score:.1f}"
    return f"{inst} {label} ({z})"


def _build_body(event: RegimeShiftEvent) -> str:
    label = _SHIFT_TYPE_LABELS.get(event.shift_type, event.shift_type)
    sev = _SEVERITY_LABELS.get(event.severity, event.severity)
    inst = event.inst_id

    if event.shift_type == "volatility_spike":
        return (
            f"{inst} 1分钟K线波动率飙升至 {event.z_score:.1f}σ，"
            f"超过7日基线 {(event.z_score / 2):.1f} 倍以上，请关注风险。"
        )
    if event.shift_type == "volume_surge":
        return (
            f"{inst} 成交量达过去60根K线中位数的 {event.z_score:.1f} 倍，"
            f"出现异常放量，关注趋势是否持续。"
        )
    if event.shift_type == "trend_break":
        direction = event.context.get("direction", "突破")
        return (
            f"{inst} 1小时收盘价 {direction} 20周期 ±2σ 布林带，"
            f"z={event.z_score:.1f}，趋势可能反转。"
        )
    if event.shift_type == "correlation_breakdown":
        return (
            f"BTC与ETH 1分钟收益率相关性从 {event.context.get('prev_corr', 0):.2f} "
            f"跌至 {event.context.get('current_corr', 0):.2f}，"
            f"市场结构可能发生根本性变化。"
        )
    return f"{inst} 检测到 {label} 信号，severity={sev}，z={event.z_score:.2f}。"


def _event_to_notification(event: RegimeShiftEvent) -> Notification:
    return Notification(
        id=uuid.uuid4().hex,
        created_at=event.detected_at,
        shift_type=event.shift_type,
        severity=event.severity,
        title=_build_title(event),
        body=_build_body(event),
        context=event.context,
        acknowledged=False,
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

@dataclass
class NotificationService:
    """
    In-memory notification queue backed by RegimeShiftEngine stream.

    Usage
    -----
    notification_service = NotificationService()
    notification_service.attach(regime_engine)
    # → a background task starts consuming regime_engine.stream()
    #   and populating the internal deque.

    recent(limit=50)         → list[Notification]  (unacknowledged only)
    acknowledge(id)          → bool
    """
    max_queue_size: int = 200

    # Internal state
    _queue: deque[Notification] = field(default_factory=lambda: deque(maxlen=200))
    _engine: Any = field(default=None, repr=False)
    _consumer_task: asyncio.Task[None] | None = field(default=None, repr=False)
    _loop: asyncio.AbstractEventLoop | None = field(default=None, repr=False)

    def attach(self, regime_engine: Any) -> None:
        """Attach to a RegimeShiftEngine and start background consumer task."""
        self._engine = regime_engine

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Not in async context yet — will start in lifespan
            return

        self._loop = loop
        self._start_consumer()

    def _start_consumer(self) -> None:
        """Start the async consumer that reads from engine.stream()."""
        if self._engine is None or self._loop is None:
            return
        if self._consumer_task is not None:
            return
        self._consumer_task = self._loop.create_task(self._consume())

    async def _on_regime_shift(self, event: RegimeShiftEvent) -> None:
        """Called by consumer to push a new notification into the deque."""
        n = _event_to_notification(event)
        self._queue.append(n)

        # Trim if over max_queue_size (deque maxlen handles this, but be explicit)
        while len(self._queue) > self.max_queue_size:
            self._queue.popleft()

    async def _consume(self) -> None:
        """Background task: reads from engine.stream() and calls _on_regime_shift."""
        if self._engine is None:
            return
        try:
            async for event in self._engine.stream():
                await self._on_regime_shift(event)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("[notification] consumer error: %s", exc)

    # ------------------------------------------------------------------
    # Public sync API (called from FastAPI route handlers)
    # ------------------------------------------------------------------

    def recent(self, limit: int = 50) -> list[Notification]:
        """
        Return the most recent `limit` unacknowledged notifications.
        Ordered newest-first.
        """
        unack = [n for n in self._queue if not n.acknowledged]
        return unack[-limit:] if limit < len(unack) else unack

    def acknowledge(self, notification_id: str) -> bool:
        """
        Mark a notification as acknowledged.
        Returns True if found and updated; False otherwise.
        """
        for n in self._queue:
            if n.id == notification_id:
                n.acknowledged = True
                return True
        return False
