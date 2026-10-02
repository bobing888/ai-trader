"""test_signal_change_bus — TDD: SignalChangeBus 进程内 pub/sub"""

import asyncio

import pytest

from app.services.signal_change_bus import SignalChangeBus, SignalChangeEvent


def _make_event(pair="BTC-USDT", change_type="direction"):
    return SignalChangeEvent(
        pair=pair,
        timeframe="1h",
        previous=None,
        current=None,  # type: ignore[arg-type]
        change_type=change_type,
    )


@pytest.mark.asyncio
async def test_bus_emit_and_subscribe():
    bus = SignalChangeBus()
    q = bus.subscribe()
    await bus.emit(_make_event())
    received = await asyncio.wait_for(q.get(), timeout=1.0)
    assert received.pair == "BTC-USDT"
    assert received.change_type == "direction"


@pytest.mark.asyncio
async def test_bus_multiple_subscribers_each_get_event():
    bus = SignalChangeBus()
    q1 = bus.subscribe()
    q2 = bus.subscribe()
    await bus.emit(_make_event(pair="ETH-USDT"))
    r1 = await asyncio.wait_for(q1.get(), timeout=1.0)
    r2 = await asyncio.wait_for(q2.get(), timeout=1.0)
    assert r1.pair == "ETH-USDT"
    assert r2.pair == "ETH-USDT"


@pytest.mark.asyncio
async def test_bus_full_queue_drops_not_raises():
    """灌满 1024 个 → 第 1025 个不报错（log warning + 丢弃）。"""
    bus = SignalChangeBus()
    _ = bus.subscribe()  # maxsize=1024
    for i in range(1025):
        # 不应抛异常
        await bus.emit(_make_event(pair=f"X{i}"))


@pytest.mark.asyncio
async def test_bus_no_subscribers_is_noop():
    """无 subscriber 时 emit 不崩。"""
    bus = SignalChangeBus()
    await bus.emit(_make_event())  # should be silent no-op
    # pass = no exception


@pytest.mark.asyncio
async def test_bus_subscriber_queue_count():
    """多次 subscribe 返回独立 queue。"""
    bus = SignalChangeBus()
    q1 = bus.subscribe()
    q2 = bus.subscribe()
    assert q1 is not q2
    assert len(bus._subscribers) == 2  # type: ignore[attr-defined]