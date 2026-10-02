"""SignalChangeDetector — 纯函数判定跟单是否因信号反转出场（spec §4.2）。

3 种机制:
1. regime flip 优先 — choppy 不算 flip（噪声）
2. 3 分钟窗口内（spec §0）
3. consecutive 2 次确认（避免单帧噪声）

用户 2026-10-02 决定:维持 3 分钟动量 + 2 次确认（spec 现状）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.models import RecommendationHistory, UserFollow

# 3 分钟 = 180 秒（spec §0）
_WINDOW_SECONDS = 180


@dataclass
class ReversalVerdict:
    """判定结果。"""

    reversed: bool
    reason: str | None = None  # "regime_flip" | "consecutive_reversal" | None


def detect_reversal(
    follow: UserFollow,
    current: RecommendationHistory,
    previous: RecommendationHistory | None,
    lookback_history: list[RecommendationHistory],
) -> ReversalVerdict:
    """判定 follow 是否应因信号反转出场。

    Args:
        follow: 跟单对象（用 direction + status + pair）
        current: 当前帧（最新写入 recommendation_history 的）
        previous: 上一帧（同 pair + tf + current 之前最近一帧）
        lookback_history: 最近 3 分钟窗口内的帧列表（保留供未来扩展）

    Returns:
        ReversalVerdict(reversed, reason)
    """
    if current is None:
        return ReversalVerdict(False, None)

    # 机制 1: regime flip 优先（无需 2 次确认，choppy 排除）
    if _is_regime_flip(follow, current):
        return ReversalVerdict(True, "regime_flip")

    # 机制 2+3: 3 分钟窗口 + 连续 2 帧
    if previous is None:
        return ReversalVerdict(False, None)
    if not _in_3min_window(previous, current):
        return ReversalVerdict(False, None)
    if _consecutive_reversal(follow, previous, current):
        return ReversalVerdict(True, "consecutive_reversal")

    return ReversalVerdict(False, None)


def _is_regime_flip(follow: UserFollow, current: RecommendationHistory) -> bool:
    """regime 从 long-friendly 翻成 short-friendly（或反向）。

    - 长 follow: bull → bear/crisis 算 flip
    - 空 follow: bear → bull/crisis 算 flip
    - choppy 噪声大，永远不算 flip
    """
    if not current.regime:
        return False
    if current.regime == "choppy":
        return False
    if follow.direction == "long":
        return current.regime in ("bear", "crisis")
    if follow.direction == "short":
        return current.regime in ("bull", "crisis")
    return False


def _in_3min_window(
    previous: RecommendationHistory, current: RecommendationHistory
) -> bool:
    """previous 与 current 间隔 ≤ 180 秒。"""
    delta = (current.scanned_at - previous.scanned_at).total_seconds()
    return 0 <= delta <= _WINDOW_SECONDS


def _consecutive_reversal(
    follow: UserFollow,
    previous: RecommendationHistory,
    current: RecommendationHistory,
) -> bool:
    """两帧都跟 follow 方向相反。"""
    return (
        previous.direction is not None
        and current.direction is not None
        and previous.direction != follow.direction
        and current.direction != follow.direction
    )
