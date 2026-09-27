"""OKX V5 Public WebSocket Client — 无需 API key，仅限公开行情 channel。"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

import websockets

if TYPE_CHECKING:
    from websockets import Connection as WsConnection

logger = logging.getLogger(__name__)

# OKX V5 public WebSocket endpoint
WS_URL = "wss://ws.okx.com:8443/ws/v5/public"

# KBKKK 监控默认币种（不在 settings 中硬编码，直接用）
DEFAULT_PAIRS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "DOGE-USDT"]

HEARTBEAT_INTERVAL = 25  # 秒，OKX 要求 30s 内有操作则自动 ping
MAX_RECONNECT_DELAY = 30  # 最大重连退避秒数


class WsState(Enum):
    DOWN = "down"
    CONNECTING = "connecting"
    CONNECTED = "connected"


@dataclass
class _Subscription:
    """跟踪一个订阅的信息。"""
    channel: str
    inst_id: str
    queue: asyncio.Queue[dict[str, Any]] = field(default_factory=asyncio.Queue)


class OkxWsClient:
    """OKX V5 公开 WebSocket 客户端，支持多 channel 复用一个长连接。

    公开方法
    --------
    start() -> None
        连接 OKX ws 并自动订阅默认 5 币种的 candle1m + tickers channel。
    stop() -> None
        关闭连接并停止所有后台任务。
    subscribe_candles(inst: str, channel="candle1m") -> asyncio.Queue
        订阅 K 线，返回只读队列，推送 {ts, o, h, l, c, vol, confirm} dict。
    subscribe_tickers(inst: str) -> asyncio.Queue
        订阅 ticker，返回只读队列，推送 {inst, last, open24h, ts} dict。
    """

    def __init__(self) -> None:
        self._conn: WsConnection | None = None
        self._recv_task: asyncio.Task[Any] | None = None
        self._ping_task: asyncio.Task[Any] | None = None
        self._running = False
        self._lock = asyncio.Lock()

        # 重连参数
        self._retry_count = 0

        # {(inst_id, channel): _Subscription}
        self._subs: dict[tuple[str, str], _Subscription] = {}

        # 当前 ws 连接状态
        self._state: WsState = WsState.DOWN

    # ------------------------------------------------------------------
    # 公开属性
    # ------------------------------------------------------------------
    @property
    def state(self) -> WsState:
        return self._state

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    async def start(self) -> None:
        """启动 ws 连接（幂等，可多次调用）。"""
        if self._running:
            return
        self._running = True
        self._retry_count = 0
        await self._connect_and_subscribe()

    async def stop(self) -> None:
        """优雅关闭。"""
        self._running = False
        if self._ping_task:
            self._ping_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._ping_task
            self._ping_task = None
        if self._recv_task:
            self._recv_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._recv_task
            self._recv_task = None
        if self._conn:
            with suppress(Exception):
                await self._conn.close()
            self._conn = None
        self._state = WsState.DOWN

    # ------------------------------------------------------------------
    # 公开订阅 API
    # ------------------------------------------------------------------
    async def subscribe_candles(self, inst: str, channel: str = "candle1m") -> asyncio.Queue[dict[str, Any]]:
        """订阅 K 线，返回推送队列。

        channel 支持: candle1m / candle5m / candle15m / candle1H / candle4H / candle1D。
        """
        key = (inst, channel)
        async with self._lock:
            if key in self._subs:
                sub = self._subs[key]
            else:
                sub = _Subscription(channel=channel, inst_id=inst)
                self._subs[key] = sub
                if self._conn is not None and getattr(self._conn, "close_code", None) is None:
                    await self._send_subscribe([{"channel": channel, "instId": inst}])
        return sub.queue

    async def subscribe_tickers(self, inst: str) -> asyncio.Queue[dict[str, Any]]:
        """订阅 ticker，返回推送队列。推送 {inst, last, open24h, ts}。"""
        channel = "tickers"
        key = (inst, channel)
        async with self._lock:
            if key in self._subs:
                sub = self._subs[key]
            else:
                sub = _Subscription(channel=channel, inst_id=inst)
                self._subs[key] = sub
                if self._conn is not None and getattr(self._conn, "close_code", None) is None:
                    await self._send_subscribe([{"channel": channel, "instId": inst}])
        return sub.queue

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    async def _connect_and_subscribe(self) -> None:
        """建立连接 + 重连循环。"""
        while self._running:
            self._state = WsState.CONNECTING
            try:
                logger.info("[OKX WS] connecting to %s …", WS_URL)
                self._conn = await websockets.connect(WS_URL, ping_interval=None)
                self._state = WsState.CONNECTED
                self._retry_count = 0
                logger.info("[OKX WS] connected")
                self._ping_task = asyncio.create_task(self._ping_loop())

                # 重连后恢复所有已有订阅
                args = [
                    {"channel": sub.channel, "instId": sub.inst_id}
                    for sub in self._subs.values()
                ]
                if args:
                    await self._send_subscribe(args)

                # 启动接收循环（会阻塞直到连接断开）
                self._recv_task = asyncio.create_task(self._recv_loop())
                await self._recv_task

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("[OKX WS] connection error: %s", exc)
                self._state = WsState.DOWN
                if not self._running:
                    break
                # 指数退避
                delay = min(2**self._retry_count, MAX_RECONNECT_DELAY)
                self._retry_count += 1
                logger.info("[OKX WS] retry in %ds (attempt %d)", delay, self._retry_count)
                await asyncio.sleep(delay)

    async def _recv_loop(self) -> None:
        """持续接收并分发消息。"""
        try:
            async for raw in self._conn:  # type: ignore[union-attr]
                await self._dispatch(raw)
        except websockets.ConnectionClosed:
            logger.warning("[OKX WS] server closed connection")

    async def _dispatch(self, raw: str | bytes) -> None:
        """解析并分发单条消息。"""
        try:
            msg = json.loads(raw) if isinstance(raw, bytes) else json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("[OKX WS] failed to decode: %r", raw)
            return

        # 订阅确认帧（op == "subscribe" 的响应）忽略
        op = msg.get("op", "")
        if op == "subscribe":
            logger.debug("[OKX WS] sub confirm: %s", msg)
            return

        # 推送数据帧
        arg = msg.get("arg", {})
        channel = arg.get("channel", "")
        data_list = msg.get("data", [])
        for item in data_list:
            queue = self._find_queue(arg.get("instId", ""), channel)
            if queue is None:
                continue
            parsed = self._parse(channel, item)
            if parsed is not None:
                await queue.put(parsed)

    def _find_queue(self, inst_id: str, channel: str) -> asyncio.Queue[dict[str, Any]] | None:
        key = (inst_id, channel)
        sub = self._subs.get(key)
        return sub.queue if sub else None

    def _parse(self, channel: str, item: list[Any]) -> dict[str, Any] | None:
        """将 OKX ws data 字段解析为 dict。

        OKX V5 candle data 格式:
          [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm, seqId]
        OKX V5 tickers data 格式:
          [instId, last, lastSz, askPx, askSz, bidPx, bidSz, open24h, high24h, low24h,
           sodUtc0, sodUtc8, utcTime, volCcy24h, vol24h, ts]
        """
        if not item or not isinstance(item, list):
            return None
        try:
            if channel.startswith("candle"):
                ts_str = str(item[0])
                try:
                    ts = int(ts_str) * 1_000_000
                except ValueError:
                    ts = 0
                return {
                    "ts": ts,
                    "o": item[1],
                    "h": item[2],
                    "l": item[3],
                    "c": item[4],
                    "vol": item[5],
                    "confirm": item[8] if len(item) > 8 else True,
                }
            if channel == "tickers":
                return {
                    "inst": item[0],
                    "last": item[1],
                    "open24h": item[7] if len(item) > 7 else None,
                    "ts": item[15] if len(item) > 15 else 0,
                }
        except (IndexError, ValueError) as exc:
            logger.warning("[OKX WS] parse error (%s): %s — %s", channel, item, exc)
        return None

    async def _send_subscribe(self, args: list[dict[str, str]]) -> None:
        """发送订阅帧。"""
        frame: dict[str, Any] = {"op": "subscribe", "args": args}
        await self._conn.send(json.dumps(frame))  # type: ignore[union-attr]
        logger.info("[OKX WS] subscribed: %s", args)

    async def _ping_loop(self) -> None:
        """每 HEARTBEAT_INTERVAL 秒发一次 ping。"""
        while self._running:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            if self._conn is not None and getattr(self._conn, "close_code", None) is None:
                try:
                    await self._conn.send(json.dumps({"op": "ping"}))
                    logger.debug("[OKX WS] ping sent")
                except Exception as exc:
                    logger.warning("[OKX WS] ping failed: %s", exc)


# ----------------------------------------------------------------------
# 模块级单例
# ----------------------------------------------------------------------
okx_ws_client = OkxWsClient()
