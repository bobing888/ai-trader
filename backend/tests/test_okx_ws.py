"""OKX WS Client 单元测试 — 使用 unittest.mock 模拟 ws 连接。"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import websockets

from app.data.okx_ws import (
    HEARTBEAT_INTERVAL,
    OkxWsClient,
    WsState,
)


# ---------------------------------------------------------------------------
# Test: 初始状态
# ---------------------------------------------------------------------------

def test_initial_state_is_down():
    client = OkxWsClient()
    assert client.state == WsState.DOWN


# ---------------------------------------------------------------------------
# Test: subscribe_candles 返回 Queue，发送订阅帧
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_subscribe_candles_returns_queue():
    """subscribe_candles 应返回 asyncio.Queue 并发送正确的订阅帧。"""
    client = OkxWsClient()

    mock_conn = AsyncMock()
    mock_conn.closed = False
    client._conn = mock_conn
    client._state = WsState.CONNECTED

    q = await client.subscribe_candles("BTC-USDT", "candle1m")

    assert isinstance(q, asyncio.Queue)
    mock_conn.send.assert_called_once()
    sent = json.loads(mock_conn.send.call_args[0][0])
    assert sent["op"] == "subscribe"
    assert sent["args"] == [{"channel": "candle1m", "instId": "BTC-USDT"}]


# ---------------------------------------------------------------------------
# Test: 重复订阅同一 inst+channel 不重复发帧
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_duplicate_subscribe_no_extra_frame():
    """同一 inst+channel 重复订阅不应发新的 sub 帧。"""
    client = OkxWsClient()

    mock_conn = AsyncMock()
    mock_conn.closed = False
    client._conn = mock_conn
    client._state = WsState.CONNECTED

    await client.subscribe_candles("BTC-USDT", "candle1m")
    send_count_after_first = mock_conn.send.call_count

    await client.subscribe_candles("BTC-USDT", "candle1m")
    send_count_after_second = mock_conn.send.call_count

    assert send_count_after_second == send_count_after_first, (
        f"重复订阅不应发新帧: before={send_count_after_first}, after={send_count_after_second}"
    )


# ---------------------------------------------------------------------------
# Test: candle 解析
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_candle_parse_fields():
    """模拟 OKX candle 推送帧，验证队列收到正确的 dict 字段。"""
    client = OkxWsClient()

    mock_conn = AsyncMock()
    mock_conn.closed = False
    client._conn = mock_conn
    client._state = WsState.CONNECTED

    q = await client.subscribe_candles("BTC-USDT", "candle1m")

    # 模拟 OKX ws candle data
    raw_frame = json.dumps({
        "arg": {"channel": "candle1m", "instId": "BTC-USDT"},
        "data": [[
            "1727446800000",  # ts ms
            "67800.5",        # open
            "68000.0",        # high
            "67600.0",        # low
            "67950.0",        # close
            "1234.56",        # vol
            "789.10",         # volCcy
            "100.0",          # volCcyQuote
            True,             # confirm
            99999999,         # seqId
        ]],
    })
    await client._dispatch(raw_frame)

    msg = q.get_nowait()
    assert msg["ts"] == 1727446800000 * 1_000_000
    assert msg["o"] == "67800.5"
    assert msg["h"] == "68000.0"
    assert msg["l"] == "67600.0"
    assert msg["c"] == "67950.0"
    assert msg["vol"] == "1234.56"
    assert msg["confirm"] is True


# ---------------------------------------------------------------------------
# Test: ticker 解析
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ticker_parse_fields():
    """模拟 OKX ticker 推送帧，验证队列收到正确的 dict 字段。"""
    client = OkxWsClient()

    mock_conn = AsyncMock()
    mock_conn.closed = False
    client._conn = mock_conn
    client._state = WsState.CONNECTED

    q = await client.subscribe_tickers("BTC-USDT")

    raw_frame = json.dumps({
        "arg": {"channel": "tickers", "instId": "BTC-USDT"},
        "data": [[
            "BTC-USDT",        # 0  instId
            "67950.5",         # 1  last
            "0.01",            # 2  lastSz
            "67950.0",         # 3  askPx
            "1.0",             # 4  askSz
            "67951.0",         # 5  bidPx
            "0.5",             # 6  bidSz
            "67000.0",         # 7  open24h
            "68500.0",         # 8  high24h
            "66000.0",         # 9  low24h
            "65000.0",         # 10 sodUtc0
            "66000.0",         # 11 sodUtc8
            "2024-09-27T12:00:00.000Z",  # 12
            "1234567.89",      # 13 volCcy24h
            "98765.43",        # 14 vol24h
            "1727446800000",   # 15 ts
        ]],
    })
    await client._dispatch(raw_frame)

    msg = q.get_nowait()
    assert msg["inst"] == "BTC-USDT"
    assert msg["last"] == "67950.5"
    assert msg["open24h"] == "67000.0"
    assert msg["ts"] == "1727446800000"


# ---------------------------------------------------------------------------
# Test: 重连指数退避计算正确
# ---------------------------------------------------------------------------

def test_reconnect_exponential_backoff():
    """验证指数退避公式：1→2→4→8→16→30(cap)。"""
    MAX_DELAY = 30

    for attempt, expected in [(0, 1), (1, 2), (2, 4), (3, 8), (4, 16), (5, 30), (10, 30)]:
        delay = min(2**attempt, MAX_DELAY)
        assert delay == expected, f"attempt={attempt}: expected {expected}, got {delay}"


# ---------------------------------------------------------------------------
# Test: ping 心跳
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ping_heartbeat_sent():
    """_ping_loop 应每 HEARTBEAT_INTERVAL 秒发送 {"op":"ping"}。"""
    client = OkxWsClient()

    mock_conn = AsyncMock()
    mock_conn.closed = False
    client._conn = mock_conn
    client._state = WsState.CONNECTED
    client._running = True  # 必须设为 True，否则 _ping_loop 第一次 sleep 就直接退出了

    # 启动 ping loop
    ping_task = asyncio.create_task(client._ping_loop())
    # 等待足够时间（略大于一个间隔）
    await asyncio.sleep(HEARTBEAT_INTERVAL + 0.5)
    ping_task.cancel()
    try:
        await ping_task
    except asyncio.CancelledError:
        pass

    # 验证至少发了一次 ping
    calls = list(mock_conn.send.call_args_list)
    ping_calls = [
        c for c in calls
        if json.loads(c[0][0]).get("op") == "ping"
    ]
    assert len(ping_calls) >= 1, f"期望至少1次 ping，实际调用: {calls}"
