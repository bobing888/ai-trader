"""/api/dashboard/* — multi-symbol overview endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview")
async def get_overview(
    symbols: Annotated[
        str, Query(description="逗号分隔的交易对，如 BTC-USDT,ETH-USDT")
    ],
    timeframe: Annotated[str, Query(description="时间周期：1h / 4h / 1d")] = "1h",
) -> dict:
    """返回 dashboard 整体 payload（items + timeframe + source + generated_at）。"""
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        raise HTTPException(status_code=400, detail="symbols required")
    try:
        result = await dashboard_service.fetch_overview(symbol_list, timeframe)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # 直接 dump pydantic model
    return result.model_dump(mode="json")