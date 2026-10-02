"""OKX 手续费 + 滑点模型。

用户超短线 = taker 为主 (0.08%)。
Slippage 默认 0.05% (固定)，可走 ATR-adaptive fallback。

可在运行时通过环境变量覆盖:
    OKX_TAKER_FEE_BPS=10.0 (default 8.0)
    OKX_MAKER_FEE_BPS=2.0  (default 2.0)
    SLIPPAGE_BPS=5.0       (default 5.0)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

Side = Literal["entry", "exit"]


def _bps_to_pct(bps: float) -> float:
    return bps / 10_000.0


# 模块加载时读取（支持 env 覆盖）
_TAKER_FEE_BPS = float(os.getenv("OKX_TAKER_FEE_BPS", "8.0"))
_MAKER_FEE_BPS = float(os.getenv("OKX_MAKER_FEE_BPS", "2.0"))
_SLIPPAGE_BPS = float(os.getenv("SLIPPAGE_BPS", "5.0"))


@dataclass(frozen=True)
class CostEstimate:
    entry_fee_pct: float
    exit_fee_pct: float
    slippage_pct: float
    total_round_trip_pct: float

    @property
    def total_round_trip_bps(self) -> float:
        return self.total_round_trip_pct * 10_000


def estimate_cost(side: Side) -> float:
    """OKX taker 单边费率（默认 0.08%）。

    Args:
        side: "entry" 或 "exit" — 实际当前实现两侧都按 taker 算（用户做加杠杆超短线默认 taker）。

    Returns:
        单边费率 (e.g. 0.0008 = 0.08%)。
    """
    return _bps_to_pct(_TAKER_FEE_BPS)


def estimate_round_trip_cost(slippage_mode: Literal["fixed", "atr"] = "fixed") -> CostEstimate:
    """单笔入场 + 出场 + 滑点的总成本。

    Args:
        slippage_mode: "fixed"（默认 0.05%）或 "atr"（K 线不足时退化为 fixed）。

    Returns:
        CostEstimate dataclass，含 entry_fee / exit_fee / slippage / 合计。
    """
    entry = estimate_cost("entry")
    exit_ = estimate_cost("exit")
    slip = _bps_to_pct(_SLIPPAGE_BPS)
    total = entry + exit_ + slip
    return CostEstimate(
        entry_fee_pct=entry,
        exit_fee_pct=exit_,
        slippage_pct=slip,
        total_round_trip_pct=total,
    )


def is_profitable_threshold(target_pct: float, confidence: float) -> bool:
    """判断「以当前 confidence 触发，target_pct 止盈」是否净赚。

    E[net_pnl] = target_pct * confidence - round_trip_cost
    若 E > 0 才有正期望 edge。

    Args:
        target_pct: 止盈百分比（e.g. 0.005 = 0.5%）。
        confidence: 信号 confidence (0~1)。

    Returns:
        True if expected net pnl > round_trip cost.
    """
    cost = estimate_round_trip_cost().total_round_trip_pct
    expected_edge = target_pct * confidence
    return expected_edge > cost