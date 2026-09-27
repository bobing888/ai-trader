"""test_regime_shift_engine — RegimeShiftEngine unit tests.

Tests are self-contained: they directly call _on_candle_1m / _on_candle_1h
handlers (synchronous) without needing the full WS dispatch loop.
"""

import sys
from collections import deque
from datetime import datetime

sys.path.insert(0, str(__file__).rsplit("/tests/", 1)[0] + "/backend")

from app.services.regime_shift_engine import RegimeShiftEngine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candle(
    ts: int,
    o: float,
    h: float,
    lo: float,
    c: float,
    vol: float,
    confirm: bool = True,
) -> dict:
    return {"ts": ts, "o": o, "h": h, "l": lo, "c": c, "vol": vol, "confirm": confirm}


def _close(prices: list[float]) -> list[dict]:
    """Convert a list of close prices into 1m candle dicts (ts auto-incremented)."""
    result = []
    for i, p in enumerate(prices):
        result.append(_make_candle(ts=i * 60_000, o=p, h=p + 1, lo=p - 1, c=p, vol=100))
    return result


# ---------------------------------------------------------------------------
# Volatility Spike
# ---------------------------------------------------------------------------

def test_volatility_spike_detected_when_returns_exceed_2sigma():
    """Feed 420 candles: 419 calm + 1 with 5% spike → volatility_spike emitted."""
    engine = RegimeShiftEngine()

    # 419 flat candles around 10000
    flat_prices = [10000.0 + (i % 5 - 2) * 0.5 for i in range(419)]
    candles = _close(flat_prices)
    for c in candles:
        engine._on_candle_1m({"BTC-USDT": c})

    # 420th: 5% jump — use normal volume so volatility_spike fires without volume_surge
    spike_close = flat_prices[-1] * 1.05
    spike_c = _make_candle(
        ts=419 * 60_000, o=flat_prices[-1], h=spike_close + 5,
        lo=spike_close - 5, c=spike_close, vol=100
    )
    engine._on_candle_1m({"BTC-USDT": spike_c})

    # Collect events from queue
    events = []
    while not engine._queue.empty():
        events.append(engine._queue.get_nowait())

    assert any(e.shift_type == "volatility_spike" for e in events), (
        f"Expected volatility_spike, got: {[e.shift_type for e in events]}"
    )


def test_no_event_when_within_baseline():
    """Feed 420 all-calm candles → no events."""
    engine = RegimeShiftEngine()

    prices = [10000.0 + (i % 7 - 3) * 0.2 for i in range(420)]
    candles = _close(prices)
    for c in candles:
        engine._on_candle_1m({"BTC-USDT": c})

    events = []
    while not engine._queue.empty():
        events.append(engine._queue.get_nowait())

    assert len(events) == 0, f"Expected no events, got: {[e.shift_type for e in events]}"


# ---------------------------------------------------------------------------
# Volume Surge
# ---------------------------------------------------------------------------

def test_volume_surge_detected_when_volume_5x_median():
    """Last candle has 6× median volume → volume_surge emitted."""
    engine = RegimeShiftEngine()

    # 60 candles, all vol=100
    for i in range(60):
        c = _make_candle(ts=i * 60_000, o=5000, h=5001, lo=4999, c=5000 + (i % 3 - 1) * 0.5, vol=100)
        engine._on_candle_1m({"BTC-USDT": c})

    # 61st: 6× median
    surge_c = _make_candle(ts=60 * 60_000, o=5000, h=5002, lo=4998, c=5001, vol=600)
    engine._on_candle_1m({"BTC-USDT": surge_c})

    events = []
    while not engine._queue.empty():
        events.append(engine._queue.get_nowait())

    assert any(e.shift_type == "volume_surge" for e in events), (
        f"Expected volume_surge, got: {[e.shift_type for e in events]}"
    )


def test_volume_surge_not_triggered_when_under_threshold():
    """Last candle has 3× median volume → below 5× threshold, no event."""
    engine = RegimeShiftEngine()

    for i in range(60):
        c = _make_candle(ts=i * 60_000, o=5000, h=5001, lo=4999, c=5000 + (i % 3 - 1) * 0.5, vol=100)
        engine._on_candle_1m({"BTC-USDT": c})

    # 61st: 3× median (below threshold)
    mid_c = _make_candle(ts=60 * 60_000, o=5000, h=5002, lo=4998, c=5001, vol=300)
    engine._on_candle_1m({"BTC-USDT": mid_c})

    events = []
    while not engine._queue.empty():
        events.append(engine._queue.get_nowait())

    assert not any(e.shift_type == "volume_surge" for e in events)


# ---------------------------------------------------------------------------
# Trend Break (1h data)
# ---------------------------------------------------------------------------

def test_trend_break_detected_when_close_exceeds_2sigma_band():
    """20 calm 1h candles + 1 that breaks upper band → trend_break emitted."""
    engine = RegimeShiftEngine()

    # Feed enough 1m data to satisfy the buffer requirement
    for i in range(420):
        engine._on_candle_1m({
            "BTC-USDT": _make_candle(ts=i * 60_000, o=10000, h=10001, lo=9999, c=10000, vol=100),
            "ETH-USDT": _make_candle(ts=i * 60_000, o=2000, h=2001, lo=1999, c=2000, vol=50),
        })

    # 20 calm 1h candles
    price = 10000.0
    for i in range(20):
        c = _make_candle(ts=i * 3_600_000, o=price, h=price + 5, lo=price - 5, c=price, vol=500)
        engine._on_candle_1h({"BTC-USDT": c})
        price += (i % 5 - 2) * 10

    # 21st: breaks upper 2σ band
    closes = [10000.0 + (i % 5 - 2) * 10 for i in range(20)]
    mean = sum(closes) / 20
    std = (sum((x - mean) ** 2 for x in closes) / 20) ** 0.5
    break_price = mean + 2.5 * std
    break_c = _make_candle(ts=20 * 3_600_000, o=price, h=break_price + 10, lo=break_price - 10, c=break_price, vol=500)
    engine._on_candle_1h({"BTC-USDT": break_c})

    events = []
    while not engine._queue.empty():
        events.append(engine._queue.get_nowait())

    assert any(e.shift_type == "trend_break" for e in events), (
        f"Expected trend_break, got: {[e.shift_type for e in events]}"
    )


# ---------------------------------------------------------------------------
# Correlation Breakdown
# ---------------------------------------------------------------------------

def test_correlation_breakdown_when_rolling_corr_drop():
    """Validate that a correlation drop from ≥0.7 to ≤0.2 triggers a correlation_breakdown event.

    We directly patch the engine's BTC and ETH deques to isolate the correlation detection
    logic from the complexities of live candle-feed alignment (dict iteration order,
    BTC-always-leads-ETH issue). The deques contain price series that produce:
      - prev: r = 0.98 (correlated BTC+ETH)
      - curr: r = -0.34 (BTC correlated, ETH flat with tiny noise)
    The detection condition (prev ≥ 0.7 AND curr ≤ 0.2) is satisfied, so an event fires.
    """
    import math

    engine = RegimeShiftEngine()

    # Phase 1: correlated BTC+ETH deques (r = 0.98 after seed)
    seed_btc = [10000.0 * math.exp(0.05 * i + math.sin(i * 0.5)) for i in range(30)]
    seed_eth = [2000.0 * math.exp(0.05 * i + math.sin(i * 0.5)) for i in range(30)]
    engine.seed_for_test(seed_btc, seed_eth, last_corr=0.98)

    # Phase 2: uncorrelated deques (BTC correlated, ETH flat)
    eth_flat = seed_eth[-1]
    phase2_btc = [10000.0 * math.exp(0.05 * i + math.sin(i * 0.5)) for i in range(30, 60)]
    phase2_eth = [eth_flat + eth_flat * 0.000001 * math.sin(i * 7.3) for i in range(30, 60)]

    # Directly patch deques (they contain price values; _eval_correlation_breakdown computes returns)
    engine._btc_closes = deque(phase2_btc, maxlen=30)
    engine._eth_closes = deque(phase2_eth, maxlen=30)
    engine._last_corr = 0.98

    # Trigger the detection
    engine._eval_correlation_breakdown()

    events = []
    while not engine._queue.empty():
        events.append(engine._queue.get_nowait())

    assert any(e.shift_type == "correlation_breakdown" for e in events), (
        f"Expected correlation_breakdown, got: {[e.shift_type for e in events]}"
    )


# ---------------------------------------------------------------------------
# Severity and context
# ---------------------------------------------------------------------------

def test_volatility_spike_event_has_correct_fields():
    """Ensure event carries all required fields with correct types."""
    engine = RegimeShiftEngine()

    flat_prices = [10000.0 + (i % 5 - 2) * 0.5 for i in range(419)]
    candles = _close(flat_prices)
    for c in candles:
        engine._on_candle_1m({"BTC-USDT": c})

    spike_close = flat_prices[-1] * 1.05
    spike_c = _make_candle(ts=419 * 60_000, o=flat_prices[-1], h=spike_close + 5, lo=spike_close - 5, c=spike_close, vol=100)
    engine._on_candle_1m({"BTC-USDT": spike_c})

    events = []
    while not engine._queue.empty():
        events.append(engine._queue.get_nowait())

    spike = next(e for e in events if e.shift_type == "volatility_spike")
    assert spike.inst_id == "BTC-USDT"
    assert spike.channel == "candle1m"
    assert spike.severity in ("low", "medium", "high")
    assert spike.z_score > 0
    assert spike.baseline_value > 0
    assert spike.current_value > spike.baseline_value
    assert isinstance(spike.context, dict)
    assert isinstance(spike.detected_at, datetime)


def test_attach_sets_ws_reference():
    """attach() stores WS references without raising."""
    engine = RegimeShiftEngine()
    mock_ws = object()
    mock_tickers = object()
    engine.attach(mock_ws, mock_tickers)
    assert engine._ws is mock_ws
    assert engine._ticker_ws is mock_tickers
