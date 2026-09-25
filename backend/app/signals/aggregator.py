"""
推荐单引擎 — Signal Aggregator
Affinity Matrix 融合多策略信号，输出最终推荐单
"""

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .regime import Regime
from .strategy_pool import (
    STRATEGY_INSTANCES,
    StrategyId,
    StrategyResult,
)


# ─── Affinity Matrix ─────────────────────────────────────────────────────────
# 亲和度矩阵：行为源策略，列为目标推荐方向，值为权重
# 格式: affinity[source][target] = bonus_score (0–0.3)
#
# 核心思想：
#   - 多空方向一致的策略互相强化
#   - 跨策略互补（如 Momentum + Volume 互相确认）
#   - Regime 适配策略加权更高

_AFFINITY_BULL_LONG: dict[StrategyId, float] = {
    StrategyId.MOMENTUM:       0.30,  # 趋势跟踪是核心
    StrategyId.MULTI_TF:        0.28,  # 多周期共振最强
    StrategyId.BREAKOUT:        0.20,  # 突破确认
    StrategyId.VOLUME:          0.15,  # 量价配合
    StrategyId.REVERSAL:        0.05,  # 反向信号轻微干扰
    StrategyId.VOLATILITY:      0.05,
    StrategyId.SENTIMENT:       0.08,
}

_AFFINITY_BEAR_SHORT: dict[StrategyId, float] = {
    StrategyId.MOMENTUM:       0.30,
    StrategyId.SENTIMENT:       0.25,  # 情绪反向在熊市更强
    StrategyId.VOLATILITY:      0.18,
    StrategyId.BREAKOUT:        0.15,
    StrategyId.VOLUME:          0.12,
    StrategyId.REVERSAL:        0.05,
    StrategyId.MULTI_TF:        0.25,
}

_AFFINITY_CHOPPY_LONG: dict[StrategyId, float] = {
    StrategyId.REVERSAL:        0.30,  # 震荡中高抛低吸
    StrategyId.VOLUME:           0.25,
    StrategyId.MULTI_TF:        0.18,
    StrategyId.MOMENTUM:         0.10,
    StrategyId.BREAKOUT:         0.10,
    StrategyId.VOLATILITY:       0.05,
    StrategyId.SENTIMENT:       0.05,
}

_AFFINITY_CHOPPY_SHORT: dict[StrategyId, float] = {
    StrategyId.REVERSAL:        0.30,
    StrategyId.SENTIMENT:        0.20,
    StrategyId.VOLATILITY:       0.18,
    StrategyId.VOLUME:           0.15,
    StrategyId.BREAKOUT:         0.10,
    StrategyId.MULTI_TF:         0.10,
    StrategyId.MOMENTUM:          0.05,
}

_AFFINITY_CRISIS: dict[StrategyId, float] = {
    StrategyId.VOLATILITY:      0.30,  # 极端波动用波动率策略
    StrategyId.SENTIMENT:        0.25,
    StrategyId.REVERSAL:         0.18,
    StrategyId.VOLUME:           0.15,
    StrategyId.BREAKOUT:          0.05,
    StrategyId.MULTI_TF:         0.05,
    StrategyId.MOMENTUM:         0.05,
}


def _select_affinity(regime: Regime, direction: str) -> dict[StrategyId, float]:
    if regime == Regime.CRISIS:
        return _AFFINITY_CRISIS
    if regime == Regime.BULL:
        return _AFFINITY_BULL_LONG if direction == "long" else _AFFINITY_BEAR_SHORT
    if regime == Regime.BEAR:
        return _AFFINITY_BEAR_SHORT if direction == "short" else _AFFINITY_BULL_LONG
    # CHOPPY
    return _AFFINITY_CHOPPY_LONG if direction == "long" else _AFFINITY_CHOPPY_SHORT


@dataclass
class AggregatedSignal:
    """最终推荐单"""
    pair: str
    direction: str           # "long" | "short"
    confidence: float         # 0.0–1.0 最终置信度
    contributing_strategies: list[str]
    reasons: list[str]
    regime: str
    regime_confidence: float
    entry_zones: list[str]    # 入场参考价
    risk_warnings: list[str]


class SignalAggregator:
    """
    多策略信号聚合器。

    流程：
    1. 遍历 StrategyPool 中所有策略
    2. 按 Affinity Matrix 融合方向一致的信号
    3. 计算加权置信度
    4. 过滤矛盾信号（多空打架则降权或放弃）
    5. 输出 AggregatedSignal
    """

    def __init__(self, min_agreement: int = 2) -> None:
        """
        min_agreement: 最少需要多少个策略达成方向一致才输出信号
        """
        self._min_agreement = min_agreement

    def aggregate(
        self,
        strategy_results: list[StrategyResult],
        regime: Regime,
        regime_confidence: float,
    ) -> Optional[AggregatedSignal]:
        """
        聚合策略信号。
        """
        if not strategy_results:
            return None

        pair = strategy_results[0].pair
        timeframe = strategy_results[0].timeframe

        # 按方向分组
        long_signals: list[StrategyResult] = []
        short_signals: list[StrategyResult] = []

        for r in strategy_results:
            if r.direction == "long":
                long_signals.append(r)
            elif r.direction == "short":
                short_signals.append(r)

        # 取更一致的方向
        best_direction = None
        dominant_signals: list[StrategyResult] = []

        if len(long_signals) >= self._min_agreement and len(long_signals) >= len(short_signals):
            best_direction = "long"
            dominant_signals = long_signals
        elif len(short_signals) >= self._min_agreement:
            best_direction = "short"
            dominant_signals = short_signals

        if best_direction is None:
            # 无足够共识信号
            return None

        # Affinity 加权
        affinity = _select_affinity(regime, best_direction)

        total_score = 0.0
        weighted_conf = 0.0
        for sig in dominant_signals:
            affinity_bonus = affinity.get(sig.strategy, 0.1)
            score = sig.confidence + affinity_bonus
            total_score += score
            weighted_conf += sig.confidence * score

        avg_confidence = (weighted_conf / total_score) if total_score > 0 else 0.0

        # Regime 置信度加权：高置信度 regime → 更可信
        regime_weight = 0.5 + 0.5 * regime_confidence
        final_confidence = min(1.0, avg_confidence * regime_weight + 0.05 * regime_confidence)

        # 收集理由（去重）
        all_reasons: list[str] = []
        seen: set[str] = set()
        for sig in dominant_signals:
            for reason in sig.reasons:
                if reason not in seen:
                    seen.add(reason)
                    all_reasons.append(reason)

        # Entry zones
        entry_zones = self._compute_entry_zones(dominant_signals, best_direction, regime)

        # Risk warnings
        warnings = self._compute_warnings(dominant_signals, regime, final_confidence)

        return AggregatedSignal(
            pair=pair,
            direction=best_direction,
            confidence=round(final_confidence, 3),
            contributing_strategies=[s.strategy.value for s in dominant_signals],
            reasons=all_reasons,
            regime=regime.value,
            regime_confidence=regime_confidence,
            entry_zones=entry_zones,
            risk_warnings=warnings,
        )

    def _compute_entry_zones(
        self,
        signals: list[StrategyResult],
        direction: str,
        regime: Regime,
    ) -> list[str]:
        zones = []
        if direction == "long":
            zones.append("现价区间下方 1–2% 分批建仓")
            if regime == Regime.CRISIS:
                zones.append("建议观望，等 ATR 收敛")
            else:
                zones.append(f"支撑参考：近 {7} 日低点")
        else:
            zones.append("现价区间上方 1–2% 分批建仓")
            if regime == Regime.CRISIS:
                zones.append("建议观望，等波动率回落")
            else:
                zones.append(f"阻力参考：近 {7} 日高点")
        return zones

    def _compute_warnings(
        self,
        signals: list[StrategyResult],
        regime: Regime,
        confidence: float,
    ) -> list[str]:
        warnings = []
        if regime == Regime.CRISIS:
            warnings.append("⚠️ 市场处于极端波动区间，建议轻仓")
        if confidence < 0.6:
            warnings.append("⚠️ 置信度偏低，建议谨慎")
        if any(s.strategy == StrategyId.VOLATILITY for s in signals):
            warnings.append("⚠️ 波动率策略信号，注意止损")
        return warnings
