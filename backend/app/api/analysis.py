"""Unified analysis endpoint — 一次返回 4 大类量化指标

返回结构：
{
  symbol, timeframe, as_of,
  regime:     { regime, confidence, regime_probs, description },
  trend:      { adx, pdi, ndi, strength_label },
  volatility: { current_atr_pct, percentile_1y, level },
  statistical:{ hurst, fractal_dim, entropy, interpretation },
  multifactor:{ technical, fundamental, sentiment, composite }
}
"""

import logging
from datetime import datetime, timezone
from typing import Annotated

import numpy as np
from fastapi import APIRouter, HTTPException, Query

from app.api.klines import TimeframeLiteral, _generate_mock_candles
from app.config import settings
from app.analytics.statistical import hurst_exponent, fractal_dimension, shannon_entropy
from app.analytics.trend import trend_strength
from app.analytics.volatility import volatility_percentile
from app.data import binance_client
from app.signals.regime import RegimeDetector
from app.signals import STRATEGY_INSTANCES
from app.signals.aggregator import SignalAggregator

logger = logging.getLogger(__name__)

router = APIRouter(redirect_slashes=False)


async def _fetch_candles(symbol: str, timeframe: str, limit: int) -> list[dict]:
    if settings.use_mock_data:
        candles = _generate_mock_candles(symbol, timeframe, min(limit, 500))
        return [c.model_dump() for c in candles]
    return await binance_client.get_klines(symbol, timeframe, limit)


def _describe_regime(regime: str, confidence: float) -> str:
    labels = {
        "bull": "上升趋势 / 偏多",
        "bear": "下降趋势 / 偏空",
        "choppy": "震荡 / 无方向",
        "crisis": "极端波动 / 风险高",
    }
    base = labels.get(regime, regime)
    if confidence >= 0.7:
        return f"{base}（高置信）"
    if confidence >= 0.4:
        return f"{base}（中等置信）"
    return f"{base}（低置信 / 信号弱）"


def _interpret_statistical(hurst: float, fractal: float, entropy: float) -> str:
    """综合解读 Hurst + 分形 + 熵"""
    parts = []
    if hurst < 0.45:
        parts.append("强均值回归")
    elif hurst < 0.55:
        parts.append("接近随机游走")
    else:
        parts.append("有趋势记忆")
    if fractal > 1.6:
        parts.append("价格路径粗糙")
    elif fractal < 1.3:
        parts.append("价格路径平滑")
    if entropy > 4.5:
        parts.append("信息熵高 / 复杂度大")
    elif entropy < 3.0:
        parts.append("信息熵低 / 模式明显")
    return " · ".join(parts) if parts else "—"


@router.get("/{symbol}")
async def analyze(
    symbol: str,
    timeframe: Annotated[TimeframeLiteral, Query()] = "1h",
    limit: Annotated[int, Query(ge=60, le=1000)] = 500,
) -> dict:
    """统一分析 — 一次返回 regime + trend + volatility + statistical + multifactor"""
    symbol = symbol.upper()
    try:
        candles = await _fetch_candles(symbol, timeframe, limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Binance upstream error: {e}")
    if not candles or len(candles) < 60:
        raise HTTPException(status_code=404, detail=f"{symbol} 数据不足（需要 ≥60 根 K 线）")

    closes = np.array([c["close"] for c in candles], dtype=np.float64)
    highs = np.array([c["high"] for c in candles], dtype=np.float64)
    lows = np.array([c["low"] for c in candles], dtype=np.float64)
    opens = np.array([c["open"] for c in candles], dtype=np.float64)
    volumes = np.array([c["volume"] for c in candles], dtype=np.float64)

    # 1. Regime（用现有 detector）
    log_returns = np.diff(np.log(closes + 1e-10), prepend=closes[0])
    detector = RegimeDetector()
    regime_info = detector.update(log_returns, volumes)
    regime_out = {
        "regime": regime_info.regime.value,
        "confidence": round(regime_info.confidence, 3),
        "regime_probs": {k.value: round(v, 3) for k, v in regime_info.regime_probs.items()},
        "description": _describe_regime(regime_info.regime.value, regime_info.confidence),
    }

    # 2. Trend (ADX)
    trend_out = trend_strength(highs, lows, closes, period=14)

    # 3. Volatility percentile
    vol_out = volatility_percentile(closes, highs, lows, period=14, lookback=min(len(closes), 8760))

    # 4. Statistical (Hurst + Fractal + Entropy)
    hurst = hurst_exponent(closes, max_lag=20)
    fractal = fractal_dimension(closes, max_lag=20)
    entropy = shannon_entropy(closes, bins=20)
    stat_out = {
        "hurst": round(hurst, 3),
        "fractal_dim": round(fractal, 3),
        "entropy": round(entropy, 3),
        "interpretation": _interpret_statistical(hurst, fractal, entropy),
    }

    # 5. Multi-factor (技术 + 情绪 + 合成)
    #    技术分：用所有内置策略的 confidence 均值（0-100）
    candles_dict = {"symbol": symbol, "timeframe": timeframe, "close": closes, "open": opens, "high": highs, "low": lows}
    strategy_results = [s.evaluate(candles_dict, volumes, regime_info.regime.value) for s in STRATEGY_INSTANCES.values()]
    confidences = [r.confidence for r in strategy_results if r.direction is not None]
    technical_score = round(100 * np.mean(confidences), 1) if confidences else 50.0

    #    情绪分：RSI 归一化（30 超卖=100, 70 超买=0）
    from app.analytics.statistical import rsi_score
    sentiment_score = rsi_score(closes, period=14)

    #    基本面：当前无 funding rate 数据，置 50
    fundamental_score = 50.0

    #    合成：技术 0.5 + 情绪 0.3 + 基本面 0.2（基本面权重小因数据不足）
    composite = round(0.5 * technical_score + 0.3 * sentiment_score + 0.2 * fundamental_score, 1)
    multifactor_out = {
        "technical": technical_score,
        "fundamental": fundamental_score,
        "sentiment": round(sentiment_score, 1),
        "composite": composite,
    }

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "regime": regime_out,
        "trend": trend_out,
        "volatility": vol_out,
        "statistical": stat_out,
        "multifactor": multifactor_out,
    }
