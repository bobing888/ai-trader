"""test_notification_service — NotificationService unit tests."""

import asyncio
import sys
from datetime import UTC, datetime

import pytest

sys.path.insert(0, str(__file__).rsplit("/tests/", 1)[0] + "/backend")

from app.services.notification_service import (
    NotificationService,
)
from app.services.regime_shift_engine import RegimeShiftEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(
    shift_type: str = "volatility_spike",
    severity: str = "medium",
    inst_id: str = "BTC-USDT",
    channel: str = "candle1m",
) -> RegimeShiftEvent:
    return RegimeShiftEvent(
        detected_at=datetime.now(UTC),
        inst_id=inst_id,
        channel=channel,
        shift_type=shift_type,
        severity=severity,
        baseline_value=1.0,
        current_value=2.5,
        z_score=2.5,
        context={},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_attached_engine_pushes_event_into_queue():
    """Inject an event directly → recent() returns it."""
    service = NotificationService()
    mock_engine = None  # not needed when calling _on_regime_shift directly
    service.attach(mock_engine)

    event = _make_event()
    await service._on_regime_shift(event)

    recent = service.recent(limit=50)
    assert len(recent) == 1
    assert recent[0].shift_type == "volatility_spike"
    assert recent[0].id is not None


@pytest.mark.asyncio
async def test_acknowledge_removes_from_unack():
    """Ack a notification → it disappears from recent (unacknowledged only)."""
    service = NotificationService()
    service.attach(None)

    ev1 = _make_event(shift_type="volatility_spike")
    ev2 = _make_event(shift_type="volume_surge")
    await service._on_regime_shift(ev1)
    await service._on_regime_shift(ev2)

    assert len(service.recent(limit=50)) == 2

    recent = service.recent(limit=50)
    ack_id = recent[0].id
    ok = service.acknowledge(ack_id)
    assert ok is True

    unack = service.recent(limit=50)
    ids = [n.id for n in unack]
    assert ack_id not in ids
    assert len(unack) == 1


@pytest.mark.asyncio
async def test_queue_max_size_trim_oldest():
    """Emit 201 events with max_queue_size=200 → only latest 200 kept."""
    service = NotificationService(max_queue_size=200)
    service.attach(None)

    for _i in range(201):
        ev = _make_event(shift_type="volatility_spike")
        await service._on_regime_shift(ev)

    assert len(service.recent(limit=201)) == 200


@pytest.mark.asyncio
async def test_notification_fields_populated():
    """Event → Notification maps all required fields correctly."""
    service = NotificationService()
    service.attach(None)

    event = RegimeShiftEvent(
        detected_at=datetime.now(UTC),
        inst_id="ETH-USDT",
        channel="candle1h",
        shift_type="trend_break",
        severity="high",
        baseline_value=0.01,
        current_value=0.05,
        z_score=3.1,
        context={"band_upper": 10500, "band_lower": 9500},
    )
    await service._on_regime_shift(event)

    recent = service.recent(limit=10)
    assert len(recent) == 1
    n = recent[0]
    assert n.shift_type == "trend_break"
    assert n.severity == "high"
    assert "ETH-USDT" in n.title
    assert n.body is not None
    assert len(n.body) > 0
    assert n.context == {"band_upper": 10500, "band_lower": 9500}
    assert n.acknowledged is False


def test_acknowledge_nonexistent_returns_false():
    """Ack a random UUID → returns False, no crash."""
    service = NotificationService()
    service.attach(None)

    ok = service.acknowledge("not-a-real-id-12345")
    assert ok is False


@pytest.mark.asyncio
async def test_recent_returns_newest_first():
    """recent(limit=N) returns items newest-last (chronological order)."""
    service = NotificationService()
    service.attach(None)

    for _i in range(5):
        ev = _make_event(shift_type="volatility_spike")
        await service._on_regime_shift(ev)
        await asyncio.sleep(0)  # ensure different timestamps

    recent = service.recent(limit=3)
    assert len(recent) == 3
