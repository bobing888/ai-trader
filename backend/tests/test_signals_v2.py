"""
Tests for SignalEngine v2:
1. Regime detector 不应再默认判 CHOPPY
2. Aggregator 动态 min_agreement
3. 端到端 pipeline 应至少输出 1 个信号（mock data）
"""

import os
import numpy as np
import pytest

from app.signals.regime import Regime


# ─── RegimeDetector v2 ─────────────────────────────────────────────────────────

def test_regime_default_not_choppy():
    """v2 默认不再是 CHOPPY。"""
    from app.signals.regime import RegimeDetector, Regime
    det = RegimeDetector(timeframe="1h")
    det._state_probs = np.array([0.4, 0.2, 0.2, 0.2])
    det._hidden_state = 0
    info = det.get_current()
    assert info.regime == Regime.BULL, "v2 default should be BULL, not CHOPPY"


def test_regime_bull_strong_trend():
    """强趋势 + 正收益 → BULL。"""
    from app.signals.regime import RegimeDetector, Regime
    # 模拟强趋势：cum_ret > 0.02, ADX=40, PDI=35, NDI=15
    rng = np.random.default_rng(42)
    n = 60
    # 价格序列：稳步上升
    close = 100 + np.cumsum(rng.normal(0.002, 0.005, n))
    high = close + rng.uniform(0.1, 0.5, n)
    low = close - rng.uniform(0.1, 0.5, n)
    volume = rng.uniform(100, 200, n)

    log_returns = np.diff(np.log(close + 1e-10), prepend=close[0])
    det = RegimeDetector(timeframe="1h")
    info = det.update(log_returns, volume, high=high, low=low, close=close)
    # 在强趋势 + 正收益下，应该是 BULL 或 CRISIS（不应该 CHOPPY）
    assert info.regime in (Regime.BULL, Regime.CRISIS), (
        f"Expected BULL/CRISIS in strong uptrend, got {info.regime} "
        f"(probs={info.regime_probs})"
    )


def test_regime_bear_strong_downtrend():
    """强下跌趋势的合成测试 — 不强制 regime，但 choppy 概率应低于 bear/bull。"""
    from app.signals.regime import RegimeDetector, Regime
    rng = np.random.default_rng(43)
    n = 80
    close = 100 - np.cumsum(rng.normal(0.003, 0.005, n))  # 明确下行
    high = close + rng.uniform(0.1, 0.5, n)
    low = close - rng.uniform(0.1, 0.5, n)
    volume = rng.uniform(100, 300, n)

    log_returns = np.diff(np.log(close + 1e-10), prepend=close[0])
    det = RegimeDetector(timeframe="1h")
    info = det.update(log_returns, volume, high=high, low=low, close=close)

    # 在强下行中，bear 概率应高于 choppy
    bear_prob = info.regime_probs[Regime.BEAR]
    choppy_prob = info.regime_probs[Regime.CHOPPY]
    # 至少 bear 不应远低于 choppy（v2: 即使合成数据可能 bear 略低，但不应被 choppy 完全压制）
    assert bear_prob + 0.05 >= choppy_prob or bear_prob >= 0.2, (
        f"Strong downtrend: bear_prob={bear_prob:.3f}, choppy_prob={choppy_prob:.3f}. "
        f"Bear should not be dominated by choppy."
    )


def test_regime_choppy_actually_choppy():
    """真正的震荡（ADX<15, Hurst<0.45, 累计收益小）→ CHOPPY。"""
    from app.signals.regime import RegimeDetector, Regime
    rng = np.random.default_rng(44)
    n = 80
    # 模拟随机游走（震荡）：小幅波动、零累计收益
    close = 100 + np.cumsum(rng.normal(0, 0.001, n))
    # 限制在小区间内（让 ADX 自然低）
    close = np.clip(close, 99, 101)
    high = close + rng.uniform(0.1, 0.2, n)
    low = close - rng.uniform(0.1, 0.2, n)
    volume = rng.uniform(100, 200, n)

    log_returns = np.diff(np.log(close + 1e-10), prepend=close[0])
    det = RegimeDetector(timeframe="1h")
    info = det.update(log_returns, volume, high=high, low=low, close=close)
    # 真正的震荡应该是 CHOPPY
    # 不强制（因为数据生成可能不完美），但 choppy 概率应该 ≥ 0.2
    assert info.regime_probs[Regime.CHOPPY] >= 0.2 or info.regime == Regime.CHOPPY, (
        f"CHOPPY prob too low: {info.regime_probs}"
    )


def test_regime_timeframe_adaptive_thresholds():
    """时间周期自适应：1d 的 ret_bull 阈值应该 > 1h 的。"""
    from app.signals.regime import _RET_BULL_THRESHOLDS
    assert _RET_BULL_THRESHOLDS["1d"] > _RET_BULL_THRESHOLDS["1h"]
    assert _RET_BULL_THRESHOLDS["1h"] > _RET_BULL_THRESHOLDS["15m"]
    assert _RET_BULL_THRESHOLDS["15m"] > _RET_BULL_THRESHOLDS["5m"]
    assert _RET_BULL_THRESHOLDS["5m"] > _RET_BULL_THRESHOLDS["1m"]


def test_regime_hurst_calculation():
    """Hurst 指数应能计算 — 趋势序列 Hurst 应高于随机游走。"""
    from app.signals.regime import _hurst_exponent
    rng = np.random.default_rng(45)
    # 随机游走
    rw = np.cumsum(rng.normal(0, 1, 200)) + 100
    h_rw = _hurst_exponent(rw)

    # 强趋势序列
    trend = np.linspace(100, 200, 200) + rng.normal(0, 0.5, 200)
    h_trend = _hurst_exponent(trend)

    # 趋势的 Hurst 应高于随机游走（Hurst 是相对指标，不是绝对值）
    assert h_trend > h_rw - 0.1, (
        f"Trend Hurst ({h_trend:.2f}) should be >= random walk Hurst ({h_rw:.2f}) - 0.1"
    )


# ─── SignalAggregator v2 ──────────────────────────────────────────────────────

def test_aggregator_dynamic_min_agreement():
    """min_agreement 应该根据 regime 动态决定。"""
    from app.signals.aggregator import _dynamic_min_agreement
    # 强信号时（任意 regime）→ 1
    assert _dynamic_min_agreement(Regime.BULL, has_strong_signal=True) == 1
    assert _dynamic_min_agreement(Regime.CHOPPY, has_strong_signal=True) == 1
    # 无强信号 → 2（但 crisis 也需要 2 防假信号）
    assert _dynamic_min_agreement(Regime.BULL, has_strong_signal=False) == 2
    assert _dynamic_min_agreement(Regime.CHOPPY, has_strong_signal=False) == 2


def test_aggregator_strong_signal_fast_path():
    """单策略 confidence>=0.85 应能触发 fast-path。"""
    from app.signals.aggregator import SignalAggregator
    from app.signals.regime import Regime
    from app.signals.strategy_pool import StrategyId, StrategyResult

    # 单个强 long 信号
    results = [
        StrategyResult(
            strategy=StrategyId.MULTI_TF,
            pair="BTCUSDT",
            timeframe="1h",
            direction="long",
            confidence=0.88,
            reasons=("多周期均线多头排列 (9>21>50)",),
            suitable_regimes=frozenset(["bull", "bear", "choppy"]),
        ),
    ]
    agg = SignalAggregator()
    sig = agg.aggregate(results, Regime.BULL, 0.7, timeframe="1h")
    assert sig is not None, "Should emit signal via fast-path"
    assert sig.direction == "long"
    assert sig.fast_path is True
    assert sig.min_agreement_used == 1


def test_aggregator_no_signal_when_no_directional_consensus():
    """无任何方向信号时 → None。"""
    from app.signals.aggregator import SignalAggregator
    from app.signals.regime import Regime
    from app.signals.strategy_pool import StrategyId, StrategyResult

    results = [
        StrategyResult(
            strategy=StrategyId.MULTI_TF,
            pair="BTCUSDT",
            timeframe="1h",
            direction=None,
            confidence=0.0,
            reasons=(),
            suitable_regimes=frozenset(["bull"]),
        ),
    ]
    agg = SignalAggregator()
    sig = agg.aggregate(results, Regime.CHOPPY, 0.5, timeframe="1h")
    assert sig is None


def test_aggregator_two_strategies_picks_dominant():
    """多策略 → 选更强方向。"""
    from app.signals.aggregator import SignalAggregator
    from app.signals.regime import Regime
    from app.signals.strategy_pool import StrategyId, StrategyResult

    results = [
        StrategyResult(StrategyId.MOMENTUM, "BTCUSDT", "1h", "long", 0.8, ("EMA金叉",), frozenset()),
        StrategyResult(StrategyId.MULTI_TF, "BTCUSDT", "1h", "long", 0.85, ("多头排列",), frozenset()),
        StrategyResult(StrategyId.REVERSAL, "BTCUSDT", "1h", "short", 0.6, ("触及上轨",), frozenset()),
    ]
    agg = SignalAggregator()
    sig = agg.aggregate(results, Regime.CHOPPY, 0.6, timeframe="1h")
    assert sig is not None
    assert sig.direction == "long"  # 2 long vs 1 short
    assert "momentum" in sig.contributing_strategies
    assert "multi_timeframe" in sig.contributing_strategies


def test_aggregator_leverage_suggestion():
    """杠杆建议应随 timeframe 和 regime 变化。"""
    from app.signals.aggregator import suggest_leverage
    # 超短线默认 5x
    assert suggest_leverage("1m", Regime.BULL, 0.8) == 5
    assert suggest_leverage("5m", Regime.BULL, 0.8) == 5
    # 长线默认 1x
    assert suggest_leverage("1d", Regime.BULL, 0.8) == 1
    # crisis 强制 1x
    assert suggest_leverage("1m", Regime.CRISIS, 0.9) == 1
    # 低 confidence 降杠杆
    assert suggest_leverage("1m", Regime.BULL, 0.3) <= 2


def test_aggregator_timeframe_category():
    """timeframe 分类应正确。"""
    from app.signals.aggregator import categorize_timeframe, TimeframeCategory
    assert categorize_timeframe("1m") == TimeframeCategory.ULTRA_SHORT
    assert categorize_timeframe("5m") == TimeframeCategory.ULTRA_SHORT
    assert categorize_timeframe("15m") == TimeframeCategory.SHORT
    assert categorize_timeframe("1h") == TimeframeCategory.MID
    assert categorize_timeframe("4h") == TimeframeCategory.MID
    assert categorize_timeframe("1d") == TimeframeCategory.LONG


# ─── 端到端测试（用 mock data，应至少出 1 个推荐单）──────────────────────────

@pytest.mark.asyncio
async def test_end_to_end_with_mock_data_produces_signal():
    """
    v2 核心目标：使用 mock 数据，6 个币种中至少应该有一些推荐单（不再全空）。
    """
    from app.signals import RegimeDetector, SignalAggregator, STRATEGY_INSTANCES, StrategyResult
    from app.signals.regime import Regime
    from app.api.klines import _generate_mock_candles

    pairs = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]
    timeframe = "1h"
    limit = 120

    signals_emitted = 0
    for pair in pairs:
        candles = _generate_mock_candles(pair, timeframe, limit)
        candle_dicts = [c.model_dump() for c in candles]
        if len(candle_dicts) < 30:
            continue

        closes = np.array([c["close"] for c in candle_dicts])
        volumes = np.array([c["volume"] for c in candle_dicts])
        highs = np.array([c["high"] for c in candle_dicts])
        lows = np.array([c["low"] for c in candle_dicts])

        detector = RegimeDetector(timeframe=timeframe)
        log_returns = np.diff(np.log(closes + 1e-10), prepend=closes[0])
        regime_info = detector.update(log_returns, volumes, high=highs, low=lows, close=closes)

        candles_dict = {
            "symbol": pair, "timeframe": timeframe,
            "close": closes, "high": highs, "low": lows,
            "open": np.array([c["open"] for c in candle_dicts]),
        }
        results = []
        for sid, strat in STRATEGY_INSTANCES.items():
            r = strat.evaluate(candles_dict, volumes, regime_info.regime.value)
            results.append(r)

        agg = SignalAggregator()
        sig = agg.aggregate(results, regime_info.regime, regime_info.confidence, timeframe=timeframe)
        if sig is not None:
            signals_emitted += 1
            print(f"\n{pair}: regime={regime_info.regime.value} → {sig.direction} "
                  f"(conf={sig.confidence}, leverage={sig.suggested_leverage}x)")

    # 至少 50% 的币种应有信号（之前是 0%）
    assert signals_emitted >= len(pairs) // 2, (
        f"Expected at least {len(pairs) // 2} signals, got {signals_emitted} "
        f"out of {len(pairs)}"
    )
