"""推荐单 API — Regime + Strategy + Affinity 融合"""

from datetime import datetime, timezone
from typing import Annotated

import numpy as np
from fastapi import APIRouter, Query

from app.api.klines import TimeframeLiteral, _generate_mock_candles
from app.config import settings
from app.data import binance_client
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
        },
        "regime": regime_info,
    }


async def _fetch_candles_for(pair: str, timeframe: str, limit: int) -> list[dict]:
    """拉取 K 线（真实 / mock 切换）。"""
    if settings.use_mock_data:
        candles = _generate_mock_candles(pair.replace("/", ""), timeframe, min(limit, 500))
        return [c.model_dump() for c in candles]
    return await binance_client.get_klines(pair.replace("/", ""), timeframe, limit)


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

    detector = RegimeDetector()
    log_returns = np.diff(np.log(closes + 1e-10), prepend=closes[0])
    regime_info_obj = detector.update(log_returns, volumes)
    regime_info = {
        "regime": regime_info_obj.regime.value,
        "confidence": round(regime_info_obj.confidence, 3),
        "regime_probs": {k.value: round(v, 3) for k, v in regime_info_obj.regime_probs.items()},
        "description": regime_info_obj.description,
    }

    candles_dict = {
        "symbol": pair,
        "timeframe": timeframe,
        "close": closes,
        "open": np.array([c["open"] for c in candle_dicts], dtype=np.float64),
        "high": np.array([c["high"] for c in candle_dicts], dtype=np.float64),
        "low": np.array([c["low"] for c in candle_dicts], dtype=np.float64),
    }
    strategy_results: list[StrategyResult] = []
    for sid, strategy in STRATEGY_INSTANCES.items():
        result = strategy.evaluate(candles_dict, volumes, regime_info_obj.regime.value)
        strategy_results.append(result)

    aggregator = SignalAggregator(min_agreement=2)
    sig = aggregator.aggregate(strategy_results, regime_info_obj.regime, regime_info_obj.confidence)

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
