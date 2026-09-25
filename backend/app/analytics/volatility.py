"""波动率分位数指标 — ATR + 历史分位"""

import numpy as np


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """ATR (Wilder 平滑)"""
    n = len(close)
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    out = np.full(n, np.nan)
    if n <= period:
        return out
    out[period] = np.mean(tr[1:period + 1])
    for i in range(period + 1, n):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out


def volatility_percentile(close: np.ndarray, high: np.ndarray, low: np.ndarray, period: int = 14, lookback: int = 8760) -> dict:
    """当前 ATR/close 的分位数（vs 过去 lookback 根 K 线的 ATR 分布）

    Args:
        lookback: 历史窗口（默认 8760 ≈ 1 年 1h K 线）
    """
    a = atr(high, low, close, period)
    if np.all(np.isnan(a)):
        return {"current_atr_pct": 0.0, "percentile_1y": 0.5, "level": "数据不足"}

    cur = float(a[-1])
    cur_pct = cur / close[-1] if close[-1] > 0 else 0.0

    # 历史分位
    sample = a[~np.isnan(a)][-lookback:]
    if len(sample) < 10:
        return {"current_atr_pct": round(cur_pct, 4), "percentile_1y": 0.5, "level": "数据不足"}
    pct = float((sample < cur).sum() / len(sample))

    if pct < 0.2:
        level = "极低（平静）"
    elif pct < 0.4:
        level = "偏低"
    elif pct < 0.6:
        level = "正常"
    elif pct < 0.8:
        level = "偏高"
    else:
        level = "极高（异常波动）"

    return {
        "current_atr_pct": round(cur_pct, 4),
        "current_atr": round(cur, 2),
        "percentile_1y": round(pct, 3),
        "level": level,
    }
