"""WebSocket endpoint — bridges OkxWsClient real-time candles to the browser."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.data.okx_ws import okx_ws_client

logger = logging.getLogger(__name__)
router = APIRouter()

# Channel label → OkxClient interval string
_CHANNEL_MAP: dict[str, str] = {
    "candle1m": "1m",
    "candle5m": "5m",
    "candle15m": "15m",
    "candle1H": "1h",
    "candle4H": "4h",
    "candle1D": "1d",
}

# Which channel to subscribe in the WS client (always candle1m for real-time push)
_WS_CHANNEL = "candle1m"


async def _fetch_snapshot(inst: str, channel: str) -> list[dict[str, Any]]:
    """Pull the last 200 candles from REST as the initial snapshot."""
    try:
        interval = _CHANNEL_MAP.get(channel, "1m")
        from app.data.okx import okx_client

        candles = await okx_client.get_klines(inst, interval=interval, limit=200)
        return candles
    except Exception as exc:
        logger.warning("[ws] failed to fetch snapshot for %s: %s", inst, exc)
        return []


async def _ws_loop(ws: WebSocket, inst: str, channel: str) -> None:
    """Bridge loop: push snapshot then stream updates until disconnect."""
    try:
        queue = await okx_ws_client.subscribe_candles(inst, _WS_CHANNEL)
        logger.info("[ws] subscribed candles for %s", inst)
    except Exception as exc:
        logger.warning("[ws] failed to subscribe %s: %s", inst, exc)
        with suppress(Exception):
            await ws.send_json({"type": "error", "detail": str(exc)})
        with suppress(Exception):
            await ws.close()
        return

    # Send snapshot
    snapshot = await _fetch_snapshot(inst, channel)
    with suppress(Exception):
        await ws.send_json({"type": "snapshot", "candles": snapshot})

    # Stream updates
    try:
        while True:
            candle = await queue.get()
            await ws.send_json({"type": "update", "candle": candle})
    except asyncio.CancelledError:
        logger.debug("[ws] stream cancelled for %s", inst)
    except Exception as exc:
        logger.warning("[ws] stream error for %s: %s", inst, exc)
        with suppress(Exception):
            await ws.send_json({"type": "error", "detail": str(exc)})


@router.websocket("/ws/klines/{inst}")
async def ws_klines(websocket: WebSocket, inst: str, channel: str = "candle1m") -> None:
    """WebSocket bridge for real-time OKX K-line data.

    Protocol
    -------
    Browser → Server:
        {"action": "subscribe"}
        {"action": "set_channel", "channel": "candle1m"}   # optional, default = path param

    Server → Browser:
        {"type": "snapshot", "candles": [...]}  # last 200 bars from REST
        {"type": "update", "candle": {...}}    # real-time push from WS
        {"type": "error", "detail": "..."}     # any error
    """
    await websocket.accept()

    # Normalize inst (uppercase, allow both BTC-USDT and BTCUSDT)
    inst = inst.upper()
    if "-" not in inst and inst.endswith("USDT"):
        base = inst[:-4]
        inst = f"{base}-USDT"

    # Guard unknown channels
    if channel not in _CHANNEL_MAP:
        await websocket.send_json({"type": "error", "detail": f"unknown channel: {channel}"})
        await websocket.close()
        return

    loop_task: asyncio.Task[None] | None = None
    try:
        # Spawn the bridge loop
        loop_task = asyncio.create_task(_ws_loop(websocket, inst, channel))
        # Wait for the loop to finish (disconnect or error)
        await loop_task
    except WebSocketDisconnect:
        logger.info("[ws] client disconnected: %s", inst)
    except Exception as exc:
        logger.exception("[ws] unexpected error for %s: %s", inst, exc)
        with suppress(Exception):
            await websocket.send_json({"type": "error", "detail": str(exc)})
    finally:
        if loop_task is not None and not loop_task.done():
            loop_task.cancel()
            with suppress(asyncio.CancelledError, asyncio.InvalidStateError):
                await loop_task
