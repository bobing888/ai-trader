"""Regime Shift Engine — detects 4 types of market regime shifts from live OKX K-line streams.

Types detected
--------------
volatility_spike   — 1m close-to-close volatility exceeds 2× 7-day baseline
volume_surge       — 1m volume exceeds 5× median of past 60 candles
trend_break        — 1h close breaks ±2σ band of past 20 1h closes
correlation_breakdown — BTC vs ETH 1m rolling r from ≥0.7 drops to ≤0.2

Architecture
------------
attach(ws_client, ticker_ws_client) → subscribes candle1m / candle1h channels
  and BTC/USDT + ETH/USDT instruments.
Each new confirmed candle fires _on_candle_1m / _on_candle_1h which populates
rolling deque buffers and runs evaluation.
stream() is an async generator that yields RegimeShiftEvent objects.
start() runs _dispatch_loop() in a background task (fire-and-forget).
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections import deque
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

ShiftTypeLiteral = Literal[
    "volatility_spike", "volume_surge", "trend_break", "correlation_breakdown"
]
SeverityLiteral = Literal["low", "medium", "high"]


@dataclass
class RegimeShiftEvent:
    detected_at: datetime
    inst_id: str
    channel: str
    shift_type: ShiftTypeLiteral
    severity: SeverityLiteral
    baseline_value: float
    current_value: float
    z_score: float
    context: dict[str, Any]


# ---------------------------------------------------------------------------
# Buffer helpers
# ---------------------------------------------------------------------------

def _rolling_std(values: list[float]) -> float:
    """Population std dev of a list of floats."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / n
    return math.sqrt(variance)


def _pearson_r(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation coefficient for two equal-length lists."""
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=False))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)


def _severity(z: float) -> SeverityLiteral:
    if z >= 4.0:
        return "high"
    if z >= 2.5:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

# Buffer sizes
_1M_BUFFER = 420        # 7 hours of 1m candles
_1H_BUFFER = 168        # 7 days of 1h candles
_VOL_WINDOW = 60        # window for volume median
_CORR_WINDOW = 30        # window for rolling correlation

# Thresholds
_VOLATILITY_SPIKE_MULT = 2.0
_VOLUME_SURGE_MULT = 5.0
_TREND_BREAK_SIGMA = 2.0
_CORR_HIGH = 0.7
_CORR_LOW = 0.2
_COOLDOWN_SECONDS = 30  # per shift_type per instrument


@dataclass
class _ShiftCooldown:
    """Tracks last detection time for each (shift_type, inst_id) to enforce cooldown."""
    _last: dict[tuple[str, str], float] = field(default_factory=dict)

    def ok(self, shift_type: str, inst_id: str) -> bool:
        now = datetime.now(UTC).timestamp()
        key = (shift_type, inst_id)
        last = self._last.get(key, 0.0)
        if now - last < _COOLDOWN_SECONDS:
            return False
        self._last[key] = now
        return True


class RegimeShiftEngine:
    """
    Listens to OKX WebSocket K-line streams and emits RegimeShiftEvent
    whenever a regime shift is detected.
    """

    def __init__(self) -> None:
        # K-line buffers: keyed by inst_id
        # Each entry is a dict with "c" (close) and "vol"
        self._buf_1m: dict[str, deque[dict[str, float]]] = {}
        self._buf_1h: dict[str, deque[dict[str, float]]] = {}

        # BTC/ETH 1m close prices for correlation
        self._btc_closes: deque[float] = deque(maxlen=_CORR_WINDOW)
        self._eth_closes: deque[float] = deque(maxlen=_CORR_WINDOW)

        # Track last known correlation for detecting drop
        self._last_corr: float = 0.0

        # Event queue
        self._queue: asyncio.Queue[RegimeShiftEvent] = asyncio.Queue()

        # Cooldown
        self._cooldown = _ShiftCooldown()

        # WS references
        self._ws: Any = None
        self._ticker_ws: Any = None
        self._task: asyncio.Task[None] | None = None
        self._running = False

    def seed_for_test(self, btc_closes: list[float], eth_closes: list[float], last_corr: float = 0.0) -> None:
        """Seed internal deques for unit testing correlation_breakdown.

        This bypasses the normal candle-feed path so tests can directly set the
        correlation state without fighting the BTC-leads-ETH alignment issue.
        """
        self._btc_closes: deque[float] = deque(btc_closes, maxlen=_CORR_WINDOW)
        self._eth_closes: deque[float] = deque(eth_closes, maxlen=_CORR_WINDOW)
        self._last_corr = last_corr

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def attach(self, ws_client: Any, ticker_ws_client: Any) -> None:
        """Subscribe to required OKX channels.

        Caller provides the WS client singleton so this module stays
        WS-agnostic (same interface works for any OKX-compatible client).
        """
        self._ws = ws_client
        self._ticker_ws = ticker_ws_client

    async def start(self) -> None:
        """Start the dispatch loop in a background task (fire-and-forget)."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._dispatch_loop())
        logger.info("[regime_shift] engine started")

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with __import__("contextlib").suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("[regime_shift] engine stopped")

    # ------------------------------------------------------------------
    # Public async generator
    # ------------------------------------------------------------------

    async def stream(self) -> AsyncGenerator[RegimeShiftEvent, None]:
        """Async generator: yields RegimeShiftEvent as they are detected."""
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                yield event
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    # ------------------------------------------------------------------
    # Internal dispatch loop (fires tasks that call _on_candle_*)
    # ------------------------------------------------------------------

    async def _dispatch_loop(self) -> None:
        """Main loop: read from WS queues and dispatch to handlers."""
        if self._ws is None:
            logger.warning("[regime_shift] no WS client attached — attach() first")
            return

        # Subscribe
        pairs = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "DOGE-USDT"]

        # BTC + ETH: need both 1m and 1h for correlation + trend_break
        for pair in pairs:
            await self._ws.subscribe_candles(pair, "candle1m")
        for pair in pairs:
            await self._ws.subscribe_candles(pair, "candle1h")

        # BTC + ETH ticker for correlation (optional — not strictly needed)
        for pair in ["BTC-USDT", "ETH-USDT"]:
            with __import__("contextlib").suppress(Exception):
                await self._ws.subscribe_tickers(pair)

        logger.info("[regime_shift] subscribed to candle streams for %s", pairs)

        # Read from all subscribed queues concurrently
        async def read_1m(pair: str) -> None:
            queue = await self._ws.subscribe_candles(pair, "candle1m")
            while self._running:
                try:
                    candle = await queue.get()
                    if candle.get("confirm", True):
                        self._on_candle_1m({pair: candle})
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.warning("[regime_shift] 1m read error %s: %s", pair, exc)

        async def read_1h(pair: str) -> None:
            queue = await self._ws.subscribe_candles(pair, "candle1h")
            while self._running:
                try:
                    candle = await queue.get()
                    if candle.get("confirm", True):
                        self._on_candle_1h({pair: candle})
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.warning("[regime_shift] 1h read error %s: %s", pair, exc)

        tasks: list[asyncio.Task[None]] = []
        for pair in pairs:
            tasks.append(asyncio.create_task(read_1m(pair)))
        for pair in pairs:
            tasks.append(asyncio.create_task(read_1h(pair)))

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for t in tasks:
                t.cancel()
            with __import__("contextlib").suppress(asyncio.CancelledError):
                await asyncio.gather(*tasks, return_exceptions=True)

    # ------------------------------------------------------------------
    # Candle handlers
    # ------------------------------------------------------------------

    def _on_candle_1m(self, data: dict[str, dict]) -> None:
        """Handle a confirmed 1m candle dict {inst_id: candle_dict}."""
        for inst_id, candle in data.items():
            close = float(candle["c"])
            vol = float(candle["vol"])

            if inst_id not in self._buf_1m:
                self._buf_1m[inst_id] = deque(maxlen=_1M_BUFFER)
            self._buf_1m[inst_id].append({"c": close, "vol": vol})

            # Correlation tracking for BTC / ETH
            if inst_id in ("BTC-USDT", "ETH-USDT"):
                closes = self._btc_closes if inst_id == "BTC-USDT" else self._eth_closes
                closes.append(close)

            # Evaluate volatility spike (needs full 420-candle buffer)
            buf = self._buf_1m[inst_id]
            if len(buf) >= _1M_BUFFER:
                self._eval_volatility_spike(inst_id, buf)

            # Evaluate volume surge (needs 60-candle rolling window)
            if len(buf) >= _VOL_WINDOW:
                self._eval_volume_surge(inst_id, buf)

            # Correlation check: both BTC + ETH deques must have enough data
            # Trigger on BOTH BTC and ETH candles so _last_corr gets updated
            # even when BTC arrives before ETH in a batch.
            if (inst_id in ("BTC-USDT", "ETH-USDT")
                    and len(self._btc_closes) >= _CORR_WINDOW
                    and len(self._eth_closes) >= _CORR_WINDOW):
                self._eval_correlation_breakdown()

    def _on_candle_1h(self, data: dict[str, dict]) -> None:
        """Handle a confirmed 1h candle dict {inst_id: candle_dict}."""
        for inst_id, candle in data.items():
            close = float(candle["c"])

            if inst_id not in self._buf_1h:
                self._buf_1h[inst_id] = deque(maxlen=_1H_BUFFER)
            self._buf_1h[inst_id].append({"c": close})

            buf = self._buf_1h[inst_id]
            if len(buf) >= 20:
                self._eval_trend_break(inst_id, buf)

    # ------------------------------------------------------------------
    # Evaluation functions
    # ------------------------------------------------------------------

    def _eval_volatility_spike(self, inst_id: str, buf: deque[dict[str, float]]) -> None:
        """Emit volatility_spike when 1m return stddev > 2× 7-day baseline."""
        closes = [x["c"] for x in buf]
        returns = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        if len(returns) < _1M_BUFFER - 1:
            return

        # Baseline: full 420-candle window (7 days)
        baseline = _rolling_std(returns)
        if baseline <= 0:
            return

        # Current: last 20 returns
        recent = returns[-20:]
        current_vol = _rolling_std(recent)

        z = current_vol / baseline
        if current_vol > _VOLATILITY_SPIKE_MULT * baseline:
            if not self._cooldown.ok("volatility_spike", inst_id):
                return
            event = RegimeShiftEvent(
                detected_at=datetime.now(UTC),
                inst_id=inst_id,
                channel="candle1m",
                shift_type="volatility_spike",
                severity=_severity(z),
                baseline_value=round(baseline, 6),
                current_value=round(current_vol, 6),
                z_score=round(z, 3),
                context={"recent_std": round(current_vol, 6), "baseline_std": round(baseline, 6)},
            )
            self._queue.put_nowait(event)
            logger.info("[regime_shift] %s volatility_spike z=%.2f", inst_id, z)

    def _eval_volume_surge(self, inst_id: str, buf: deque[dict[str, float]]) -> None:
        """Emit volume_surge when current volume > 5× median of past 60 volumes."""
        vols = [x["vol"] for x in buf]
        if len(vols) < _VOL_WINDOW:
            return

        recent_vols = vols[-_VOL_WINDOW:]
        sorted_vols = sorted(recent_vols)
        mid = len(sorted_vols) // 2
        if len(sorted_vols) % 2 == 0:
            median_vol = (sorted_vols[mid - 1] + sorted_vols[mid]) / 2
        else:
            median_vol = sorted_vols[mid]

        if median_vol <= 0:
            return

        current_vol = vols[-1]
        ratio = current_vol / median_vol
        if ratio >= _VOLUME_SURGE_MULT:
            if not self._cooldown.ok("volume_surge", inst_id):
                return
            event = RegimeShiftEvent(
                detected_at=datetime.now(UTC),
                inst_id=inst_id,
                channel="candle1m",
                shift_type="volume_surge",
                severity=_severity(ratio),
                baseline_value=round(median_vol, 2),
                current_value=round(current_vol, 2),
                z_score=round(ratio, 3),
                context={"median_vol": round(median_vol, 2), "current_vol": round(current_vol, 2)},
            )
            self._queue.put_nowait(event)
            logger.info("[regime_shift] %s volume_surge ratio=%.2f", inst_id, ratio)

    def _eval_trend_break(self, inst_id: str, buf: deque[dict[str, float]]) -> None:
        """Emit trend_break when 1h close breaks ±2σ band of past 20 closes."""
        closes = [x["c"] for x in buf]
        if len(closes) < 20:
            return

        # Use last 20 closes for band
        window = closes[-20:]
        mean = sum(window) / 20
        std = _rolling_std(window)
        if std <= 0:
            return

        current = closes[-1]
        upper = mean + _TREND_BREAK_SIGMA * std
        lower = mean - _TREND_BREAK_SIGMA * std

        if current > upper or current < lower:
            # Direction: high = broke upper band, low = broke lower band
            direction = "high" if current > upper else "low"
            z = abs(current - mean) / std
            if not self._cooldown.ok("trend_break", inst_id):
                return
            event = RegimeShiftEvent(
                detected_at=datetime.now(UTC),
                inst_id=inst_id,
                channel="candle1h",
                shift_type="trend_break",
                severity=_severity(z),
                baseline_value=round(mean, 4),
                current_value=round(current, 4),
                z_score=round(z, 3),
                context={
                    "mean": round(mean, 4),
                    "std": round(std, 4),
                    "upper_band": round(upper, 4),
                    "lower_band": round(lower, 4),
                    "direction": direction,
                },
            )
            self._queue.put_nowait(event)
            logger.info("[regime_shift] %s trend_break %s z=%.2f", inst_id, direction, z)

    def _eval_correlation_breakdown(self) -> None:
        """Emit correlation_breakdown when BTC-ETH 1m rolling r drops from ≥0.7 to ≤0.2."""
        btc_list = list(self._btc_closes)
        eth_list = list(self._eth_closes)

        if len(btc_list) < _CORR_WINDOW or len(eth_list) < _CORR_WINDOW:
            return

        # Compute returns
        btc_returns = [btc_list[i] - btc_list[i - 1] for i in range(1, len(btc_list))]
        eth_returns = [eth_list[i] - eth_list[i - 1] for i in range(1, len(eth_list))]

        # Align lengths
        min_len = min(len(btc_returns), len(eth_returns))
        btc_r = btc_returns[-min_len:]
        eth_r = eth_returns[-min_len:]

        if len(btc_r) <= _CORR_WINDOW - 2:
            return

        # Use last CORR_WINDOW returns
        btc_r = btc_r[-_CORR_WINDOW:]
        eth_r = eth_r[-_CORR_WINDOW:]

        current_corr = _pearson_r(btc_r, eth_r)
        prev_corr = self._last_corr

        # Always update _last_corr so next evaluation has correct baseline
        self._last_corr = current_corr

        # Detect: was ≥0.7, now ≤0.2
        if prev_corr >= _CORR_HIGH and current_corr <= _CORR_LOW:
            if not self._cooldown.ok("correlation_breakdown", "BTC-ETH"):
                return
            event = RegimeShiftEvent(
                detected_at=datetime.now(UTC),
                inst_id="BTC-ETH",
                channel="candle1m",
                shift_type="correlation_breakdown",
                severity=_severity(abs(prev_corr - current_corr) * 2),
                baseline_value=round(prev_corr, 4),
                current_value=round(current_corr, 4),
                z_score=round(abs(prev_corr - current_corr), 4),
                context={
                    "prev_corr": round(prev_corr, 4),
                    "current_corr": round(current_corr, 4),
                    "threshold_high": _CORR_HIGH,
                    "threshold_low": _CORR_LOW,
                },
            )
            self._queue.put_nowait(event)
            logger.info("[regime_shift] correlation_breakdown r: %.4f → %.4f", prev_corr, current_corr)

        self._last_corr = current_corr
