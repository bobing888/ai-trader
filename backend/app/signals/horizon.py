"""
horizon.py — Horizon tier classification for multi-timeframe signal engine.

Defines:
- HorizonTier enum (P0_LONG through P3_UHF)
- TierConfig dataclass per tier
- TIER_CONFIG lookup table

Spec: docs/superpowers/specs/2026-10-03-multi-tf-leverage-uhf-design.md §3.A
Plan:  docs/superpowers/plans/2026-10-03-multi-tf-leverage-uhf.md Task 1
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


@dataclass(frozen=True)
class TierConfig:
    timeframes: List[str]
    hold_time_hours: int
    leverage_max: int
    delta_neutral_only: bool = False


TIER_CONFIG = {
    HorizonTier.P0_LONG: TierConfig(["1d", "1w"], 24 * 7, 1),
    HorizonTier.P0_CROSS_MONTH: TierConfig(["1w", "1M"], 24 * 30, 1),
    HorizonTier.P1_MID: TierConfig(["4h", "1d"], 24, 3),
    HorizonTier.P1_SHORT: TierConfig(["1h", "4h"], 12, 5),
    HorizonTier.P2_ULTRA: TierConfig(["5m", "15m"], 2, 5),
    HorizonTier.P3_UHF: TierConfig(["1m", "5m"], 1, 100, delta_neutral_only=True),
}
