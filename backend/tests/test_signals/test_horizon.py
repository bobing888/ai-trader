"""
Tests for horizon.py — HorizonTier enum + TIER_CONFIG.
Step 1 (RED): write failing tests.
Step 4 (GREEN): horizon.py exists and these pass.
"""

import pytest


def test_horizon_tier_enum_values():
    from app.signals.horizon import HorizonTier
    assert HorizonTier.P0_LONG.value == "P0_long"
    assert HorizonTier.P3_UHF.value == "P3_uhf"


def test_tier_config_p0_long():
    from app.signals.horizon import HorizonTier, TIER_CONFIG
    cfg = TIER_CONFIG[HorizonTier.P0_LONG]
    assert cfg.timeframes == ["1d", "1w"]
    assert cfg.leverage_max == 1
    assert cfg.hold_time_hours == 24 * 7  # 1 周


def test_tier_config_p3_uhf_delta_neutral():
    from app.signals.horizon import HorizonTier, TIER_CONFIG
    cfg = TIER_CONFIG[HorizonTier.P3_UHF]
    assert cfg.timeframes == ["1m", "5m"]
    assert cfg.leverage_max == 100
    assert cfg.delta_neutral_only is True
