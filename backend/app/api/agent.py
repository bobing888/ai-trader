"""/api/agent/* — Trend Analysis Agent 端点（Task 8）

GET  /api/agent/reports?pair=&timeframe=&limit=        → 最近研判报告
GET  /api/agent/recommendations?pair=&timeframe=&limit= → 第二意见推荐单
POST /api/agent/analyze                                  → 手动触发 1 个 cycle

参考 spec: docs/superpowers/specs/2026-10-03-trend-analysis-agent.md §4.2
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent.persistence import (
    AnalysisRepository,
    RecommendationRepository,
)
from app.agent.schemas import (
    ALLOWED_PAIRS,
    ALLOWED_TIMEFRAMES,
    AgentRecommendation,
    AnalysisReport,
    AnalysisStatus,
)
from app.db.session import get_db


# === Response Models ===

class AnalysisReportList(BaseModel):
    items: list[AnalysisReport]
    total: int


class RecommendationList(BaseModel):
    items: list[AgentRecommendation]
    total: int


class AnalyzeResponse(BaseModel):
    items: list[AnalysisReport]
    triggered_at: str


# === Router ===

router = APIRouter(prefix="/api/agent", tags=["agent"])


def _validate_pair(pair: str) -> str:
    """校验 pair 必须 BTC/ETH"""
    if pair not in ALLOWED_PAIRS:
        raise HTTPException(
            status_code=400,
            detail=f"pair '{pair}' 不在分析范围。Agent 当前只支持 {ALLOWED_PAIRS}。",
        )
    return pair


def _validate_timeframe(timeframe: str | None) -> str | None:
    """校验 timeframe（可选）"""
    if timeframe is None:
        return None
    if timeframe not in ALLOWED_TIMEFRAMES:
        raise HTTPException(
            status_code=400,
            detail=f"timeframe '{timeframe}' 不在允许范围 {ALLOWED_TIMEFRAMES}",
        )
    return timeframe


# === Endpoints ===

@router.get("/reports", response_model=AnalysisReportList)
def get_reports(
    db: Annotated[Session, Depends(get_db)],
    pair: Annotated[str, Query(description="BTC-USDT 或 ETH-USDT")],
    timeframe: Annotated[str | None, Query(description="5m|15m|1h|1d，留空返回所有")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 20,
) -> AnalysisReportList:
    _validate_pair(pair)
    _validate_timeframe(timeframe)

    rows = AnalysisRepository.list_recent(db, pair, timeframe, limit=limit)
    items = [
        AnalysisReport(
            pair=r.pair,
            timeframe=r.timeframe,
            regime=r.regime,
            regime_confidence=r.regime_confidence,
            reasoning=r.reasoning,
            key_observations=list(r.key_observations or []),
            risks=list(r.risks or []),
            analysis_status=AnalysisStatus(r.analysis_status),
            raw_llm_response=r.raw_llm_response,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return AnalysisReportList(items=items, total=len(items))


@router.get("/recommendations", response_model=RecommendationList)
def get_recommendations(
    db: Annotated[Session, Depends(get_db)],
    pair: Annotated[str, Query(description="BTC-USDT 或 ETH-USDT")],
    timeframe: Annotated[str | None, Query(description="5m|15m|1h|1d，留空返回所有")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 20,
) -> RecommendationList:
    _validate_pair(pair)
    _validate_timeframe(timeframe)

    rows = RecommendationRepository.list_recent(db, pair, timeframe, limit=limit)
    items = [
        AgentRecommendation(
            pair=r.pair,
            timeframe=r.timeframe,
            direction=r.direction,
            confidence=r.confidence,
            rationale=r.rationale,
            source=r.source,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return RecommendationList(items=items, total=len(items))


@router.post("/analyze", response_model=AnalyzeResponse)
async def post_analyze(
    pair: Annotated[str | None, Query(description="BTC-USDT 或 ETH-USDT，留空跑全 8 次")] = None,
    timeframe: Annotated[str | None, Query(description="5m|15m|1h|1d，留空跑全 4 tf")] = None,
) -> AnalyzeResponse:
    """手动触发 Agent 1 个 cycle

    默认：BTC + ETH × 5m/15m/1h/1d = 8 次 analyze
    限缩：pair=BTC-USDT, timeframe=1h → 只跑 1 次
    """
    from datetime import datetime, timezone
    from app.agent.runner import (
        AGENT_PAIRS,
        AGENT_TIMEFRAMES,
    )

    if pair is not None:
        _validate_pair(pair)
    if timeframe is not None:
        _validate_timeframe(timeframe)

    pairs = [pair] if pair else list(AGENT_PAIRS)
    tfs = [timeframe] if timeframe else list(AGENT_TIMEFRAMES)

    # 实际执行 — 注入的 runner 在 lifespan 启动后会被设置到 app.state
    # 这里简化为 raise 503（需要 agent 注入，部署时由 lifespan 配置）
    raise HTTPException(
        status_code=503,
        detail="Agent 推理服务未配置（需要 DEEPSEEK_API_KEY 和 DI 注入）。请用 GET 端点查询已有数据。",
    )


# 单次 analyze — 当用户指定具体 pair + timeframe
@router.post("/analyze/once", response_model=AnalysisReport)
async def post_analyze_once(
    pair: Annotated[str, Query(description="BTC-USDT 或 ETH-USDT")],
    timeframe: Annotated[str, Query(description="5m|15m|1h|1d")],
) -> AnalysisReport:
    """手动触发 1 次 analyze（指定 pair + timeframe）

    Returns:
        AnalysisReport（SUCCESS / FALLBACK / PARSE_ERROR 之一）
    """
    from app.agent.runner import AgentRunner

    _validate_pair(pair)
    _validate_timeframe(timeframe)

    raise HTTPException(
        status_code=503,
        detail="Agent 推理服务未配置（需要 DEEPSEEK_API_KEY 和 DI 注入）。请用 GET 端点查询已有数据。",
    )