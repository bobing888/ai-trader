"""Persistence — Agent 研判报告 + 推荐单 DB 持久化（Task 5）

设计：
  - 2 张新表：ai_trend_analysis + agent_recommendation
  - AnalysisRepository + RecommendationRepository（classmethod 风格）
  - 复用现有 app/db/models.py 的 Base（DeclarativeBase）
  - JSON 字段存 list[str]（key_observations / risks）
  - 不引入 Alembic（项目现有风格是手写 SQL + Base.metadata.create_all）

参考 spec: docs/superpowers/specs/2026-10-03-trend-analysis-agent.md §4.1
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.agent.schemas import AgentRecommendation, AnalysisReport
from app.db.models import Base


# === ORM Models ===

class AiTrendAnalysis(Base):
    """Agent 研判报告（自然语言）"""

    __tablename__ = "ai_trend_analysis"
    __table_args__ = (
        Index("idx_ai_trend_pair_tf_created", "pair", "timeframe", "created_at"),
        Index("idx_ai_trend_status", "analysis_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pair: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    regime: Mapped[str] = mapped_column(String(20), nullable=False)
    regime_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    key_observations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    risks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    analysis_status: Mapped[str] = mapped_column(String(20), nullable=False, default="success")
    raw_llm_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class AgentRecommendationRow(Base):
    """Agent 第二意见推荐单"""

    __tablename__ = "agent_recommendation"
    __table_args__ = (
        Index("idx_agent_rec_pair_tf_created", "pair", "timeframe", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pair: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="agent")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


# === init helper ===

def init_agent_tables() -> type[Base]:
    """返回 Base — 调用方用 Base.metadata.create_all(engine) 建表

    把 ORM 类 import 一次确保 SQLAlchemy 知道它们的存在
    """
    # 这两个 import 必须在这里做，让 Base.metadata 知道这两个表
    return Base  # AiTrendAnalysis + AgentRecommendationRow 已通过 from import 注册


# === Repositories ===

class AnalysisRepository:
    """AiTrendAnalysis 仓储"""

    @classmethod
    def save(cls, db: Session, report: AnalysisReport) -> AiTrendAnalysis:
        """把 Pydantic AnalysisReport 写入 DB"""
        row = AiTrendAnalysis(
            pair=report.pair,
            timeframe=report.timeframe,
            regime=report.regime,
            regime_confidence=report.regime_confidence,
            reasoning=report.reasoning,
            key_observations=list(report.key_observations),
            risks=list(report.risks),
            analysis_status=report.analysis_status.value,
            raw_llm_response=report.raw_llm_response,
        )
        db.add(row)
        db.flush()  # 拿 id，不 commit（让调用方决定）
        return row

    @classmethod
    def list_recent(
        cls,
        db: Session,
        pair: str,
        timeframe: str | None,
        limit: int = 20,
    ) -> list[AiTrendAnalysis]:
        """最近 N 条研判报告，按 created_at desc"""
        q = db.query(AiTrendAnalysis).filter(AiTrendAnalysis.pair == pair)
        if timeframe is not None:
            q = q.filter(AiTrendAnalysis.timeframe == timeframe)
        return q.order_by(AiTrendAnalysis.created_at.desc()).limit(limit).all()


class RecommendationRepository:
    """AgentRecommendation 仓储"""

    @classmethod
    def save(cls, db: Session, rec: AgentRecommendation) -> AgentRecommendationRow:
        """把 Pydantic AgentRecommendation 写入 DB"""
        row = AgentRecommendationRow(
            pair=rec.pair,
            timeframe=rec.timeframe,
            direction=rec.direction.value,
            confidence=rec.confidence,
            rationale=rec.rationale,
            source=rec.source,  # 永远是 "agent"
        )
        db.add(row)
        db.flush()
        return row

    @classmethod
    def list_recent(
        cls,
        db: Session,
        pair: str,
        timeframe: str | None,
        limit: int = 20,
    ) -> list[AgentRecommendationRow]:
        q = db.query(AgentRecommendationRow).filter(AgentRecommendationRow.pair == pair)
        if timeframe is not None:
            q = q.filter(AgentRecommendationRow.timeframe == timeframe)
        return q.order_by(AgentRecommendationRow.created_at.desc()).limit(limit).all()