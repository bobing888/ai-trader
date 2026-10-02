"""/api/follows/* — 跟单 CRUD endpoint（spec §5.1）

5 endpoints:
- POST   /api/follows           — create
- GET    /api/follows           — list (filter by status/pair)
- GET    /api/follows/{id}      — get one
- POST   /api/follows/{id}/close   — 出场 + 算 PnL
- POST   /api/follows/{id}/cancel  — 撤销

错误码:
- 409: 重复 close/cancel
- 422: 参数错误
- 404: follow 不存在
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import UserFollow
from app.db.session import get_db
from app.schemas.follows import (
    FollowCancelRequest,
    FollowCloseRequest,
    FollowListOut,
    UserFollowCreate,
    UserFollowOut,
)
from app.services.follow_service import FollowService

router = APIRouter(prefix="/api/follows", tags=["follows"])


@router.post("", response_model=UserFollowOut, status_code=200)
def create_follow(
    payload: UserFollowCreate,
    db: Annotated[Session, Depends(get_db)],
) -> UserFollow:
    if payload.stake_amount is None:
        payload.stake_amount = settings.follow_default_stake_amount
    follow = FollowService.create(db, payload.model_dump())
    return follow


@router.get("", response_model=FollowListOut)
def list_follows(
    db: Annotated[Session, Depends(get_db)],
    status: Annotated[str, Query(description="open|closed|cancelled|all")] = "all",
    pair: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> FollowListOut:
    items = FollowService.list(db, status=status, pair=pair, limit=limit)
    total = db.query(UserFollow).count()
    return FollowListOut(items=[UserFollowOut.model_validate(f) for f in items], total=total)


@router.get("/{follow_id}", response_model=UserFollowOut)
def get_follow(
    follow_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> UserFollow:
    follow = FollowService.get(db, follow_id)
    if follow is None:
        raise HTTPException(status_code=404, detail=f"Follow {follow_id} not found")
    return follow


@router.post("/{follow_id}/close", response_model=UserFollowOut)
def close_follow(
    follow_id: int,
    payload: FollowCloseRequest,
    db: Annotated[Session, Depends(get_db)],
) -> UserFollow:
    try:
        return FollowService.close(
            db,
            follow_id,
            payload.exit_price,
            payload.exit_reason or "manual",
            payload.exit_size_pct,
        )
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=409, detail=msg) from exc


@router.post("/{follow_id}/cancel", response_model=UserFollowOut)
def cancel_follow(
    follow_id: int,
    payload: FollowCancelRequest,
    db: Annotated[Session, Depends(get_db)],
) -> UserFollow:
    try:
        return FollowService.cancel(db, follow_id, reason=payload.reason or "manual")
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=409, detail=msg) from exc
