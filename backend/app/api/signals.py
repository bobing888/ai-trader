"""推荐单 API — Regime + Strategy + Affinity 融合"""

from datetime import datetime, timezone
from typing import Annotated

import numpy as np
from fastapi import APIRouter, Query

from app.api.klines import TimeframeLiteral, _generate_mock_candles
from app.config import settings
from app.data import binance_client, get_client
from app.signals import (
    Regime,
    RegimeDetector,
    SignalAggregator,
    STRATEGY_INSTANCES,
    StrategyResult,
)

router = APIRouter(prefix="/signals", tags=["signals"])


def _build_signal_response(sig, regime_info: dict | None) -> dict:
    if sig is None:
        return {
            "has_signal": False,
            "message": "当前无足够共识信号，建议观望",
            "regime": regime_info,
        }
    return {
        "has_signal": True,
        "signal": {
            "pair": sig.pair,
            "direction": sig.direction,
            "confidence": sig.confidence,
            "contributing_strategies": sig.contributing_strategies,
            "reasons": sig.reasons,
            "entry_zones": sig.entry_zones,
            "risk_warnings": sig.risk_warnings,
            "regime": sig.regime,
            "regime_confidence": sig.regime_confidence,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            # v2 新增字段
            "timeframe": sig.timeframe,
            "timeframe_category": sig.timeframe_category,
            "suggested_leverage": sig.suggested_leverage,
            "min_agreement_used": sig.min_agreement_used,
            "fast_path": sig.fast_path,
            # Phase 1 signal credibility
            "calibrated_confidence": sig.calibrated_confidence,
            "net_pnl_estimate": sig.net_pnl_estimate,
        },
        "regime": regime_info,
    }


async def _fetch_candles_for(pair: str, timeframe: str, limit: int) -> list[dict]:
    """拉取 K 线（真实 / mock 切换）。"""
    if settings.use_mock_data:
        candles = _generate_mock_candles(pair.replace("/", ""), timeframe, min(limit, 500))
        return [c.model_dump() for c in candles]
    return await get_client().get_klines(pair.replace("/", ""), timeframe, limit)


@router.get("/recommend/{pair}")
async def get_recommendation(
    pair: str,
    timeframe: Annotated[TimeframeLiteral, Query(description="时间周期")] = "1h",
    limit: Annotated[int, Query(ge=30, le=500)] = 120,
) -> dict:
    """返回指定交易对的推荐单信号。"""
    try:
        candle_dicts = await _fetch_candles_for(pair, timeframe, limit)
    except Exception as e:
        return {
            "has_signal": False,
            "message": f"无法获取 {pair} 数据：{e}",
            "regime": None,
        }

    if not candle_dicts or len(candle_dicts) < 30:
        return {
            "has_signal": False,
            "message": f"{pair} 数据不足（需要 ≥30 根 K 线）",
            "regime": None,
        }

    closes = np.array([c["close"] for c in candle_dicts], dtype=np.float64)
    volumes = np.array([c["volume"] for c in candle_dicts], dtype=np.float64)
    highs = np.array([c["high"] for c in candle_dicts], dtype=np.float64)
    lows = np.array([c["low"] for c in candle_dicts], dtype=np.float64)

    # v2: 传入 timeframe 以便 regime 阈值自适应 + 传入 high/low/close 计算 ADX/Hurst
    detector = RegimeDetector(timeframe=timeframe)
    log_returns = np.diff(np.log(closes + 1e-10), prepend=closes[0])
    regime_info_obj = detector.update(log_returns, volumes, high=highs, low=lows, close=closes)
    regime_info = {
        "regime": regime_info_obj.regime.value,
        "confidence": round(regime_info_obj.confidence, 3),
        "regime_probs": {k.value: round(v, 3) for k, v in regime_info_obj.regime_probs.items()},
        "description": regime_info_obj.description,
        # v2 新增
        "adx": regime_info_obj.adx,
        "hurst": regime_info_obj.hurst,
        "trend_strength_label": regime_info_obj.trend_strength_label,
    }

    candles_dict = {
        "symbol": pair,
        "timeframe": timeframe,
        "close": closes,
        "open": np.array([c["open"] for c in candle_dicts], dtype=np.float64),
        "high": highs,
        "low": lows,
    }
    strategy_results: list[StrategyResult] = []
    for sid, strategy in STRATEGY_INSTANCES.items():
        result = strategy.evaluate(candles_dict, volumes, regime_info_obj.regime.value)
        strategy_results.append(result)

    # v2: 传入 timeframe + 强趋势信号 (adx/hurst)
    aggregator = SignalAggregator()
    sig = aggregator.aggregate(
        strategy_results,
        regime_info_obj.regime,
        regime_info_obj.confidence,
        timeframe=timeframe,
        adx=regime_info_obj.adx,
        hurst=regime_info_obj.hurst,
    )

    return _build_signal_response(sig, regime_info)


@router.get("/batch")
async def get_batch_signals(
    pairs: Annotated[str, Query(description="逗号分隔的交易对")],
    timeframe: Annotated[TimeframeLiteral, Query(description="时间周期")] = "1h",
    limit: Annotated[int, Query(ge=30, le=500)] = 120,
) -> dict:
    """批量获取多个交易对的推荐信号。"""
    pair_list = [p.strip().upper() for p in pairs.split(",") if p.strip()]
    results = []
    for pair in pair_list:
        rec = await get_recommendation(pair, timeframe, limit)
        results.append({"pair": pair, **rec})
    ranked = sorted(
        [r for r in results if r.get("has_signal")],
        key=lambda x: x.get("signal", {}).get("confidence", 0),
        reverse=True,
    )
    return {
        "results": results,
        "ranked": ranked,
        "count": len(results),
        "regime_global": results[0]["regime"] if results else None,
    }
