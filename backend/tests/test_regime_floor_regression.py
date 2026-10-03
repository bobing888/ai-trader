"""Regression test: regime 评分 softmax 不应被 +0.05 floor 均匀化。

bug 现象 (kbkkk.com 生产环境 2026-10-03 验证):
  BTC 1h regime_probs = {bull: 0.27, bear: 0.29, choppy: 0.22, crisis: 0.22}
  → max probability 只到 0.297, 4 个值差距 < 0.07

根因:
  regime.py _score_regimes 末尾:
    scores = np.clip(scores, 0.0, None) + 0.05  # 平滑 floor
    exp = np.exp(scores - scores.max())
    probs = exp / exp.sum()
  → 4 个状态都被加 0.05 floor,即使 score=[1.0, 0.8, 0.2, 0.0],
    exp 也只输出 [e^0.95, e^0.75, e^0.15, e^0] → 拉不开差距

修复:
  - 撤掉 +0.05 floor (或 temperature-scaled softmax)
  - 改用 exp(scores / T) with T=0.3 拉大差距
"""
from __future__ import annotations

import numpy as np

from app.signals.regime import Regime, RegimeDetector


def _score_regimes(features, timeframe, **kw):
    """_score_regimes 是 RegimeDetector 的 @staticmethod, 通过类访问."""
    return RegimeDetector._score_regimes(features, timeframe, **kw)


def _bullish_candles(n: int = 100, seed: int = 42) -> dict:
    """构造 n 根 strong bull K 线: +0.3%/bar, ADX 强, Hurst 持续."""
    rng = np.random.default_rng(seed)
    base = 100.0
    closes = [base]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1.0 + 0.003 + rng.normal(0, 0.001)))
    closes = np.array(closes)
    highs = closes * (1.0 + 0.002)
    lows = closes * (1.0 - 0.002)
    return {
        "close": closes,
        "high": highs,
        "low": lows,
        "volume": np.ones(n) * 1000.0,
    }


def test_score_regimes_no_artificial_floor():
    """bull 信号应明显高于其他状态, max prob 至少 0.5."""
    features = np.zeros((30, 3))
    features[:, 0] = 0.005  # +0.5% log return per bar → 强 bull
    features[:, 1] = 0.005  # 适度 vol
    features[:, 2] = 1.0    # vol ratio

    probs, _, _ = _score_regimes(
        features, "1h",
        adx_val=30.0, pdi_val=28.0, ndi_val=12.0,   # 强 bull trend
        hurst_val=0.62,                             # 持续
    )

    max_prob = float(probs.max())
    bull_idx = 0  # [bull, bear, choppy, crisis]
    bull_prob = float(probs[bull_idx])
    second_max = float(np.partition(probs, -2)[-2])

    # 强 bull 信号 → bull 应该是最大且明显领先
    assert bull_prob == max_prob, f"bull should be max, got probs={probs}"
    assert bull_prob >= 0.5, f"bull_prob={bull_prob:.3f} 应 ≥ 0.5, 实际过弱"
    assert bull_prob > second_max * 1.4, (
        f"bull_prob={bull_prob:.3f} vs second_max={second_max:.3f} "
        f"差距 < 1.4x, 仍被 +0.05 floor 拉平"
    )


def test_regime_detector_strong_bull_outputs_high_bull_confidence():
    """强 bull 数据 → RegimeInfo.confidence (winner) 应 ≥ 0.5."""
    candles = _bullish_candles(120, seed=42)
    returns = np.diff(np.log(candles["close"]), prepend=candles["close"][0])

    detector = RegimeDetector(timeframe="1h")
    info = detector.update(returns, candles["volume"], candles["high"], candles["low"], candles["close"])

    bull_prob = info.regime_probs[__import__("app.signals.regime", fromlist=["Regime"]).Regime.BULL]
    assert info.regime.value == "bull", f"expected bull, got {info.regime.value}"
    assert bull_prob >= 0.5, f"BULL prob={bull_prob:.3f} 过弱, 当前是 {info.regime_probs}"
