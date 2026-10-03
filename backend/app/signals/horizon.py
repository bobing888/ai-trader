"""
horizon.py — 时间框架分级（Horizon Tiers）
参照 spec §3.A：P0/P1/P2/P3 四档 + informative_timeframes 配置
"""

from enum import Enum


class HorizonTier(str, Enum):
    """
    策略对应的时间框架档位。

    | Tier          | 主要 TF       | 辅助 informative TF        |
    |---------------|---------------|---------------------------|
    | P0_LONG       | 1d / 1w       | [1d, 4h, 1h]              |
    | P0_CROSS_MONTH| 1w / 1M        | [1w, 1d, 4h]              |
    | P1_MID        | 4h / 1d        | [4h, 1h, 15m]             |
    | P1_SHORT      | 1h / 4h        | [1h, 15m, 5m]             |
    | P2_ULTRA      | 5m / 15m       | [5m, 1m]                  |
    | P3_UHF        | 1m / 5m        | [1m]                       |
    """
    P0_LONG = "p0_long"
    P0_CROSS_MONTH = "p0_cross_month"
    P1_MID = "p1_mid"
    P1_SHORT = "p1_short"
    P2_ULTRA = "p2_ultra"
    P3_UHF = "p3_uhf"

    @property
    def is_p0(self) -> bool:
        return self in (HorizonTier.P0_LONG, HorizonTier.P0_CROSS_MONTH)

    @property
    def is_p1(self) -> bool:
        return self in (HorizonTier.P1_MID, HorizonTier.P1_SHORT)

    @property
    def is_p2(self) -> bool:
        return self == HorizonTier.P2_ULTRA

    @property
    def is_p3(self) -> bool:
        return self == HorizonTier.P3_UHF


# ─── 每档的元数据（informative TFs + 建议持仓时间）───────────────────────────

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
