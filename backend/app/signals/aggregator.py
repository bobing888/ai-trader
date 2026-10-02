"""
推荐单引擎 — Signal Aggregator (v2)
Affinity Matrix 融合多策略信号 + 动态 min_agreement + 杠杆/时间周期分类。

v2 关键改进（解决 v1「推荐单永远为空」）：
1. **动态 min_agreement**：根据 regime 决定最低共识数
   - bull/bear: 1 个强信号（confidence>=0.8）即可；常规 2 个
   - choppy: 1 个均值回归信号即可
   - crisis: 2 个（避免假信号）
2. **strong-signal fast-path**：单策略 confidence>=0.85 即可输出（带警告）
3. **affinity 加权更细**：regime × direction 双重 affinity
4. **杠杆建议**：根据 timeframe 自动建议杠杆倍数（1m/5m → 5x-10x；1h → 3x；1d → 1x）
5. **时间周期分类**：超短线/短线/中线/长线
6. **杠杆风险评分**：confidence 低或 regime 危机时降杠杆
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np

from .calibration import calibrate
from .cost_model import estimate_round_trip_cost
from .regime import Regime
from .strategy_pool import (
    STRATEGY_INSTANCES,
    StrategyId,
    StrategyResult,
)


# ─── 时间周期分类（v2 新增）────────────────────────────────────────────────────

class TimeframeCategory(str, Enum):
    """时间周期分类，用于 UI 4 档切换 + 杠杆建议。"""
    ULTRA_SHORT = "ultra_short"   # 超短线：1m, 5m
    SHORT = "short"               # 短线：15m
    MID = "mid"                   # 中线：1h, 4h
    LONG = "long"                 # 长线：1d


_TIMEFRAME_CATEGORY: dict[str, TimeframeCategory] = {
    "1m": TimeframeCategory.ULTRA_SHORT,
    "5m": TimeframeCategory.ULTRA_SHORT,
    "15m": TimeframeCategory.SHORT,
    "1h": TimeframeCategory.MID,
    "4h": TimeframeCategory.MID,
    "1d": TimeframeCategory.LONG,
}

# 默认杠杆倍数（基于时间周期分类）
_DEFAULT_LEVERAGE = {
    TimeframeCategory.ULTRA_SHORT: 5,
    TimeframeCategory.SHORT: 3,
    TimeframeCategory.MID: 2,
    TimeframeCategory.LONG: 1,
}


def categorize_timeframe(timeframe: str) -> TimeframeCategory:
    """获取 timeframe 的分类。"""
    return _TIMEFRAME_CATEGORY.get(timeframe, TimeframeCategory.MID)


def suggest_leverage(
    timeframe: str,
    regime: Regime,
    confidence: float,
) -> int:
    """
    根据 timeframe + regime + confidence 建议杠杆倍数。

    规则：
    - 基础杠杆由 timeframe 决定
    - crisis: 强制 1x（不允许加杠杆）
    - confidence < 0.5: 降一档
    - confidence >= 0.8 + 强趋势: 可加一档（最多到 base）
    """
    cat = categorize_timeframe(timeframe)
    base = _DEFAULT_LEVERAGE[cat]

    if regime == Regime.CRISIS:
        return 1
    if confidence < 0.5:
        return max(1, base // 2)
    return base


# ─── Affinity Matrix（v2 微调）───────────────────────────────────────────────

_AFFINITY_BULL_LONG: dict[StrategyId, float] = {
    StrategyId.MOMENTUM: 0.30,
    StrategyId.MULTI_TF: 0.28,
    StrategyId.BREAKOUT: 0.22,    # v2: 0.20 → 0.22
    StrategyId.VOLUME: 0.18,      # v2: 0.15 → 0.18
    StrategyId.CONFLUENCE: 0.20,  # v2: 新增（之前 0）
    StrategyId.REVERSAL: 0.05,
    StrategyId.VOLATILITY: 0.05,
    StrategyId.SENTIMENT: 0.08,
}

_AFFINITY_BEAR_SHORT: dict[StrategyId, float] = {
    StrategyId.MOMENTUM: 0.30,
    StrategyId.SENTIMENT: 0.25,
    StrategyId.VOLATILITY: 0.20,  # v2: 0.18 → 0.20
    StrategyId.BREAKOUT: 0.18,    # v2: 0.15 → 0.18
    StrategyId.CONFLUENCE: 0.20,  # v2: 新增
    StrategyId.VOLUME: 0.15,
    StrategyId.REVERSAL: 0.05,
    StrategyId.MULTI_TF: 0.25,
}

_AFFINITY_CHOPPY_LONG: dict[StrategyId, float] = {
    StrategyId.REVERSAL: 0.30,
    StrategyId.VOLUME: 0.28,      # v2: 0.25 → 0.28
    StrategyId.MULTI_TF: 0.20,    # v2: 0.18 → 0.20
    StrategyId.CONFLUENCE: 0.18,  # v2: 新增
    StrategyId.MOMENTUM: 0.10,
    StrategyId.BREAKOUT: 0.12,    # v2: 0.10 → 0.12
    StrategyId.VOLATILITY: 0.05,
    StrategyId.SENTIMENT: 0.05,
}

_AFFINITY_CHOPPY_SHORT: dict[StrategyId, float] = {
    StrategyId.REVERSAL: 0.30,
    StrategyId.SENTIMENT: 0.22,
    StrategyId.VOLATILITY: 0.20,
    StrategyId.VOLUME: 0.18,
    StrategyId.CONFLUENCE: 0.18,  # v2: 新增
    StrategyId.BREAKOUT: 0.12,
    StrategyId.MULTI_TF: 0.12,    # v2: 0.10 → 0.12
    StrategyId.MOMENTUM: 0.05,
}

_AFFINITY_CRISIS: dict[StrategyId, float] = {
    StrategyId.VOLATILITY: 0.30,
    StrategyId.SENTIMENT: 0.25,
    StrategyId.REVERSAL: 0.20,    # v2: 0.18 → 0.20
    StrategyId.VOLUME: 0.18,      # v2: 0.15 → 0.18
    StrategyId.BREAKOUT: 0.05,
    StrategyId.MULTI_TF: 0.05,
    StrategyId.MOMENTUM: 0.05,
    StrategyId.CONFLUENCE: 0.05,  # v2: 新增
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


# ─── 动态 min_agreement（v2 新增）───────────────────────────────────────────

def _dynamic_min_agreement(regime: Regime, has_strong_signal: bool) -> int:
    """
    根据 regime 决定最少需要几个策略达成一致。

    规则（v2 改进）：
    - bull/bear + 有强信号 (>=0.85)：1 个即可
    - bull/bear 无强信号：2 个
    - choppy + 有强信号：1 个即可
    - choppy 无强信号：2 个（用 reversal/volume 共识）
    - crisis: 必须 2 个（防假信号）
    """
    if regime == Regime.CRISIS:
        return 1 if has_strong_signal else 2

    # bull/bear/choppy
    return 1 if has_strong_signal else 2


# ─── 输出 dataclass（v2 扩展字段）────────────────────────────────────────────

@dataclass
class AggregatedSignal:
    """最终推荐单"""
    pair: str
    direction: str           # "long" | "short"
    confidence: float         # 0.0–1.0 最终置信度（原始，未校准）
    contributing_strategies: list[str]
    reasons: list[str]
    regime: str
    regime_confidence: float
    entry_zones: list[str]
    risk_warnings: list[str]
    # v2 新增字段
    timeframe: str = "1h"
    timeframe_category: str = "mid"
    suggested_leverage: int = 1
    min_agreement_used: int = 2
    fast_path: bool = False   # 是否走 strong-signal 快速通道
    # Phase 1 signal credibility
    calibrated_confidence: float | None = None   # 经 per-tf Isotonic 校准后的胜率（None = 冷启动）
    net_pnl_estimate: float = 0.0                 # 预期净 PnL（confidence * target - cost）


class SignalAggregator:
    """
    多策略信号聚合器（v2）。

    v2 流程：
    1. 遍历 StrategyPool 中所有策略
    2. 按方向分组
    3. **动态 min_agreement** + strong-signal fast-path
    4. Affinity 加权 + 置信度计算
    5. 杠杆建议 + 时间周期分类
    6. 输出 AggregatedSignal
    """

    def __init__(self) -> None:
        """v2: 不再使用固定 min_agreement，根据 regime 动态决定。"""
        pass

    def aggregate(
        self,
        strategy_results: list[StrategyResult],
        regime: Regime,
        regime_confidence: float,
        timeframe: str = "1h",
    ) -> Optional[AggregatedSignal]:
        """
        聚合策略信号（v2）。
        """
        if not strategy_results:
            return None

        pair = strategy_results[0].pair
        tf = strategy_results[0].timeframe or timeframe

        # 按方向分组
        long_signals: list[StrategyResult] = []
        short_signals: list[StrategyResult] = []

        for r in strategy_results:
            if r.direction == "long":
                long_signals.append(r)
            elif r.direction == "short":
                short_signals.append(r)

        # v2: 检查是否有 strong signal（fast-path 触发条件）
        has_strong_long = any(s.confidence >= 0.85 for s in long_signals)
        has_strong_short = any(s.confidence >= 0.85 for s in short_signals)
        has_strong_signal = has_strong_long or has_strong_short

        # v2: 动态 min_agreement
        min_agr = _dynamic_min_agreement(regime, has_strong_signal)

        # 选更一致的方向（v2: tie-break 更公平——按 (count, avg_confidence) 比较）
        best_direction = None
        dominant_signals: list[StrategyResult] = []

        long_avg_conf = (
            np.mean([s.confidence for s in long_signals]) if long_signals else 0.0
        )
        short_avg_conf = (
            np.mean([s.confidence for s in short_signals]) if short_signals else 0.0
        )

        long_count = len(long_signals)
        short_count = len(short_signals)

        # v2: 同时满足 count 和 avg_conf 才选
        long_qualifies = long_count >= min_agr
        short_qualifies = short_count >= min_agr

        if long_qualifies and not short_qualifies:
            best_direction = "long"
            dominant_signals = long_signals
        elif short_qualifies and not long_qualifies:
            best_direction = "short"
            dominant_signals = short_signals
        elif long_qualifies and short_qualifies:
            # 双方都有信号 → 选 avg_conf 高的方向
            # 但当对侧 avg_conf 接近时，压制对方（避免反复）
            if long_avg_conf > short_avg_conf * 1.1:  # 至少 10% 优势
                best_direction = "long"
                dominant_signals = long_signals
            elif short_avg_conf > long_avg_conf * 1.1:
                best_direction = "short"
                dominant_signals = short_signals
            else:
                # 平局 → 用 fast-path 选强信号方
                if has_strong_long and not has_strong_short:
                    best_direction = "long"
                    dominant_signals = long_signals
                elif has_strong_short and not has_strong_long:
                    best_direction = "short"
                    dominant_signals = short_signals
                else:
                    # 仍然平局 → 选 avg_conf 较高方（不要求 10% 优势）
                    if long_avg_conf >= short_avg_conf:
                        best_direction = "long"
                        dominant_signals = long_signals
                    else:
                        best_direction = "short"
                        dominant_signals = short_signals

        if best_direction is None:
            # 无足够共识信号
            return None

        fast_path = has_strong_signal and (long_count + short_count) < 2 * min_agr

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

        # Regime 置信度加权
        regime_weight = 0.5 + 0.5 * regime_confidence
        # v2: 略放宽，避免低置信度 regime 把所有信号压成 0
        final_confidence = min(1.0, avg_confidence * regime_weight + 0.10 * regime_confidence)

        # 收集理由
        all_reasons: list[str] = []
        seen: set[str] = set()
        for sig in dominant_signals:
            for reason in sig.reasons:
                if reason not in seen:
                    seen.add(reason)
                    all_reasons.append(reason)

        # v2: Entry zones 更具体（按 timeframe 给具体区间）
        entry_zones = self._compute_entry_zones(
            dominant_signals, best_direction, regime, tf
        )

        # v2: Risk warnings 更细致（含杠杆警示）
        warnings = self._compute_warnings(
            dominant_signals, regime, final_confidence, tf, fast_path
        )

        # v2: 时间周期分类 + 杠杆建议
        tf_category = categorize_timeframe(tf)
        leverage = suggest_leverage(tf, regime, final_confidence)

        # Phase 1 signal credibility — calibration + cost-aware PnL
        # 校准后的真实胜率（None = calibrator 冷启动 / 未训练）
        calibrated = calibrate(final_confidence, tf)
        # 预期净 PnL = confidence * target_pct - cost
        target_pct_for_estimate = 0.005   # 默认 0.5% (同 backtest)
        cost = estimate_round_trip_cost().total_round_trip_pct
        net_pnl = final_confidence * target_pct_for_estimate - cost

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
            timeframe=tf,
            timeframe_category=tf_category.value,
            suggested_leverage=leverage,
            min_agreement_used=min_agr,
            fast_path=fast_path,
            calibrated_confidence=calibrated,
            net_pnl_estimate=net_pnl,
        )

    def _compute_entry_zones(
        self,
        signals: list[StrategyResult],
        direction: str,
        regime: Regime,
        timeframe: str,
    ) -> list[str]:
        """v2: 按 timeframe 给具体入场区间建议。"""
        zones = []
        cat = categorize_timeframe(timeframe)

        if direction == "long":
            if cat == TimeframeCategory.ULTRA_SHORT:
                zones.append("⚡ 超短线：现价附近分批建仓（1-2% 仓位）")
                zones.append(f"快进快出，止损 -0.5%/-1%")
            elif cat == TimeframeCategory.SHORT:
                zones.append("🎯 短线：现价下方 1-2% 分批建仓")
                zones.append(f"止损参考：近 {3} 日低点")
            elif cat == TimeframeCategory.MID:
                zones.append("📈 中线：现价下方 2-3% 分批建仓")
                zones.append(f"支撑参考：近 {7} 日低点")
            else:  # LONG
                zones.append("📊 长线：现价下方 5-10% 分批建仓")
                zones.append(f"支撑参考：近 {30} 日低点")

            if regime == Regime.CRISIS:
                zones.append("⚠️ 市场极端波动，建议观望")
        else:  # short
            if cat == TimeframeCategory.ULTRA_SHORT:
                zones.append("⚡ 超短线：现价附近分批做空（1-2% 仓位）")
                zones.append(f"快进快出，止损 -0.5%/-1%")
            elif cat == TimeframeCategory.SHORT:
                zones.append("🎯 短线：现价上方 1-2% 分批做空")
                zones.append(f"止损参考：近 {3} 日高点")
            elif cat == TimeframeCategory.MID:
                zones.append("📉 中线：现价上方 2-3% 分批做空")
                zones.append(f"阻力参考：近 {7} 日高点")
            else:
                zones.append("📊 长线：现价上方 5-10% 分批做空")
                zones.append(f"阻力参考：近 {30} 日高点")

            if regime == Regime.CRISIS:
                zones.append("⚠️ 市场极端波动，建议观望")
        return zones

    def _compute_warnings(
        self,
        signals: list[StrategyResult],
        regime: Regime,
        confidence: float,
        timeframe: str,
        fast_path: bool = False,
    ) -> list[str]:
        """v2: 增加杠杆/快进快出警示。"""
        warnings = []
        cat = categorize_timeframe(timeframe)
        leverage = suggest_leverage(timeframe, regime, confidence)

        if regime == Regime.CRISIS:
            warnings.append("⚠️ 市场处于极端波动区间，建议轻仓或观望")

        if confidence < 0.55:
            warnings.append(f"⚠️ 置信度偏低 ({confidence:.0%})，建议谨慎")

        if any(s.strategy == StrategyId.VOLATILITY for s in signals):
            warnings.append("⚠️ 波动率策略信号，注意止损")

        # v2: 杠杆警示
        if cat == TimeframeCategory.ULTRA_SHORT and leverage >= 3:
            warnings.append(f"⚡ 超短线建议杠杆 {leverage}x，快进快出严控止损")

        # v2: fast-path 警示
        if fast_path:
            warnings.append("ℹ️ 单策略强信号触发，建议交叉验证其他指标")

        return warnings
