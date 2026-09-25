"""统计套利指标 — Hurst 指数 + 分形维数 + Shannon 熵"""

import math

import numpy as np


def hurst_exponent(prices: np.ndarray, max_lag: int = 20) -> float:
    """Rescaled Range (R/S) 方法估算 Hurst 指数 H

    H < 0.5: 均值回归（反持续）
    H = 0.5: 随机游走
    H > 0.5: 趋势持续（长记忆）

    Returns: H ∈ [0, 1]
    """
    prices = np.asarray(prices, dtype=np.float64)
    n = len(prices)
    if n < 50:
        return 0.5  # 数据不足时默认随机游走

    log_prices = np.log(prices + 1e-10)
    lags = range(2, min(max_lag, n // 2))
    tau = []
    for lag in lags:
        # 切片成 lag 长度的子序列
        n_segments = n // lag
        if n_segments < 2:
            continue
        rs_values = []
        for i in range(n_segments):
            seg = log_prices[i * lag:(i + 1) * lag]
            mean_seg = seg.mean()
            cumulative_deviation = seg - mean_seg
            cumulative = cumulative_deviation.cumsum()
            r = cumulative.max() - cumulative.min()
            s = seg.std()
            if s > 1e-10:
                rs_values.append(r / s)
        if rs_values:
            tau.append(np.log(np.mean(rs_values)))
    if len(tau) < 3:
        return 0.5
    lags_log = [math.log(l) for l in lags[:len(tau)]]
    # 线性回归 slope = H
    coeffs = np.polyfit(lags_log, tau, 1)
    h = float(coeffs[0])
    return max(0.0, min(1.0, h))


def fractal_dimension(prices: np.ndarray, max_lag: int = 20) -> float:
    """Higuchi 分形维数 D = 2 - H (近似)。

    D ∈ [1, 2]。越大越不规则。
    """
    h = hurst_exponent(prices, max_lag)
    return 2.0 - h


def shannon_entropy(prices: np.ndarray, bins: int = 20) -> float:
    """价格分箱后的 Shannon 信息熵 H = -Σ p_i log2(p_i)

    H ∈ [0, log2(bins)]。越大说明价格分布越均匀 / 信息复杂度越高。
    """
    prices = np.asarray(prices, dtype=np.float64)
    if len(prices) < bins:
        return 0.0
    hist, _ = np.histogram(prices, bins=bins)
    total = hist.sum()
    if total == 0:
        return 0.0
    probs = hist / total
    probs = probs[probs > 0]
    return float(-np.sum(probs * np.log2(probs)))


def rsi_score(prices: np.ndarray, period: int = 14) -> float:
    """RSI 反向情绪分 (0-100)

    RSI < 30 → 100 (超卖，逆向买入机会)
    RSI > 70 → 0 (超买，逆向卖出机会)
    RSI = 50 → 50 (中性)
    线性映射。
    """
    prices = np.asarray(prices, dtype=np.float64)
    n = len(prices)
    if n < period + 1:
        return 50.0

    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_g = np.mean(gains[:period])
    avg_l = np.mean(losses[:period])
    for i in range(period, len(deltas)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
    rs = avg_g / (avg_l + 1e-10)
    rsi = 100 - 100 / (1 + rs)

    # 反向映射: rsi=70 → 0, rsi=30 → 100, rsi=50 → 50
    score = 100 - (rsi - 30) * (100 / (70 - 30))
    return max(0.0, min(100.0, score))
