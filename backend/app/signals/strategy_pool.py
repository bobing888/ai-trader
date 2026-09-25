"""
推荐单引擎 — Strategy Pool
7 个策略骨架，各自对应不同的市场状态和信号类型
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

import numpy as np


class StrategyId(Enum):
    """策略唯一标识"""
    MOMENTUM = "momentum"           # 趋势跟踪（适用于 BULL）
    REVERSAL = "mean_reversion"     # 均值回归（适用于 CHOPPY）
    BREAKOUT = "breakout"           # 突破策略（适用于 BULL/CHOPPY 边界）
    VOLATILITY = "volatility_bands" # 波动率通道（适用于 CRISIS）
    SENTIMENT = "sentiment"          # 情绪反向（适用于 BEAR）
    VOLUME = "volume_profile"       # 量价共振（通用）
    MULTI_TF = "multi_timeframe"   # 多周期共振（通用，信号质量最高）


@dataclass(frozen=True, slots=True)
class StrategySignal:
    strategy: StrategyId
    direction: str          # "long" | "short"
    strength: float         # 0.0–1.0
    reasons: tuple[str, ...]  # 信号理由列表


@dataclass
class StrategyResult:
    strategy: StrategyId
    pair: str
    timeframe: str
    direction: str | None   # None = 无信号
    confidence: float       # 0.0–1.0
    reasons: tuple[str, ...]
    suitable_regimes: frozenset[str]  # 适合的市场状态


class Strategy(Protocol):
    """策略接口"""
    def evaluate(self, candles: dict, volumes: np.ndarray, regime: str) -> StrategyResult: ...


# ─── 基础工具函数 ─────────────────────────────────────────────────────────────

def ema(values: np.ndarray, period: int) -> np.ndarray:
    k = 2 / (period + 1)
    out = np.zeros_like(values, dtype=np.float64)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = k * values[i] + (1 - k) * out[i - 1]
    return out


def rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
    deltas = np.diff(prices, prepend=prices[0])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.zeros_like(prices)
    avg_loss = np.zeros_like(prices)
    avg_gain[period] = np.mean(gains[1:period+1])
    avg_loss[period] = np.mean(losses[1:period+1])
    for i in range(period + 1, len(prices)):
        avg_gain[i] = (avg_gain[i-1] * (period - 1) + gains[i]) / period
        avg_loss[i] = (avg_loss[i-1] * (period - 1) + losses[i]) / period
    rs = avg_gain / (avg_loss + 1e-10)
    return 100 - 100 / (1 + rs)


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    tr = np.maximum(high[1:] - low[1:], np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1]))
    tr = np.concatenate([[tr[0] if len(tr) > 0 else 0], tr])
    atr = np.zeros_like(tr)
    atr[period] = np.mean(tr[1:period+1])
    for i in range(period + 1, len(tr)):
        atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period
    return atr


def bollinger_bands(close: np.ndarray, period: int = 20, num_std: float = 2.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ma = np.convolve(close, np.ones(period)/period, mode="same")
    std = np.array([np.std(close[max(0,i-period):i+1]) for i in range(len(close))])
    return ma, ma + num_std * std, ma - num_std * std


def volume_profile(volumes: np.ndarray, prices: np.ndarray, bins: int = 20) -> dict:
    """返回价格区间成交量分布"""
    price_range = np.linspace(prices.min(), prices.max(), bins + 1)
    counts, _ = np.histogram(prices, bins=price_range, weights=volumes)
    peak_idx = int(np.argmax(counts))
    return {
        "poc": float((price_range[peak_idx] + price_range[peak_idx+1]) / 2),
        "value_area_high": float(price_range[peak_idx + min(3, bins - peak_idx)]),
        "value_area_low": float(price_range[max(0, peak_idx - 3)]),
    }


# ─── 策略实现 ────────────────────────────────────────────────────────────────

class MomentumStrategy:
    """趋势跟踪：EMA 金叉/死叉 + RSI 确认"""
    ID = StrategyId.MOMENTUM

    def evaluate(self, candles: dict, volumes: np.ndarray, regime: str) -> StrategyResult:
        close = np.array(candles["close"], dtype=np.float64)
        ema_fast = ema(close, 9)
        ema_slow = ema(close, 21)
        rsi_val = rsi(close, 14)[-1]
        prev_fast = ema_fast[-2]
        prev_slow = ema_slow[-2]

        reasons = []
        direction = None
        confidence = 0.0

        golden_cross = prev_fast <= prev_slow and ema_fast[-1] > ema_slow[-1]
        death_cross = prev_fast >= prev_slow and ema_fast[-1] < ema_slow[-1]

        if regime in ("bull", "choppy") and golden_cross:
            direction = "long"
            reasons.append(f"EMA({9}) 金叉 EMA({21})")
            confidence = 0.7 + (rsi_val - 50) / 500 if 50 < rsi_val < 70 else 0.7
        elif regime == "bear" and death_cross:
            direction = "short"
            reasons.append(f"EMA({9}) 死叉 EMA({21})")
            confidence = 0.6 + (50 - rsi_val) / 500 if 30 < rsi_val < 50 else 0.6

        if rsi_val > 70:
            reasons.append(f"RSI({14})={rsi_val:.0f} 超买")
            confidence *= 0.8
        elif rsi_val < 30:
            reasons.append(f"RSI({14})={rsi_val:.0f} 超卖")
            confidence *= 0.8

        return StrategyResult(
            strategy=self.ID,
            pair=candles.get("symbol", "UNKNOWN"),
            timeframe=candles.get("timeframe", "1h"),
            direction=direction,
            confidence=max(0, min(1, confidence)),
            reasons=tuple(reasons),
            suitable_regimes=frozenset(["bull", "choppy"]),
        )


class MeanReversionStrategy:
    """均值回归：布林带 + RSI"""
    ID = StrategyId.REVERSAL

    def evaluate(self, candles: dict, volumes: np.ndarray, regime: str) -> StrategyResult:
        close = np.array(candles["close"], dtype=np.float64)
        ma, upper, lower = bollinger_bands(close)
        rsi_val = rsi(close, 14)[-1]
        price = close[-1]
        bandwidth = (upper[-1] - lower[-1]) / ma[-1]

        reasons = []
        direction = None
        confidence = 0.5

        if price < lower[-1] and rsi_val < 35:
            direction = "long"
            reasons.append(f"价格触及布林下轨 ({price:.2f} < {lower[-1]:.2f})")
            confidence = 0.75
        elif price > upper[-1] and rsi_val > 65:
            direction = "short"
            reasons.append(f"价格触及布林上轨 ({price:.2f} > {upper[-1]:.2f})")
            confidence = 0.75

        if bandwidth < 0.03:
            reasons.append(f"布林带收窄 (带宽={bandwidth:.3f})，突破在即")

        return StrategyResult(
            strategy=self.ID,
            pair=candles.get("symbol", "UNKNOWN"),
            timeframe=candles.get("timeframe", "1h"),
            direction=direction,
            confidence=max(0, min(1, confidence)),
            reasons=tuple(reasons),
            suitable_regimes=frozenset(["choppy", "bull"]),
        )


class BreakoutStrategy:
    """突破策略：区间高点/低点 + 成交量确认"""
    ID = StrategyId.BREAKOUT

    def evaluate(self, candles: dict, volumes: np.ndarray, regime: str) -> StrategyResult:
        close = np.array(candles["close"], dtype=np.float64)
        high = np.array(candles["high"], dtype=np.float64)
        low = np.array(candles["low"], dtype=np.float64)
        lookback = 20
        recent_high = np.max(high[-lookback:-1])
        recent_low = np.min(low[-lookback:-1])
        vol_ma20 = np.convolve(volumes, np.ones(20)/20, mode="valid")
        vol_ratio = float(volumes[-1] / vol_ma20[-1]) if vol_ma20[-1] > 0 else 1.0

        reasons = []
        direction = None
        confidence = 0.0

        price = close[-1]
        if price > recent_high and vol_ratio > 1.3:
            direction = "long"
            reasons.append(f"突破 {lookback} 日高点 ({price:.2f} > {recent_high:.2f})")
            reasons.append(f"成交量放大 ({vol_ratio:.1f}x 均量)")
            confidence = 0.75
        elif price < recent_low and vol_ratio > 1.3:
            direction = "short"
            reasons.append(f"跌破 {lookback} 日低点 ({price:.2f} < {recent_low:.2f})")
            reasons.append(f"成交量放大 ({vol_ratio:.1f}x 均量)")
            confidence = 0.75

        return StrategyResult(
            strategy=self.ID,
            pair=candles.get("symbol", "UNKNOWN"),
            timeframe=candles.get("timeframe", "1h"),
            direction=direction,
            confidence=max(0, min(1, confidence)),
            reasons=tuple(reasons),
            suitable_regimes=frozenset(["bull", "choppy"]),
        )


class VolatilityStrategy:
    """波动率策略：ATR 通道 + 极端波动预警"""
    ID = StrategyId.VOLATILITY

    def evaluate(self, candles: dict, volumes: np.ndarray, regime: str) -> StrategyResult:
        close = np.array(candles["close"], dtype=np.float64)
        high = np.array(candles["high"], dtype=np.float64)
        low = np.array(candles["low"], dtype=np.float64)
        atr_val = atr(high, low, close, 14)[-1]
        atr_pct = atr_val / close[-1]

        reasons = []
        direction = None
        confidence = 0.0

        if regime == "crisis" or atr_pct > 0.05:
            # 极端波动：减少暴露
            reasons.append(f"ATR 波动率偏高 ({atr_pct:.1%})")
            if atr_pct > 0.08:
                reasons.append("建议观望或极小仓位")
                confidence = 0.3
            else:
                # 小仓反向
                rsi_val = rsi(close, 14)[-1]
                if rsi_val < 30:
                    direction = "long"
                    reasons.append("超卖·小仓抄底")
                    confidence = 0.5
                elif rsi_val > 70:
                    direction = "short"
                    reasons.append("超买·小仓做空")
                    confidence = 0.5

        return StrategyResult(
            strategy=self.ID,
            pair=candles.get("symbol", "UNKNOWN"),
            timeframe=candles.get("timeframe", "1h"),
            direction=direction,
            confidence=max(0, min(1, confidence)),
            reasons=tuple(reasons),
            suitable_regimes=frozenset(["crisis", "bear"]),
        )


class SentimentStrategy:
    """情绪反向：恐惧/贪婪指标"""
    ID = StrategyId.SENTIMENT

    def evaluate(self, candles: dict, volumes: np.ndarray, regime: str) -> StrategyResult:
        close = np.array(candles["close"], dtype=np.float64)
        rsi_val = rsi(close, 14)[-1]
        vol_ratio = float(volumes[-1] / (np.mean(volumes[-20:]) + 1e-10))

        reasons = []
        direction = None
        confidence = 0.0

        if regime == "bear" and rsi_val < 25:
            direction = "long"
            reasons.append(f"极度超卖 RSI({14})={rsi_val:.0f}，情绪恐慌·逆向机会")
            confidence = 0.65
        elif regime == "bull" and rsi_val > 80:
            direction = "short"
            reasons.append(f"极度超买 RSI({14})={rsi_val:.0f}，情绪贪婪·逆向机会")
            confidence = 0.6

        if vol_ratio > 2.0:
            reasons.append(f"恐慌放量 ({vol_ratio:.1f}x)")

        return StrategyResult(
            strategy=self.ID,
            pair=candles.get("symbol", "UNKNOWN"),
            timeframe=candles.get("timeframe", "1h"),
            direction=direction,
            confidence=max(0, min(1, confidence)),
            reasons=tuple(reasons),
            suitable_regimes=frozenset(["bear", "bull"]),
        )


class VolumeProfileStrategy:
    """量价共振：POC 支撑/阻力"""
    ID = StrategyId.VOLUME

    def evaluate(self, candles: dict, volumes: np.ndarray, regime: str) -> StrategyResult:
        close = np.array(candles["close"], dtype=np.float64)
        vp = volume_profile(volumes[-100:], close[-100:])
        price = close[-1]

        reasons = []
        direction = None
        confidence = 0.0

        if price < vp["value_area_low"]:
            direction = "long"
            reasons.append(f"价格低于 VA 低沿 ({price:.2f} < {vp['value_area_low']:.2f})，POC={vp['poc']:.2f}")
            confidence = 0.6
        elif price > vp["value_area_high"]:
            direction = "short"
            reasons.append(f"价格高于 VA 高沿 ({price:.2f} > {vp['value_area_high']:.2f})，POC={vp['poc']:.2f}")
            confidence = 0.6

        return StrategyResult(
            strategy=self.ID,
            pair=candles.get("symbol", "UNKNOWN"),
            timeframe=candles.get("timeframe", "1h"),
            direction=direction,
            confidence=max(0, min(1, confidence)),
            reasons=tuple(reasons),
            suitable_regimes=frozenset(["bull", "bear", "choppy", "crisis"]),
        )


class MultiTimeframeStrategy:
    """多周期共振：日线 + 4H + 1H 趋势一致时最强信号"""
    ID = StrategyId.MULTI_TF

    def evaluate(self, candles: dict, volumes: np.ndarray, regime: str) -> StrategyResult:
        close = np.array(candles["close"], dtype=np.float64)
        ema_9 = ema(close, 9)
        ema_21 = ema(close, 21)
        ema_50 = ema(close, 50)
        rsi_val = rsi(close, 14)[-1]

        reasons = []
        direction = None
        confidence = 0.0

        # 趋势一致：ema9 > ema21 > ema50 → 多头
        aligned_long = ema_9[-1] > ema_21[-1] > ema_50[-1]
        aligned_short = ema_9[-1] < ema_21[-1] < ema_50[-1]

        if aligned_long and regime in ("bull", "choppy"):
            direction = "long"
            reasons.append("多周期均线多头排列 (9>21>50)")
            confidence = 0.85
            if rsi_val < 60:
                reasons.append(f"RSI({14})={rsi_val:.0f} 仍有空间")
        elif aligned_short and regime in ("bear", "choppy"):
            direction = "short"
            reasons.append("多周期均线空头排列 (9<21<50)")
            confidence = 0.80
            if rsi_val > 40:
                reasons.append(f"RSI({14})={rsi_val:.0f} 仍有空间")

        return StrategyResult(
            strategy=self.ID,
            pair=candles.get("symbol", "UNKNOWN"),
            timeframe=candles.get("timeframe", "1h"),
            direction=direction,
            confidence=max(0, min(1, confidence)),
            reasons=tuple(reasons),
            suitable_regimes=frozenset(["bull", "bear", "choppy"]),
        )


# ─── 策略池 ──────────────────────────────────────────────────────────────────

STRATEGY_INSTANCES: dict[StrategyId, Strategy] = {
    StrategyId.MOMENTUM: MomentumStrategy(),
    StrategyId.REVERSAL: MeanReversionStrategy(),
    StrategyId.BREAKOUT: BreakoutStrategy(),
    StrategyId.VOLATILITY: VolatilityStrategy(),
    StrategyId.SENTIMENT: SentimentStrategy(),
    StrategyId.VOLUME: VolumeProfileStrategy(),
    StrategyId.MULTI_TF: MultiTimeframeStrategy(),
}
