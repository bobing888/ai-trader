"""/api/recommendations/ws — WebSocket 推送 SignalChangeBus 事件（spec §5.2）

客户端连接后,任何 SignalChangeEvent 都会通过这个 endpoint 推送。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.signal_change_bus import get_signal_bus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.websocket("/ws")
async def recommendations_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    bus = get_signal_bus()
    queue = bus.subscribe()
    try:
        while True:
            event = await queue.get()
            try:
                await websocket.send_json({
                    "type": "signal_change",
                    "pair": event.pair,
                    "timeframe": event.timeframe,
                    "change_type": event.change_type,
                    "current_id": event.current.id if event.current else None,
                    "scanned_at": event.current.scanned_at.isoformat() if event.current else None,
                })
            except Exception as exc:
                logger.warning("[recs_ws] send failed: %s", exc)
                break
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(queue)
