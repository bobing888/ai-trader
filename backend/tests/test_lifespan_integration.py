"""test_lifespan_integration — TDD: lifespan 启动后 bus + follow_scheduler 已注入

设计：直接调 lifespan 上下文，monkeypatch 替换所有会 hang 的 IO（OKX WS / regime engine）。
"""

import asyncio

import pytest


@pytest.fixture(autouse=True)
def _patch_external_io(monkeypatch):
    """所有 lifespan 内的真实网络 IO 旁路。"""
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

    async def _engine_start_noop(self):
        return None

    async def _engine_stop_noop(self):
        return None

    monkeypatch.setattr(rse.RegimeShiftEngine, "start", _engine_start_noop)
    monkeypatch.setattr(rse.RegimeShiftEngine, "stop", _engine_stop_noop)


def test_lifespan_initializes_signal_change_bus():
    """lifespan 启动后 get_signal_bus() 应可用。"""
    from fastapi import FastAPI

    from app.main import lifespan
    from app.services.signal_change_bus import get_signal_bus

    app = FastAPI()

    async def run():
        async with lifespan(app):
            return get_signal_bus()

    bus = asyncio.run(run())
    assert bus is not None


def test_lifespan_initializes_follow_scheduler():
    """lifespan 启动后 get_follow_scheduler() 应可用。"""
    from fastapi import FastAPI

    from app.main import lifespan
    from app.services.follow_scheduler import get_follow_scheduler

    app = FastAPI()

    async def run():
        async with lifespan(app):
            return get_follow_scheduler()

    scheduler = asyncio.run(run())
    assert scheduler is not None
