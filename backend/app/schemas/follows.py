"""Pydantic schemas for follows + recommendations API (spec §5.3)"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserFollowCreate(BaseModel):
    """跟单创建 payload。"""

    pair: str = Field(..., description="OKX 形态 pair (BTC-USDT)")
    timeframe: str = Field(..., description="5m|15m|1h|4h|1d")
    direction: str = Field(..., description="long|short")
    entry_price: float | None = None
    stop_loss: float | None = None
    target: float | None = None
    leverage: int = Field(default=1, ge=1, le=125)
    stake_amount: float | None = None  # default = settings.follow_default_stake_amount
    source: str = Field(default="manual", description="manual|ai_recommendation")
    recommendation_id: int | None = None
    notes: str | None = None


class UserFollowOut(BaseModel):
    """跟单详情 + 状态。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    recommendation_id: int | None
    pair: str
    timeframe: str
    direction: str
    entry_price: float | None
    stop_loss: float | None
    target: float | None
    leverage: int
    status: str
    pnl_pct: float | None
    pnl_abs: float | None
    stake_amount: float
    entry_time: datetime
    exit_time: datetime | None
    exit_price: float | None
    exit_reason: str | None
    source: str
    notes: str | None
    created_at: datetime
    updated_at: datetime


class FollowListOut(BaseModel):
    items: list[UserFollowOut]
    total: int


class FollowCloseRequest(BaseModel):
    exit_price: float
    exit_reason: str | None = None


class FollowCancelRequest(BaseModel):
    reason: str | None = None