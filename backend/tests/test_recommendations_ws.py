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

    # 隔离 DB:避免 _send_initial_snapshot 在测试期去查空 production DB
    # 注入一个返回空 list 的 SessionLocal → snapshot 立即走完 → 落到 queue.get()
    class _FakeResult:
        def scalars(self):
            class _Scalars:
                def all(self_inner):
                    return []
            return _Scalars()

    class _FakeSession:
        def execute(self, *a, **kw):
            return _FakeResult()
        def close(self):
            pass

    def _fake_session_local():
        return _FakeSession()

    from app.db import session as _db_mod

    monkeypatch.setattr(_db_mod, "SessionLocal", _fake_session_local)


def test_ws_connection_accepted():
    """ws endpoint 应 accept connection 不立即断开。"""
    with TestClient(app) as client, client.websocket_connect("/api/recommendations/ws") as ws:
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
        # 用一个最小可 JSON 序列化的 stub rec（MagicMock 默认任意属性返 MagicMock → json 序列化失败 → send 抛错）
        # 协议层测试只需 verify emit→receive 流转,字段详细 shape 由 serializer 单测覆盖
        class _StubRec:
            id = 42
            scanned_at = datetime.now(UTC)
            pair = "BTC-USDT"
            timeframe = "1h"
            has_signal = True
            direction = "long"
            confidence = 0.8
            regime = "bull"
            regime_confidence = 0.6
            contributing_strategies = "[]"
            reasons = "[]"
            suggested_leverage = 1
            min_agreement_used = 2
            fast_path = False
            outcome = None
            source = "test"
            calibrated_confidence = None
            net_pnl_estimate = None
            entry_levels_json = None
            stop_loss_price = None
            take_profit_1_price = None
            take_profit_2_price = None
            atr = None
            risk_reward_ratio = None
            current_price = None
            quality = "medium"
            quality_reasons_json = None
        curr = _StubRec()

        # 在 connect 之外预订阅,emit;在 connect 内通过 sub 接收
        # 但 TestClient.websocket_connect 内部 loop,emit 必须在主线程串行
        # 用一个简单的 race — connect 前放 event 不会到 ws (还没订阅)
        # 改为 connect 后立即 emit:
        with client.websocket_connect("/api/recommendations/ws") as ws:
            # emit 在另一线程(线程内部 loop 跑后,推到同一 bus queue)
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
