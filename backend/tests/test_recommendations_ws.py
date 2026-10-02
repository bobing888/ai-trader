"""test_recommendations_ws — TDD: WS 推送 SignalChangeBus 事件"""

import os
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("AI_TRADER_STRATEGIES_DB_PATH", "/tmp/test_recs_ws.db")

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _patch_external_io(monkeypatch):
    from app.data import binance_client, okx_client
    from app.data import okx_ws as _okx_ws_mod

    async def _noop():
        return None

    monkeypatch.setattr(binance_client, "init", _noop)
    monkeypatch.setattr(binance_client, "close", _noop)
    monkeypatch.setattr(okx_client, "init", _noop)
    monkeypatch.setattr(okx_client, "close", _noop)
    monkeypatch.setattr(_okx_ws_mod.okx_ws_client, "start", _noop)
    monkeypatch.setattr(_okx_ws_mod.okx_ws_client, "stop", _noop)

    from app.services import regime_shift_engine as rse

    async def _e(self):
        return None

    monkeypatch.setattr(rse.RegimeShiftEngine, "start", _e)
    monkeypatch.setattr(rse.RegimeShiftEngine, "stop", _e)


def test_ws_connection_accepted():
    """ws endpoint 应 accept connection 不立即断开。"""
    with TestClient(app) as client:
        with client.websocket_connect("/api/recommendations/ws") as ws:
            # 连接建立即可 — 后续 emit 才会推送
            pass


def test_ws_receives_signal_change():
    """WS 连接建立后 emit 事件 → 客户端收到 signal_change 消息。

    注: TestClient + 同一线程内 asyncio.run + websocket_connect 共享 portal,emit 在 connect 后才能推到该 subscriber。
    """
    import asyncio
    import threading

    from app.services.signal_change_bus import SignalChangeEvent, get_signal_bus

    with TestClient(app) as client:
        bus = get_signal_bus()
        curr = MagicMock()
        curr.id = 42
        curr.scanned_at = datetime.now(UTC)

        # 在 connect 之外预订阅,emit;在 connect 内通过 sub 接收
        # 但 TestClient.websocket_connect 内部 loop,emit 必须在主线程串行
        # 用一个简单的 race — connect 前放 event 不会到 ws (还没订阅)
        # 改为 connect 后立即 emit:
        with client.websocket_connect("/api/recommendations/ws") as ws:
            # emit 在另一线程(线程内部 loop 跑后,推到同一 bus queue)
            result_holder = []

            def emit_in_thread():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(bus.emit(SignalChangeEvent(
                        pair="BTC-USDT",
                        timeframe="1h",
                        previous=None,
                        current=curr,
                        change_type="direction",
                    )))
                    loop.close()

            t = threading.Thread(target=emit_in_thread)
            t.start()
            t.join(timeout=2)

            msg = ws.receive_json()
            assert msg["type"] == "signal_change"
            assert msg["pair"] == "BTC-USDT"
            assert msg["change_type"] == "direction"