"""K 线数据端点 — 真实数据 (Binance/OKX) 或 mock 可切换

通过 settings.data_source 选择数据源：
- 'binance'（默认）走 BinanceClient
- 'okx'（kbkkk 等被 Binance 限流的地区）走 OkxClient
两者对外接口相同（get_klines 返回 time/open/high/low/close/volume 格式），
前端无任何感知，HttpRouter 不变化。
"""

import math
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config import settings
from app.data import binance_client, get_client, okx_client

router = APIRouter(prefix="", tags=["klines"])


class Candle(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class KLinesResponse(BaseModel):
    symbol: str
    timeframe: str
    candles: list[Candle]
    count: int


TimeframeLiteral = Literal["1m", "5m", "15m", "1h", "4h", "1d"]

_TIMEFRAME_SECONDS: dict[str, int] = {
    "1m": 60, "5m": 300, "15m": 900,
    "1h": 3600, "4h": 14400, "1d": 86400,
}


def _generate_mock_candles(symbol: str, timeframe: TimeframeLiteral, count: int) -> list[Candle]:
    """生成 mock K 线（不同 symbol 不同 regime）。"""
    timeframe_seconds = _TIMEFRAME_SECONDS[timeframe]
    now = int(datetime.now(timezone.utc).timestamp())
    aligned_now = now - (now % timeframe_seconds)

    seed = sum(ord(c) for c in symbol)
    base_price = 100 + (seed % 90000) / 10

    candles: list[Candle] = []
    price = base_price
    regime_bias = seed % 4

    for i in range(count):
        t = aligned_now - (count - 1 - i) * timeframe_seconds

        if regime_bias == 0:  # bull
            wave = math.sin((i + seed) * 0.05) * (base_price * 0.015)
            noise = math.cos((i + seed) * 0.27) * (base_price * 0.003)
            drift = base_price * 0.0008
        elif regime_bias == 1:  # bear
            wave = math.sin((i + seed) * 0.05) * (base_price * 0.015)
            noise = math.cos((i + seed) * 0.27) * (base_price * 0.003)
            drift = -base_price * 0.0008
        elif regime_bias == 2:  # choppy
            wave = math.sin((i + seed) * 0.18) * (base_price * 0.012)
            noise = math.cos((i + seed) * 0.37) * (base_price * 0.004)
            drift = 0
        else:  # volatile bull
            wave = math.sin((i + seed) * 0.07) * (base_price * 0.022)
            noise = math.cos((i + seed) * 0.31) * (base_price * 0.008)
            drift = base_price * 0.0004

        open_price = price
        close_price = price + wave + noise + drift
        high_price = max(open_price, close_price) + abs(noise) * 1.2
        low_price = min(open_price, close_price) - abs(noise) * 1.2

        if regime_bias == 0:
            volume = 300 + abs(math.sin((i + seed) * 0.2)) * 1500
        elif regime_bias == 1:
            volume = 200 + abs(math.sin((i + seed) * 0.2)) * 800
        elif regime_bias == 2:
            volume = 400 + abs(math.sin((i + seed) * 0.2)) * 600
        else:
            volume = 500 + abs(math.sin((i + seed) * 0.2)) * 2000

        candles.append(Candle(
            time=t,
            open=round(open_price, 2),
            high=round(high_price, 2),
            low=round(low_price, 2),
            close=round(close_price, 2),
            volume=round(volume, 2),
        ))
        price = close_price

    return candles


@router.get("/{symbol}", response_model=KLinesResponse)
async def get_klines(
    symbol: str,
    timeframe: TimeframeLiteral = Query("1h"),
    limit: int = Query(500, ge=1, le=1000),
) -> KLinesResponse:
    symbol = symbol.upper()
    if not symbol or len(symbol) > 32:
        raise HTTPException(status_code=400, detail="Invalid symbol")

    if settings.use_mock_data:
        candles = _generate_mock_candles(symbol, timeframe, min(limit, 500))
        return KLinesResponse(symbol=symbol, timeframe=timeframe, candles=candles, count=len(candles))

    # 真实 Binance / OKX 数据（按 settings.data_source 选）
    try:
        raw = await get_client().get_klines(symbol, timeframe, limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {e}")

    if not raw:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found or no data")

    candles = [Candle(**c) for c in raw]
    return KLinesResponse(symbol=symbol, timeframe=timeframe, candles=candles, count=len(candles))
