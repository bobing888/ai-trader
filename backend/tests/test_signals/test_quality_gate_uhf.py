"""Tests for quality_gate UHF strict mode (Task 5, spec §3.D)."""

import pytest


# ─── Gate result dataclass (mirrors what gate() returns) ──────────────────────


class GateResult:
    def __init__(self, passed: bool, reasons: list[str]):
        self.passed = passed
        self.reasons = reasons

    def __repr__(self):
        return f"GateResult(passed={self.passed}, reasons={self.reasons})"

    def __eq__(self, other):
        return self.passed == other.passed and self.reasons == other.reasons


# ─── P3_UHF 6-gate tests ───────────────────────────────────────────────────────


def test_quality_gate_rejects_uhf_missing_funding_rate():
    """funding_rate missing → reject (gate 1: funding_rate abs > 0.01%/8h)."""
    from app.signals.quality_gate import gate
    signal = {"horizon_tier": "P3_uhf", "leverage": 100}
    market = {"funding_rate": None, "oi_24h_change": 0.02, "volume_24h_usdt": 1.5e9, "spread": 0.0003}
    result = gate(signal, market)
    assert result.passed is False, f"Expected reject, got {result}"
    assert any("funding_rate" in r for r in result.reasons), f"Expected funding_rate reason, got {result.reasons}"


def test_quality_gate_rejects_uhf_high_funding_rate():
    """funding_rate abs > 0.0001 (0.01%/8h) → reject."""
    from app.signals.quality_gate import gate
    signal = {"horizon_tier": "P3_uhf", "leverage": 100}
    market = {"funding_rate": 0.0002, "oi_24h_change": 0.02, "volume_24h_usdt": 1.5e9, "spread": 0.0003}
    result = gate(signal, market)
    assert result.passed is False, f"Expected reject for high funding_rate, got {result}"
    assert any("funding_rate" in r for r in result.reasons), f"Expected funding_rate reason, got {result.reasons}"


def test_quality_gate_rejects_uhf_low_volume():
    """volume_24h_usdt < 1B → reject (gate 2)."""
    from app.signals.quality_gate import gate
    signal = {"horizon_tier": "P3_uhf", "leverage": 100}
    market = {"funding_rate": 0.00005, "oi_24h_change": 0.02, "volume_24h_usdt": 5e8, "spread": 0.0003}
    result = gate(signal, market)
    assert result.passed is False, f"Expected reject for low volume, got {result}"
    assert any("volume" in r.lower() for r in result.reasons), f"Expected volume reason, got {result.reasons}"


def test_quality_gate_rejects_uhf_negative_oi_change():
    """OI 24h change < -0.05 → reject (gate 3: 多空双爆)."""
    from app.signals.quality_gate import gate
    signal = {"horizon_tier": "P3_uhf", "leverage": 100}
    market = {"funding_rate": 0.00005, "oi_24h_change": -0.10, "volume_24h_usdt": 1.5e9, "spread": 0.0003}
    result = gate(signal, market)
    assert result.passed is False, f"Expected reject for negative OI, got {result}"
    assert any("oi" in r.lower() for r in result.reasons), f"Expected OI reason, got {result.reasons}"


def test_quality_gate_rejects_uhf_wide_spread():
    """spread > 0.0005 (0.05%) → reject (gate 4)."""
    from app.signals.quality_gate import gate
    signal = {"horizon_tier": "P3_uhf", "leverage": 100}
    market = {"funding_rate": 0.00005, "oi_24h_change": 0.02, "volume_24h_usdt": 1.5e9, "spread": 0.001}
    result = gate(signal, market)
    assert result.passed is False, f"Expected reject for wide spread, got {result}"
    assert any("spread" in r.lower() for r in result.reasons), f"Expected spread reason, got {result.reasons}"


def test_quality_gate_rejects_uhf_non_delta_neutral():
    """100x without delta_neutral=True → reject (gate 5)."""
    from app.signals.quality_gate import gate
    signal = {"horizon_tier": "P3_uhf", "leverage": 100, "delta_neutral": False}
    market = {"funding_rate": 0.00005, "oi_24h_change": 0.02, "volume_24h_usdt": 1.5e9, "spread": 0.0003}
    result = gate(signal, market)
    assert result.passed is False, f"Expected reject for non-delta-neutral, got {result}"
    assert any("delta_neutral" in r or "delta" in r for r in result.reasons), f"Expected delta_neutral reason, got {result.reasons}"


def test_quality_gate_accepts_uhf_delta_neutral_all_gates_pass():
    """P3_UHF with delta_neutral=True + all 6 gates pass → accept."""
    from app.signals.quality_gate import gate
    signal = {"horizon_tier": "P3_uhf", "leverage": 100, "delta_neutral": True}
    market = {
        "funding_rate": 0.00005,
        "oi_24h_change": 0.02,
        "volume_24h_usdt": 1.5e9,
        "spread": 0.0003,
    }
    result = gate(signal, market)
    assert result.passed is True, f"Expected pass for good UHF signal, got {result}"


# ─── Non-UHF tiers keep existing logic ───────────────────────────────────────


def test_non_uhf_tier_passes_without_market_data():
    """Non-UHF tiers (e.g. P1) should not require market dict fields."""
    from app.signals.quality_gate import gate
    signal = {"horizon_tier": "P1", "leverage": 3}
    # market can be None or minimal for non-UHF tiers
    result = gate(signal, None)
    # Should not crash; the existing logic doesn't need market data
    assert hasattr(result, "passed")
    assert hasattr(result, "reasons")


def test_non_uhf_tier_rejects_low_confidence():
    """Non-UHF tiers still reject low confidence via existing gate."""
    from app.signals.quality_gate import gate
    signal = {"horizon_tier": "P1", "leverage": 3, "calibrated_confidence": 0.3, "net_pnl_estimate": 0.002, "regime": "BULL"}
    result = gate(signal, None)
    # Low confidence should cause reject
    assert result.passed is False, f"Expected reject for low confidence, got {result}"
