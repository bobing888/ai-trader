"""RecommendationRecorder — WS 1m K 线驱动推荐持久化（spec §4.1 / T8）

stub: 完整实现在 T8 完成。先保证 main.py import 不挂。
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.signal_change_bus import SignalChangeBus

logger = logging.getLogger(__name__)

_recorder: RecommendationRecorder | None = None


class RecommendationRecorder:
    """每分钟持久化所有 (pair, timeframe) 推荐决议。"""

    def __init__(
        self,
        ws_client: Any,
        bus: SignalChangeBus,
        session_factory: Any,
    ) -> None:
        self._ws = ws_client
        self._bus = bus
        self._session = session_factory
        self._running = False
        self._candle_queues: dict[str, Any] = {}
        self._candles_1m: dict[str, Any] = {}

    async def start(self) -> None:
        """启动 WS 订阅 + consume loop（完整实现在 T8）。"""
        if self._running:
            return
        self._running = True
        logger.info("[recorder] stub started — T8 will replace with WS consume loop")

    async def stop(self) -> None:
        self._running = False


def set_recorder(r: RecommendationRecorder) -> None:
    global _recorder
    _recorder = r


def get_recorder() -> RecommendationRecorder:
    if _recorder is None:
        raise RuntimeError("RecommendationRecorder not initialized")
    return _recorder