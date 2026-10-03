"""
horizon.py — Horizon tier classification for multi-timeframe signal engine.

Defines:
- HorizonTier enum (P0_LONG through P3_UHF)
- TierConfig dataclass per tier (Task 1: timeframes, hold_time_hours, leverage_max)
- HORIZON_META per tier (Task 3: informative_timeframes, hold_time_min/max)
- TIER_CONFIG lookup table (Task 1)
- is_p0/is_p1/is_p2/is_p3 tier-grouping properties (Task 3)

Spec: docs/superpowers/specs/2026-10-03-multi-tf-leverage-uhf-design.md §3.A
Plan: docs/superpowers/plans/2026-10-03-multi-tf-leverage-uhf.md Tasks 1+3
"""

from dataclasses import dataclass
from enum import Enum
from typing import List


class HorizonTier(str, Enum):
    P0_LONG = "P0_long"
    P0_CROSS_MONTH = "P0_cross_month"
    P1_MID = "P1_mid"
    P1_SHORT = "P1_short"
    P2_ULTRA = "P2_ultra"
    P3_UHF = "P3_uhf"

    # ─── Tier-grouping properties (Task 3 reconciliation) ──────────────
    @property
    def is_p0(self) -> bool:
        """True for P0_LONG + P0_CROSS_MONTH (long-horizon tiers)."""
        return self in (HorizonTier.P0_LONG, HorizonTier.P0_CROSS_MONTH)

    @property
    def is_p1(self) -> bool:
        """True for P1_MID + P1_SHORT (mid-horizon tiers)."""
        return self in (HorizonTier.P1_MID, HorizonTier.P1_SHORT)

    @property
    def is_p2(self) -> bool:
        """True for P2_ULTRA (ultra-short)."""
        return self == HorizonTier.P2_ULTRA

    @property
    def is_p3(self) -> bool:
        """True for P3_UHF (paper-trading)."""
        return self == HorizonTier.P3_UHF


@dataclass(frozen=True)
class TierConfig:
    """Task 1 schema — used by aggregator / quality_gate / API filters."""
    timeframes: List[str]
    hold_time_hours: int
    leverage_max: int
    delta_neutral_only: bool = False


TIER_CONFIG: dict[HorizonTier, TierConfig] = {
    HorizonTier.P0_LONG: TierConfig(["1d", "1w"], 24 * 7, 1),
    HorizonTier.P0_CROSS_MONTH: TierConfig(["1w", "1M"], 24 * 30, 1),
    HorizonTier.P1_MID: TierConfig(["4h", "1d"], 24, 3),
    HorizonTier.P1_SHORT: TierConfig(["1h", "4h"], 12, 5),
    HorizonTier.P2_ULTRA: TierConfig(["5m", "15m"], 2, 5),
    HorizonTier.P3_UHF: TierConfig(["1m", "5m"], 1, 100, delta_neutral_only=True),
}


# ─── Task 3 metadata: informative TFs + human-readable bounds ──────────────
# Augmented alongside TIER_CONFIG; useful for strategy_pool horizon tagging
# and for human-readable display (labels).
HORIZON_META: dict[HorizonTier, dict] = {
    HorizonTier.P0_LONG: {
        "informative_timeframes": ["1d", "4h", "1h"],
        "hold_time_min": "1d",
        "hold_time_max": "4w",
        "leverage_max": 1,
        "label": "长期 1d/1w",
    },
    HorizonTier.P0_CROSS_MONTH: {
        "informative_timeframes": ["1w", "1d", "4h"],
        "hold_time_min": "2w",
        "hold_time_max": "3M",
        "leverage_max": 1,
        "label": "跨月 1w/1M",
    },
    HorizonTier.P1_MID: {
        "informative_timeframes": ["4h", "1h", "15m"],
        "hold_time_min": "4h",
        "hold_time_max": "2d",
        "leverage_max": 3,
        "label": "中期 4h",
    },
    HorizonTier.P1_SHORT: {
        "informative_timeframes": ["1h", "15m", "5m"],
        "hold_time_min": "1h",
        "hold_time_max": "12h",
        "leverage_max": 5,
        "label": "短期 1h",
    },
    HorizonTier.P2_ULTRA: {
        "informative_timeframes": ["5m", "1m"],
        "hold_time_min": "5m",
        "hold_time_max": "2h",
        "leverage_max": 5,
        "label": "超短 5m/15m",
    },
    HorizonTier.P3_UHF: {
        "informative_timeframes": ["1m"],
        "hold_time_min": "1m",
        "hold_time_max": "30m",
        "leverage_max": 100,
        "label": "UHF 1m (paper)",
    },
}