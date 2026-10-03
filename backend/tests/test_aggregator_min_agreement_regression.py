"""Regression test: aggregator 在 ADX 强趋势 + Hurst 持续下不应因 min_agreement=2 返回 None。

bug 现象 (kbkkk.com 生产 2026-10-03):
  BTC 4h: ADX=28.4 (中等趋势), Hurst=0.88 (强持续) → 仍 has_signal=false
  BTC 1h: ADX=13.2 (无趋势), Hurst=0.90 (强持续) → 仍 has_signal=false

根因:
  aggregator._dynamic_min_agreement 在没有 strong signal (≥0.85) 时,
  bull/bear/choppy 全部要求 min_agreement=2。
  但实际策略 confidence 上限是 0.85,且常受多策略方向冲突影响。

修复:
  bull/bear + ADX >= 20 + Hurst >= 0.55 → 允许 min_agreement=1 (一个高
  confidence 策略即可)
"""
from __future__ import annotations

import numpy as np

from app.signals.aggregator import SignalAggregator
from app.signals.regime import Regime
from app.signals.strategy_pool import (
    STRATEGY_INSTANCES,
    StrategyId,
    StrategyResult,
)


def _mk_result(strategy: StrategyId, direction: str, confidence: float) -> StrategyResult:
    return StrategyResult(
        strategy=strategy,
        pair="BTC-USDT",
        timeframe="4h",
        direction=direction,
        confidence=confidence,
        reasons=(f"{strategy.value} test",),
        suitable_regimes=frozenset({"bull", "bear", "choppy"}),
    )


def test_strong_trend_with_1_long_signal_should_not_be_none():
    """ADX 30 + Hurst 0.65 + bull regime + 1 long @ 0.78 → 必须出 long 信号.

    修复前: min_agreement=2, 只有 1 个 long → return None.
    修复后: 强趋势下 min_agreement=1, 应出 AggregatedSignal.
    """
    strategy_results = [
        _mk_result(StrategyId.MOMENTUM, "long", 0.78),     # 唯一 long
        _mk_result(StrategyId.VOLUME, "short", 0.55),      # 反向
        _mk_result(StrategyId.REVERSAL, "short", 0.50),
    ]

    agg = SignalAggregator()
    sig = agg.aggregate(
        strategy_results,
        regime=Regime.BULL,
        regime_confidence=0.65,
        timeframe="4h",
        adx=30.0,        # 强趋势 (中等趋势, ADX 20-50)
        hurst=0.65,      # 持续性
    )

    assert sig is not None, "强趋势 + bull + 1 个高 conf long 不应被 min_agreement=2 卡住"
    assert sig.direction == "long", f"应选 long, 实际 {sig.direction}"
    assert sig.confidence >= 0.5, f"confidence={sig.confidence} 应 ≥ 0.5"


def test_choppy_with_no_strong_signal_still_requires_2():
    """choppy + ADX=10 (无趋势) + 1 long @ 0.6 → 仍应 None (不能放宽太多)."""
    strategy_results = [
        _mk_result(StrategyId.MOMENTUM, "long", 0.60),
        _mk_result(StrategyId.VOLUME, "short", 0.55),
        _mk_result(StrategyId.REVERSAL, "short", 0.50),
    ]

    agg = SignalAggregator()
    # 模拟 choppy + 无 ADX + 无 Hurst (Hurst=None 表示数据不足)
    # → _dynamic_min_agreement 看到 has_strong_signal=False → 应保持 2
    sig = agg.aggregate(
        strategy_results,
        regime=Regime.CHOPPY,
        regime_confidence=0.4,
        timeframe="1h",
    )

    # choppy 无趋势只有 1 个 long 0.6 → 应该 return None (不能乱出)
    assert sig is None, f"choppy 无趋势 + 单 long 不应出信号, got {sig}"
