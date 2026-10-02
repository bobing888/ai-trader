"""Pydantic schemas for recommendations API (spec §5.3)"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RecommendationHistoryOut(BaseModel):
    """一帧推荐决议快照。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    pair: str
    timeframe: str
    has_signal: bool
    direction: str | None
    confidence: float | None
    regime: str | None
    regime_confidence: float | None
    suggested_leverage: int | None
    fast_path: bool
    outcome: str
    scanned_at: datetime
    source: str


class RecommendationHistoryList(BaseModel):
    items: list[RecommendationHistoryOut]
    total: int