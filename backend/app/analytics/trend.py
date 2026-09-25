"""趋势强度指标 — ADX + +DI / -DI"""

import numpy as np


def adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """标准 Wilder 平滑的 ADX + PDI + NDI。"""
    n = len(close)
    tr = np.zeros(n)
    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)

    for i in range(1, n):
        up = high[i] - high[i - 1]
        dn = low[i - 1] - low[i]
        plus_dm[i] = up if up > dn and up > 0 else 0.0
        minus_dm[i] = dn if dn > up and dn > 0 else 0.0
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))

    # Wilder 平滑（递推）
    atr = np.zeros(n)
    sp_dm = np.zeros(n)
    sn_dm = np.zeros(n)
    if n <= period:
        return np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan)
    # 初值用 period 根的简单平均
    atr[period] = np.mean(tr[1:period + 1])
    sp_dm[period] = np.mean(plus_dm[1:period + 1])
    sn_dm[period] = np.mean(minus_dm[1:period + 1])

    for i in range(period + 1, n):
        atr[i] = atr[i - 1] - atr[i - 1] / period + tr[i]
        sp_dm[i] = sp_dm[i - 1] - sp_dm[i - 1] / period + plus_dm[i]
        sn_dm[i] = sn_dm[i - 1] - sn_dm[i - 1] / period + minus_dm[i]

    pdi = np.where(atr > 0, 100 * sp_dm / np.where(atr == 0, 1, atr), 0.0)
    ndi = np.where(atr > 0, 100 * sn_dm / np.where(atr == 0, 1, atr), 0.0)
    dx = np.where((pdi + ndi) > 0, 100 * np.abs(pdi - ndi) / np.where(pdi + ndi == 0, 1, pdi + ndi), 0.0)

    adx_arr = np.full(n, np.nan)
    if n > 2 * period:
        # ADX = Wilder smoothed DX
        adx_arr[2 * period] = np.nanmean(dx[period:2 * period])
        for i in range(2 * period + 1, n):
            adx_arr[i] = (adx_arr[i - 1] * (period - 1) + dx[i]) / period

    return adx_arr, pdi, ndi


def trend_strength(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> dict:
    """返回当前最新点的 ADX 趋势强度分析"""
    a, p, n = adx(high, low, close, period)
    if np.all(np.isnan(a)):
        return {"adx": 0.0, "pdi": 0.0, "ndi": 0.0, "strength_label": "数据不足"}
    adx_now = float(a[-1]) if not np.isnan(a[-1]) else 0.0
    pdi_now = float(p[-1]) if not np.isnan(p[-1]) else 0.0
    ndi_now = float(n[-1]) if not np.isnan(n[-1]) else 0.0

    if adx_now < 15:
        label = "无趋势"
    elif adx_now < 25:
        label = "弱趋势"
    elif adx_now < 50:
        label = "中等趋势"
    elif adx_now < 75:
        label = "强趋势"
    else:
        label = "极强趋势"

    direction = "long" if pdi_now > ndi_now else "short"
    return {
        "adx": round(adx_now, 2),
        "pdi": round(pdi_now, 2),
        "ndi": round(ndi_now, 2),
        "strength_label": label,
        "direction": direction,
    }
