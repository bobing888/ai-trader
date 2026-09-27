"""趋势强度指标 — ADX + +DI / -DI + MACD + SMA + 多指标共振"""

from __future__ import annotations

import numpy as np
from typing import Literal


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


def _ema(values: np.ndarray, period: int) -> np.ndarray:
    """指数移动平均（纯 numpy 实现）。"""
    k = 2 / (period + 1)
    out = np.zeros_like(values, dtype=np.float64)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = k * values[i] + (1 - k) * out[i - 1]
    return out


def macd(close: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """经典 MACD: EMA(fast) - EMA(slow) → macd_line; macd_line 的 EMA(signal) → signal_line; diff → histogram."""
    ema_fast_arr = _ema(close.astype(np.float64), fast)
    ema_slow_arr = _ema(close.astype(np.float64), slow)
    macd_line = ema_fast_arr - ema_slow_arr
    signal_line = _ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def sma(close: np.ndarray, period: int = 30) -> np.ndarray:
    """简单移动平均（SMA）。前 period-1 个点为 nan。"""
    n = len(close)
    out = np.full(n, np.nan, dtype=np.float64)
    if n < period:
        return out
    out[period - 1] = np.mean(close[:period])
    for i in range(period, n):
        out[i] = out[i - 1] + (close[i] - close[i - period]) / period
    return out


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


def derive_signal_direction(
    ma30_state: str,
    macd_status: str,
    rsi_zone: str,
    pdi: float,
    ndi: float,
) -> Literal["long", "short", "mixed"]:
    """
    从子指标组合推导方向信号。

    Long 票（+1）：
      - MA30 is above / cross_above
      - MACD is bullish_cross / above_zero
      - RSI is neutral or oversold (oversold = 空头过度，有反弹潜力)
      - PDI > NDI（明确多头动能）

    Short 票（-1）：
      - MA30 is below / cross_below
      - MACD is bearish_cross / below_zero
      - RSI is overbought（多头过度，有回调风险）
      - PDI < NDI（明确空头动能）

    规则：
      - >= 3 票同向 → 该方向
      - RSI overbought 强力否决 long（防追高）
      - PDI <= NDI 时否决 long（无方向动能则不追）
      - PDI >= NDI 时否决 short（无空头动能则不做空）
      - 否则 → mixed
    """
    long_votes = 0
    short_votes = 0

    # MA30
    if ma30_state in ("above", "cross_above"):
        long_votes += 1
    elif ma30_state in ("below", "cross_below"):
        short_votes += 1

    # MACD
    if macd_status in ("bullish_cross", "above_zero"):
        long_votes += 1
    elif macd_status in ("bearish_cross", "below_zero"):
        short_votes += 1

    # RSI zone
    if rsi_zone == "neutral":
        long_votes += 1
    elif rsi_zone == "oversold":
        long_votes += 1
    elif rsi_zone == "overbought":
        short_votes += 1

    # ADX PDI vs NDI — 仅在有明确方向时计票
    if pdi > ndi:
        long_votes += 1
    elif ndi > pdi:
        short_votes += 1
    # PDI == NDI → 无方向票

    # Veto: RSI overbought 强力否决 long
    if rsi_zone == "overbought" and long_votes >= 3:
        return "mixed"

    # Veto: PDI <= NDI 时否决 long（无多头动能则不追）
    if pdi <= ndi and long_votes >= 3:
        return "mixed"

    # Veto: PDI >= NDI 时否决 short（无空头动能则不做空）
    if pdi >= ndi and short_votes >= 3:
        return "mixed"

    if long_votes >= 3:
        return "long"
    elif short_votes >= 3:
        return "short"
    else:
        return "mixed"


def multi_indicator_confluence(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
) -> dict:
    """多指标共振评分 — 返回所有子指标 + Confluence Score (0–100)。"""
    close = close.astype(np.float64)
    high = high.astype(np.float64)
    low = low.astype(np.float64)
    volume = volume.astype(np.float64)

    n = len(close)
    ma30_arr = sma(close, 30)

    # MA30 当前值与位置
    ma30_val = float(ma30_arr[-1]) if not np.isnan(ma30_arr[-1]) else None
    price = float(close[-1])
    if ma30_val is None:
        price_vs_ma30 = "insufficient_data"
    else:
        diff_pct = (price - ma30_val) / ma30_val * 100 if ma30_val != 0 else 0.0
        if diff_pct > 3:
            price_vs_ma30 = "above"
        elif diff_pct < -3:
            price_vs_ma30 = "below"
        else:
            # 检查前 3 根是否穿越
            if n >= 3:
                prev_2 = float(close[-3])
                prev_1 = float(close[-2])
                prev_3_ma = float(ma30_arr[-3]) if not np.isnan(ma30_arr[-3]) else ma30_val
                prev_2_ma = float(ma30_arr[-2]) if not np.isnan(ma30_arr[-2]) else ma30_val
                prev_1_ma = float(ma30_arr[-1]) if not np.isnan(ma30_arr[-1]) else ma30_val
                if prev_2 < prev_2_ma and prev_1 > prev_1_ma and price > ma30_val:
                    price_vs_ma30 = "cross_above"
                elif prev_2 > prev_2_ma and prev_1 < prev_1_ma and price < ma30_val:
                    price_vs_ma30 = "cross_below"
                else:
                    price_vs_ma30 = "above" if price > ma30_val else "below"
            else:
                price_vs_ma30 = "above" if price > ma30_val else "below"

    # MACD
    macd_line, signal_line, histogram = macd(close)
    macd_val = float(macd_line[-1]) if not np.isnan(macd_line[-1]) else 0.0
    signal_val = float(signal_line[-1]) if not np.isnan(signal_line[-1]) else 0.0
    hist_val = float(histogram[-1]) if not np.isnan(histogram[-1]) else 0.0

    # MACD 金叉/死叉（前 3 根内）
    macd_status = "below_zero"
    if n >= 2:
        prev_macd = float(macd_line[-2]) if not np.isnan(macd_line[-2]) else macd_val
        prev_signal = float(signal_line[-2]) if not np.isnan(signal_line[-2]) else signal_val
        if prev_macd <= prev_signal and macd_val > signal_val:
            if n >= 3:
                prev2_macd = float(macd_line[-3]) if not np.isnan(macd_line[-3]) else prev_macd
                prev2_signal = float(signal_line[-3]) if not np.isnan(signal_line[-3]) else prev_signal
                if prev2_macd <= prev2_signal:
                    macd_status = "bullish_cross"
                else:
                    macd_status = "above_zero"
            else:
                macd_status = "bullish_cross"
        elif prev_macd >= prev_signal and macd_val < signal_val:
            if n >= 3:
                prev2_macd = float(macd_line[-3]) if not np.isnan(macd_line[-3]) else prev_macd
                prev2_signal = float(signal_line[-3]) if not np.isnan(signal_line[-3]) else prev_signal
                if prev2_macd >= prev2_signal:
                    macd_status = "bearish_cross"
                else:
                    macd_status = "below_zero"
            else:
                macd_status = "bearish_cross"
        elif macd_val > 0:
            macd_status = "above_zero"
        else:
            macd_status = "below_zero"

    # 布林带（用 sma 重用）
    period_bb = 20
    sma_arr = sma(close, period_bb)
    std_arr = np.array([np.std(close[max(0, i - period_bb + 1):i + 1]) for i in range(n)], dtype=np.float64)
    upper = sma_arr + 2 * std_arr
    mid = sma_arr
    lower = sma_arr - 2 * std_arr
    bb_upper_val = float(upper[-1]) if not np.isnan(upper[-1]) else price
    bb_mid_val = float(mid[-1]) if not np.isnan(mid[-1]) else price
    bb_lower_val = float(lower[-1]) if not np.isnan(lower[-1]) else price
    if price > bb_upper_val:
        bb_position = "above_upper"
    elif price < bb_lower_val:
        bb_position = "below_lower"
    elif price > bb_mid_val:
        bb_position = "inside_upper"
    else:
        bb_position = "inside_lower"

    # RSI
    def _rsi(prices: np.ndarray, period_r: int = 14) -> np.ndarray:
        deltas = np.diff(prices, prepend=prices[0])
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        avg_gain = np.zeros_like(prices, dtype=np.float64)
        avg_loss = np.zeros_like(prices, dtype=np.float64)
        if len(prices) <= period_r:
            return np.full(len(prices), np.nan)
        avg_gain[period_r] = np.mean(gains[1:period_r + 1])
        avg_loss[period_r] = np.mean(losses[1:period_r + 1])
        for i in range(period_r + 1, len(prices)):
            avg_gain[i] = (avg_gain[i - 1] * (period_r - 1) + gains[i]) / period_r
            avg_loss[i] = (avg_loss[i - 1] * (period_r - 1) + losses[i]) / period_r
        rs = avg_gain / (avg_loss + 1e-10)
        return 100 - 100 / (1 + rs)

    rsi_arr = _rsi(close)
    rsi_val = float(rsi_arr[-1]) if not np.isnan(rsi_arr[-1]) else 50.0
    if rsi_val > 70:
        rsi_zone = "overbought"
    elif rsi_val < 30:
        rsi_zone = "oversold"
    else:
        rsi_zone = "neutral"

    # ADX（复用 trend_strength 逻辑）
    adx_arr, pdi_arr, ndi_arr = adx(high, low, close, 14)
    adx_val = float(adx_arr[-1]) if not np.isnan(adx_arr[-1]) else 0.0
    pdi_val = float(pdi_arr[-1]) if not np.isnan(pdi_arr[-1]) else 0.0
    ndi_val = float(ndi_arr[-1]) if not np.isnan(ndi_arr[-1]) else 0.0
    adx_dict = {"adx": round(adx_val, 2), "pdi": round(pdi_val, 2), "ndi": round(ndi_val, 2)}

    # Volume ratio
    vol_ma20_arr = sma(volume, 20)
    vol_ma20_val = float(vol_ma20_arr[-1]) if not np.isnan(vol_ma20_arr[-1]) and vol_ma20_arr[-1] > 0 else 1.0
    volume_ratio = round(float(volume[-1]) / vol_ma20_val, 3) if vol_ma20_val > 0 else 1.0

    # ── Confluence Score ──────────────────────────────────────────────────────────
    score = 0
    bullish_count = 0
    bearish_count = 0

    # 1. 价格在 MA30 上方 +10，价格在 MA30 上方 1–3% 额外 +5
    if ma30_val is not None and ma30_val > 0:
        diff_pct = (price - ma30_val) / ma30_val * 100
        if price > ma30_val:
            score += 10
            bullish_count += 1
            if 1.0 <= diff_pct <= 3.0:
                score += 5
        elif price < ma30_val:
            bearish_count += 1
    else:
        score += 5  # 数据不足时给中性分

    # 2. MACD 金叉 +15，MACD 在零线上方 +10
    if macd_status == "bullish_cross":
        score += 15
        bullish_count += 1
    elif macd_status == "above_zero":
        score += 10
        bullish_count += 1
    elif macd_status == "bearish_cross":
        bearish_count += 1

    # 3. 布林带：价格在内部 + 价格在中轨附近 +5
    if bb_position in ("inside_upper", "inside_lower"):
        score += 5
        # 价格在中轨附近（±2%）
        if bb_mid_val > 0:
            mid_diff = abs(price - bb_mid_val) / bb_mid_val * 100
            if mid_diff <= 2.0:
                score += 5
                if price > bb_mid_val:
                    bullish_count += 1
                else:
                    bearish_count += 1

    # 4. RSI 50–70 +10（多头区）；RSI 30–50 +10（空头区）
    if 50 <= rsi_val <= 70:
        score += 10
        bullish_count += 1
    elif 30 <= rsi_val < 50:
        score += 10
        bearish_count += 1

    # 5. ADX > 25 且趋势方向与价格方向一致 +10
    if adx_val > 25:
        trend_dir = "long" if pdi_val > ndi_val else "short"
        if trend_dir == "long" and price > (ma30_val or price):
            score += 10
            bullish_count += 1
        elif trend_dir == "short" and price < (ma30_val or price):
            score += 10
            bearish_count += 1

    # 6. Volume ratio 1.0–1.5 健康放量 +10；>1.5 异常放量 +5
    if 1.0 <= volume_ratio <= 1.5:
        score += 10
    elif volume_ratio > 1.5:
        score += 5

    # 7. 多空共振大奖：方向一致 +10，不一致则扣 5
    if bullish_count > 0 and bearish_count == 0:
        score += 10
    elif bearish_count > 0 and bullish_count == 0:
        score += 10  # 一致方向也加分
    elif bullish_count > 0 and bearish_count > 0:
        score -= 5

    confluence_score = max(0, min(100, score))

    # 从子指标推导方向
    direction = derive_signal_direction(
        ma30_state=price_vs_ma30,
        macd_status=macd_status,
        rsi_zone=rsi_zone,
        pdi=pdi_val,
        ndi=ndi_val,
    )

    return {
        "ma30": ma30_val,
        "price_vs_ma30": price_vs_ma30,
        "macd": {
            "macd_value": round(macd_val, 4),
            "signal_value": round(signal_val, 4),
            "histogram": round(hist_val, 4),
            "status": macd_status,
        },
        "bollinger": {
            "upper": round(bb_upper_val, 4),
            "mid": round(bb_mid_val, 4),
            "lower": round(bb_lower_val, 4),
            "position": bb_position,
        },
        "rsi14": {
            "value": round(rsi_val, 2),
            "zone": rsi_zone,
        },
        "adx14": adx_dict,
        "volume_ratio": volume_ratio,
        "confluence_score": confluence_score,
        "signal_direction": direction,
    }
