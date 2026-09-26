"""Ticker 端点 — 实时行情（Binance / OKX / mock 切换）

通过 settings.data_source 选择：
  - 'binance'（默认）走 BinanceClient → source='binance'
  - 'okx'（kbkkk 等）走 OkxClient → source='okx'
  - mock 模式 (use_mock_data=true) → 全返 0
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.data import get_client

router = APIRouter(prefix="/ticker", tags=["ticker"])


def _source_label() -> str:
    if settings.use_mock_data:
        return "mock"
    return (settings.data_source or "binance").lower()


@router.get("/batch")
async def get_ticker_batch(
    symbols: Annotated[str, Query(description="逗号分隔的交易对，如 BTCUSDT,ETHUSDT")],
) -> dict:
    """批量获取 ticker（24h 价格变动）。"""
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        raise HTTPException(status_code=400, detail="symbols required")
    if len(symbol_list) > 50:
        raise HTTPException(status_code=400, detail="max 50 symbols per request")

    if settings.use_mock_data:
        # mock 模式：固定 0
        return {
            "tickers": [
                {"symbol": s, "price": 0.0, "change_24h": 0.0} for s in symbol_list
            ],
            "source": "mock",
        }

    tickers = await get_client().get_tickers_batch(symbol_list)
    return {"tickers": tickers, "source": _source_label()}


@router.get("/{symbol}")
async def get_ticker_one(symbol: str) -> dict:
    """获取单个 ticker。"""
    symbol = symbol.upper()
    if settings.use_mock_data:
        return {"symbol": symbol, "price": 0.0, "change_24h": 0.0, "source": "mock"}

    ticker = await get_client().get_ticker(symbol)
    if not ticker:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
    return {**ticker, "source": _source_label()}
