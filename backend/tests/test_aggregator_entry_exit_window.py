"""Test aggregator entry/exit window fields — 用户挂在看板上的时间指引。

每个 timeframe 一个 entry/exit window（分钟），基于 timeframe 推 N 根 K 线：
  - 5m  → entry=5min, exit=15min (3 根)
  - 15m → entry=15min, exit=60min (4 根)
  - 1h  → entry=60min, exit=240min (4 根)
  - 1d  → entry=1440min, exit=4320min (3 根)

D1 ATR 计算不可用时（缺 candles/price）→ 字段 = None。
"""
from __future__ import annotations

from app.signals.aggregator import AggregatedSignal


# ── 1. dataclass 字段存在性 + 默认值 ────────────────────────────────────────────

def test_aggregated_signal_has_entry_exit_window_fields():
    sig = AggregatedSignal(
        pair="BTC-USDT",
        direction="long",
        confidence=0.7,
        contributing_strategies=["MomentumStrategy"],
        reasons=["test"],
        regime="bull",
        regime_confidence=0.8,
        entry_zones=[],
        risk_warnings=[],
    )
    # 默认值：未算 D1 时应该是 None
    assert hasattr(sig, "entry_window_minutes"), "missing entry_window_minutes field"
    assert hasattr(sig, "exit_window_minutes"), "missing exit_window_minutes field"
    assert sig.entry_window_minutes is None
    assert sig.exit_window_minutes is None


def test_aggregated_signal_with_window_fields_set():
    sig = AggregatedSignal(
        pair="BTC-USDT",
        direction="long",
        confidence=0.7,
        contributing_strategies=[],
        reasons=[],
        regime="bull",
        regime_confidence=0.8,
        entry_zones=[],
        risk_warnings=[],
        entry_window_minutes=60,
        exit_window_minutes=240,
    )
    assert sig.entry_window_minutes == 60
    assert sig.exit_window_minutes == 240


# ── 2. SignalAggregator 实际产出 entry/exit window ──────────────────────────────

def _candles(n: int = 80):
    """构造简单上涨趋势 candles（ATR 可算）。"""
    out = []
    price = 65000.0
    for i in range(n):
        # 每根 +50 / 上下 30
        o = price
        c = price + 50
        h = c + 30
        l = o - 30
        out.append({
            "open_time": i * 60_000,
            "open": o, "high": h, "low": l, "close": c,
            "volume": 100.0,
        })
        price = c
    return out


def test_aggregator_emits_window_for_5m():
    """5m 推荐 1h — entry=5min, exit=15min。"""
    from app.signals.aggregator import SignalAggregator
    from app.signals.regime import Regime, RegimeDetector
    from app.signals.strategy_pool import STRATEGY_INSTANCES

    candles = _candles(80)
    regime_info = RegimeDetector().detect(candles, "5m")
    candles_dict = {
        "symbol": "BTC-USDT",
        "timeframe": "5m",
        "close": [c["close"] for c in candles],
        "open": [c["open"] for c in candles],
        "high": [c["high"] for c in candles],
        "low": [c["low"] for c in candles],
    }
    import numpy as np
    volumes = np.array([c["volume"] for c in candles], dtype=np.float64)
    strategy_results = [
        s.evaluate(candles_dict, volumes, regime_info.regime.value)
        for s in STRATEGY_INSTANCES.values()
    ]

    ohlcv = [
        {"open_time": c["open_time"], "open": c["open"], "high": c["high"],
         "low": c["low"], "close": c["close"], "volume": c["volume"]}
        for c in candles
    ]
    sig = SignalAggregator().aggregate(
        strategy_results,
        regime_info.regime,
        regime_info.confidence,
        "5m",
        candles_dict={"BTC-USDT": ohlcv},
        current_price={"BTC-USDT": candles[-1]["close"]},
    )
    assert sig.entry_window_minutes == 5, f"5m entry expected 5min, got {sig.entry_window_minutes}"
    assert sig.exit_window_minutes == 15, f"5m exit expected 15min, got {sig.exit_window_minutes}"


def test_aggregator_emits_window_for_1h():
    """1h → entry=60min, exit=240min。"""
    from app.signals.aggregator import SignalAggregator
    from app.signals.regime import Regime, RegimeDetector
    from app.signals.strategy_pool import STRATEGY_INSTANCES
    import numpy as np

    candles = _candles(80)
    regime_info = RegimeDetector().detect(candles, "1h")
    candles_dict = {
        "symbol": "BTC-USDT",
        "timeframe": "1h",
        "close": [c["close"] for c in candles],
        "open": [c["open"] for c in candles],
        "high": [c["high"] for c in candles],
        "low": [c["low"] for c in candles],
    }
    volumes = np.array([c["volume"] for c in candles], dtype=np.float64)
    strategy_results = [
        s.evaluate(candles_dict, volumes, regime_info.regime.value)
        for s in STRATEGY_INSTANCES.values()
    ]
    ohlcv = [
        {"open_time": c["open_time"], "open": c["open"], "high": c["high"],
         "low": c["low"], "close": c["close"], "volume": c["volume"]}
        for c in candles
    ]
    sig = SignalAggregator().aggregate(
        strategy_results,
        regime_info.regime,
        regime_info.confidence,
        "1h",
        candles_dict={"BTC-USDT": ohlcv},
        current_price={"BTC-USDT": candles[-1]["close"]},
    )
    assert sig.entry_window_minutes == 60
    assert sig.exit_window_minutes == 240


def test_aggregator_window_none_when_no_candles():
    """缺 candles → entry/exit window 应为 None（与其他 D1 字段一致）。"""
    from app.signals.aggregator import SignalAggregator
    from app.signals.regime import Regime, RegimeDetector
    from app.signals.strategy_pool import STRATEGY_INSTANCES
    import numpy as np

    candles = _candles(80)
    regime_info = RegimeDetector().detect(candles, "1h")
    candles_dict = {
        "symbol": "BTC-USDT",
        "timeframe": "1h",
        "close": [c["close"] for c in candles],
        "open": [c["open"] for c in candles],
        "high": [c["high"] for c in candles],
        "low": [c["low"] for c in candles],
    }
    volumes = np.array([c["volume"] for c in candles], dtype=np.float64)
    strategy_results = [
        s.evaluate(candles_dict, volumes, regime_info.regime.value)
        for s in STRATEGY_INSTANCES.values()
    ]
    sig = SignalAggregator().aggregate(
        strategy_results,
        regime_info.regime,
        regime_info.confidence,
        "1h",
        candles_dict={},   # 空 → 不算 ATR
        current_price={"BTC-USDT": candles[-1]["close"]},
    )
    assert sig.entry_window_minutes is None
    assert sig.exit_window_minutes is None