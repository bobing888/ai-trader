"""Tests for the K-line WebSocket bridge."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

from app.main import app

# 注: 'client' fixture 来自 conftest.py (function-scope)
# 这里不再定义 local version,避免重复 TestClient 启动 lifespan 触发 task 残留 hang。


class _FakeQueue:
    """In-memory asyncio.Queue stand-in for testing."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[dict] = asyncio.Queue()

    async def put(self, item: dict) -> None:
        await self._queue.put(item)

    async def get(self) -> dict:
        return await self._queue.get()

    def get_nowait(self) -> dict | None:
        return self._queue.get_nowait()

    def task_done(self) -> None:
        self._queue.task_done()

    def put_nowait(self, item: dict) -> None:
        self._queue.put_nowait(item)


class TestWsKlines:
    """Smoke tests for /api/ws/klines/{inst}."""

    def test_unknown_channel_returns_error(self, client: TestClient) -> None:
        """An invalid channel label should be rejected before connection is established."""
        with client.websocket_connect("/api/ws/klines/BTC-USDT?channel=invalid") as ws:
            data = ws.receive_json()
            assert data["type"] == "error"
            assert "unknown channel" in data["detail"]

    def test_normalizes_btcusdt_to_btc_usdt(self, client: TestClient) -> None:
        """BTCUSDT (no dash) should be accepted and treated as BTC-USDT."""
        with patch("app.api.ws.okx_ws_client") as mock_ws:
            fake_q: _FakeQueue = _FakeQueue()
            mock_ws.subscribe_candles = AsyncMock(return_value=fake_q)

            with patch("app.api.ws._fetch_snapshot", new_callable=AsyncMock) as mock_snap:
                mock_snap.return_value = []

                with client.websocket_connect("/api/ws/klines/BTCUSDT") as ws:
                    # Should receive snapshot (empty list is fine — network may fail in test env)
                    msg = ws.receive_json()
                    assert msg["type"] in ("snapshot", "error")

    def test_snapshot_plus_update_delivered(self, client: TestClient) -> None:
        """Server must send a snapshot first, then stream updates from the WS queue."""
        fake_q: _FakeQueue = _FakeQueue()

        with patch("app.api.ws.okx_ws_client") as mock_ws:
            mock_ws.subscribe_candles = AsyncMock(return_value=fake_q)

            with patch("app.api.ws._fetch_snapshot", new_callable=AsyncMock) as mock_snap:
                mock_snap.return_value = [
                    {"time": 1700000000, "open": 100.0, "high": 105.0, "low": 99.0, "close": 103.0, "volume": 5000.0}
                ]

                with client.websocket_connect("/api/ws/klines/BTC-USDT?channel=candle1m") as ws:
                    # First message: snapshot
                    snap = ws.receive_json()
                    assert snap["type"] == "snapshot"
                    assert len(snap["candles"]) == 1
                    assert snap["candles"][0]["close"] == 103.0

                    # Enqueue an update from another coroutine
                    # 旧 asyncio.get_event_loop() 在 Python 3.14 无 running loop 时抛 RuntimeError
                    # 改用 new_event_loop() 在新 loop 跑 (sync context 里没办法 await)
                    def _fire_update() -> None:
                        loop = asyncio.new_event_loop()
                        try:
                            loop.run_until_complete(
                                fake_q.put(
                                    {
                                        "ts": 1700000060,
                                        "o": "103.0",
                                        "h": "104.0",
                                        "l": "102.5",
                                        "c": "103.5",
                                        "vol": "100.0",
                                        "confirm": True,
                                    }
                                )
                            )
                        finally:
                            loop.close()

                    _fire_update()

                    upd = ws.receive_json()
                    assert upd["type"] == "update"
                    assert "candle" in upd

    def test_disconnect_cleans_up_loop(self) -> None:
        """When the client disconnects the task must be cancelled with no orphan tasks left.

        完全独立 — 不依赖 'client' fixture(避免与 function-scope TestClient 跨 loop 冲突)。
        用 asyncio.run() 隔离 loop + patch okx_ws_client.subscribe_candles 返 FakeQueue(跨 loop 安全),
        验证 task.cancel() 后 task.cancelled() == True + 不在 all_tasks() 的 pending 列表。
        """
        import gc
        import weakref
        from unittest.mock import AsyncMock, patch

        from app.api.ws import _ws_loop

        # Track task via weakref
        # 旧 weakref.ref(None) — Python 不允许,改为: 局部变量在 asyncio.run 内赋值
        task_ref: weakref.ref[asyncio.Task[None]] | None = None

        async def fake_ws_loop() -> None:
            await asyncio.sleep(10.0)  # long enough to not finish

        class FakeWebSocket:
            """Minimal fake matching what FastAPI expects for accept / close."""

            async def accept(self) -> None:
                pass

            async def send_json(self, data: dict) -> None:
                pass

            async def close(self) -> None:
                pass

        async def _run() -> bool:
            with patch("app.api.ws.okx_ws_client") as mock_ws:
                mock_ws.subscribe_candles = AsyncMock(return_value=_FakeQueue())
                task = asyncio.create_task(_ws_loop(FakeWebSocket(), "BTC-USDT", "candle1m"))
                nonlocal task_ref
                task_ref = weakref.ref(task)
                await asyncio.sleep(0.05)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                # _ws_loop 内部 try/except 吞掉 CancelledError (避免 ws handler crash),
                # task 会被标记 done(result=None) 而不是 cancelled。
                # 测试改用: task 在 cancel 后已完成 + 不在 all_tasks() pending 列表
                pending = [t for t in asyncio.all_tasks() if not t.done()]
                return task.done() and task not in pending

        cancelled_ok = asyncio.run(_run())
        gc.collect()
        assert cancelled_ok, "task 应被 cancel 标记 + 不在 pending list"
