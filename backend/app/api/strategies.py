"""Strategies CRUD API — 完整增删改查 + 克隆 + 导入/导出 + GitHub 同步触发"""

import asyncio
import io
import json
import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import Strategy
from app.db.session import get_db
from app.services import github_sync as gh

logger = logging.getLogger(__name__)

router = APIRouter(redirect_slashes=False)


# ── Schemas ──────────────────────────────────────────────────────────────────


class StrategyCreate(BaseModel):
    name: str = Field(..., max_length=120)
    description: str = ""
    strategy_type: str = "custom"
    parameters: dict[str, Any] = Field(default_factory=dict)
    code: str = ""
    status: str = "enabled"
    weight: float = 1.0


class StrategyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    strategy_type: str | None = None
    parameters: dict[str, Any] | None = None
    code: str | None = None
    status: str | None = None
    weight: float | None = None


class StrategyRead(BaseModel):
    id: int
    name: str
    description: str
    strategy_type: str
    source: str
    parameters: dict[str, Any]
    code: str
    status: str
    weight: float
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_obj(cls, s: Strategy) -> "StrategyRead":
        return cls(
            id=s.id,
            name=s.name,
            description=s.description,
            strategy_type=s.strategy_type,
            source=s.source,
            parameters=s.parameters,
            code=s.code,
            status=s.status,
            weight=s.weight,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )

    class Config:
        from_attributes = True


# ── Routes ───────────────────────────────────────────────────────────────────


@router.get("", response_model=list[StrategyRead])
def list_strategies(
    db: Annotated[Session, Depends(get_db)],
    status: Annotated[str | None, Query(description="enabled | disabled")] = None,
    strategy_type: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[StrategyRead]:
    q = db.query(Strategy)
    if status:
        q = q.filter(Strategy.status == status)
    if strategy_type:
        q = q.filter(Strategy.strategy_type == strategy_type)
    rows = q.order_by(Strategy.id.desc()).offset(offset).limit(limit).all()
    return [StrategyRead.from_orm_obj(s) for s in rows]


@router.get("/{strategy_id}", response_model=StrategyRead)
def get_strategy(strategy_id: int, db: Annotated[Session, Depends(get_db)]) -> StrategyRead:
    s = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if s is None:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")
    return StrategyRead.from_orm_obj(s)


@router.post("", response_model=StrategyRead, status_code=201)
def create_strategy(payload: StrategyCreate, db: Annotated[Session, Depends(get_db)]) -> StrategyRead:
    s = Strategy(
        name=payload.name,
        description=payload.description,
        strategy_type=payload.strategy_type,
        source="manual",
        parameters=payload.parameters,
        code=payload.code,
        status=payload.status,
        weight=payload.weight,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return StrategyRead.from_orm_obj(s)


@router.put("/{strategy_id}", response_model=StrategyRead)
def update_strategy(
    strategy_id: int,
    payload: StrategyUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> StrategyRead:
    s = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if s is None:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(s, k, v)
    s.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(s)
    return StrategyRead.from_orm_obj(s)


@router.delete("/{strategy_id}", status_code=204)
def delete_strategy(strategy_id: int, db: Annotated[Session, Depends(get_db)]) -> None:
    s = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if s is None:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")
    db.delete(s)
    db.commit()


@router.post("/{strategy_id}/clone", response_model=StrategyRead, status_code=201)
def clone_strategy(strategy_id: int, db: Annotated[Session, Depends(get_db)]) -> StrategyRead:
    s = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if s is None:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")
    cloned = Strategy(
        name=f"{s.name} (copy)",
        description=s.description,
        strategy_type=s.strategy_type,
        source="manual",
        parameters=dict(s.parameters),
        code=s.code,
        status=s.status,
        weight=s.weight,
    )
    db.add(cloned)
    db.commit()
    db.refresh(cloned)
    return StrategyRead.from_orm_obj(cloned)


@router.get("/{strategy_id}/export")
def export_strategy(strategy_id: int, db: Annotated[Session, Depends(get_db)]) -> StreamingResponse:
    s = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if s is None:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")
    payload = {
        "name": s.name,
        "description": s.description,
        "strategy_type": s.strategy_type,
        "parameters": s.parameters,
        "code": s.code,
        "status": s.status,
        "weight": s.weight,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": "1.0",
    }
    raw = json.dumps(payload, ensure_ascii=False, indent=2)
    return StreamingResponse(
        io.BytesIO(raw.encode("utf-8")),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{s.name.replace("/", "_")}.json"'
        },
    )


@router.post("/import", response_model=StrategyRead, status_code=201)
async def import_strategy(payload: dict, db: Annotated[Session, Depends(get_db)]) -> StrategyRead:
    """接受 JSON 单条策略导入（与 export 格式相同）"""
    name = payload.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="missing 'name' field")
    s = Strategy(
        name=name,
        description=payload.get("description", ""),
        strategy_type=payload.get("strategy_type", "imported"),
        source="import",
        parameters=payload.get("parameters", {}),
        code=payload.get("code", ""),
        status=payload.get("status", "enabled"),
        weight=float(payload.get("weight", 1.0)),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return StrategyRead.from_orm_obj(s)


@router.post("/sync-github")
async def trigger_sync_github(db: Annotated[Session, Depends(get_db)]) -> dict:
    """手动触发 GitHub 同步 — 立即跑一次同步"""
    try:
        result = await gh.sync_github_strategies(db)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"sync failed: {e}")


@router.get("/sync-github/status")
def sync_github_status(db: Annotated[Session, Depends(get_db)]) -> dict:
    """查询当前 db 中所有 github 源 strategies + 最近一次同步时间"""
    rows = db.query(Strategy).filter(Strategy.source.like("github:%")).all()
    return {
        "enabled": gh.settings.github_sync_enabled,
        "interval_hours": gh.settings.github_sync_interval_hours,
        "query": gh.settings.github_search_query,
        "limit": gh.settings.github_sync_limit,
        "github_strategies_count": len(rows),
        "items": [
            {"id": s.id, "name": s.name, "parameters": s.parameters, "updated_at": s.updated_at}
            for s in rows
        ],
    }
