"""Tests for aggregator's ATR-based entry levels & quality gate."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from app.signals.aggregator import SignalAggregator
from app.signals.quality_gate import evaluate_signal_quality


def make_candles(n: int, base_price: float = 100.0, vol: float = 1.0) -> list[dict]:
    out = []
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    for i in range(n):
        close = base_price
        out.append(
            {
                "open_time": now + timedelta(hours=i),
                "open": close,
                "high": close + vol,
                "low": close - vol,
                "close": close,
                "volume": 1000.0,
            }
        )
    return out


class TestQualityGate:
    def test_high_quality(self):
        result = evaluate_signal_quality(
            calibrated_confidence=0.7,
            net_pnl_estimate=0.015,
            regime="BULL",
        )
        assert result["quality"] == "high"
        assert result["reject"] is False

    def test_low_confidence_rejected(self):
        result = evaluate_signal_quality(
            calibrated_confidence=0.3,
            net_pnl_estimate=0.01,
            regime="BULL",
        )
        assert result["quality"] in {"low", "reject"}

    def test_crisis_regime_low(self):
        result = evaluate_signal_quality(
            calibrated_confidence=0.9,
            net_pnl_estimate=0.02,
            regime="CRISIS",
        )
        assert result["quality"] in {"low", "reject"}

    def test_negative_net_pnl_rejected(self):
        result = evaluate_signal_quality(
            calibrated_confidence=0.6,
            net_pnl_estimate=-0.005,
            regime="BULL",
        )
        assert result["quality"] in {"low", "reject"}
        assert result["reject"] is True


class TestAggregatorD1:
    def test_compute_executable_levels_long(self):
        agg = SignalAggregator()
        levels = agg._compute_executable_levels(
            direction="long",
            current_price=100.0,
            atr=1.0,
        )
        assert "entry_levels" in levels
        assert len(levels["entry_levels"]) == 3
        assert levels["stop_loss_price"] < 100.0
        assert levels["take_profit_1_price"] > 100.0
        assert levels["take_profit_2_price"] > levels["take_profit_1_price"]
        assert math.isclose(
            sum(e["size_pct"] for e in levels["entry_levels"]), 1.0, abs_tol=1e-6
        )

    def test_compute_executable_levels_short(self):
        agg = SignalAggregator()
        levels = agg._compute_executable_levels(
            direction="short",
            current_price=100.0,
            atr=1.0,
        )
        assert levels["stop_loss_price"] > 100.0
        assert levels["take_profit_1_price"] < 100.0
        assert levels["take_profit_2_price"] < levels["take_profit_1_price"]

    def test_atr_constant_vol(self):
        agg = SignalAggregator()
        # constant H-L of 2.0 → TR per candle = 2.0 → ATR ≈ 2.0
        atr = agg._compute_atr_value(make_candles(20, vol=1.0), period=14)
        assert atr is not None
        assert math.isclose(atr, 2.0, rel_tol=0.05)