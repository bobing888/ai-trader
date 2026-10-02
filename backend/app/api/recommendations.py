"""/api/recommendations/* — 查询推荐历史（spec §5.2）

GET /api/recommendations/history?pair=&timeframe=&limit=  → list
GET /api/recommendations/latest?pair=&timeframe=         → most recent
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.models import RecommendationHistory
from app.db.session import get_db
from app.schemas.recommendations import (
    RecommendationHistoryList,
    RecommendationHistoryOut,
)

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.get("/history", response_model=RecommendationHistoryList)
def get_history(
    db: Annotated[Session, Depends(get_db)],
    pair: Annotated[str, Query(description="OKX 形态 pair")],
    timeframe: Annotated[str, Query(description="5m|15m|1h|4h|1d")],
    limit: Annotated[int, Query(ge=1, le=500)] = 60,
) -> RecommendationHistoryList:
    items = (
        db.query(RecommendationHistory)
        .filter(RecommendationHistory.pair == pair)
        .filter(RecommendationHistory.timeframe == timeframe)
        .order_by(RecommendationHistory.scanned_at.desc())
        .limit(limit)
        .all()
    )
    return RecommendationHistoryList(
        items=[RecommendationHistoryOut.model_validate(it) for it in items],
        total=len(items),
    )


@router.get("/latest", response_model=RecommendationHistoryOut)
def get_latest(
    db: Annotated[Session, Depends(get_db)],
    pair: Annotated[str, Query(description="OKX 形态 pair")],
    timeframe: Annotated[str, Query(description="5m|15m|1h|4h|1d")],
) -> RecommendationHistory:
    rec = (
        db.query(RecommendationHistory)
        .filter(RecommendationHistory.pair == pair)
        .filter(RecommendationHistory.timeframe == timeframe)
        .order_by(RecommendationHistory.scanned_at.desc())
        .first()
    )
    if rec is None:
        raise HTTPException(status_code=404, detail=f"No recommendation for {pair}/{timeframe}") from None
    return rec
