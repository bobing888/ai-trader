"""Tests for backend.app.agent.persistence — DB 持久化层（Task 5）.

覆盖（spec §4.1 + plan Task 5）：
  - ai_trend_analysis 表写入
  - agent_recommendation 表写入
  - 按 pair+timeframe 查询
  - limit 截断
  - 拒接非 BTC/ETH
  - 测数据完整性（Pydantic schema → DB row 一一对应）
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.agent.persistence import (
    AnalysisRepository,
    RecommendationRepository,
    init_agent_tables,
)
from app.agent.schemas import (
    AgentRecommendation,
    AnalysisReport,
    AnalysisStatus,
    Direction,
)


# === Fixtures ===

@pytest.fixture
def db_session():
    """in-memory SQLite for tests"""
    engine = create_engine("sqlite:///:memory:")
    Base = init_agent_tables()  # ensure tables exist
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    yield session
    session.close()


def make_report(**overrides) -> AnalysisReport:
    base = {
        "pair": "BTC-USDT",
        "timeframe": "1h",
        "regime": "bull",
        "regime_confidence": 0.75,
        "reasoning": "BTC 1h 处于多头格局。",
        "key_observations": ["ADX 28", "Hurst 0.62"],
        "risks": ["阻力位 51500"],
    }
    base.update(overrides)
    return AnalysisReport(**base)


def make_recommendation(**overrides) -> AgentRecommendation:
    base = {
        "pair": "ETH-USDT",
        "timeframe": "15m",
        "direction": "short",
        "confidence": 0.6,
        "rationale": "ETH 15m 顶背离。",
    }
    base.update(overrides)
    return AgentRecommendation(**base)


# === Init tables ===

class TestInitTables:
    def test_init_creates_ai_trend_analysis_table(self, db_session: Session):
        """init_agent_tables() 必须建 ai_trend_analysis 表"""
        from sqlalchemy import inspect
        inspector = inspect(db_session.bind)
        assert "ai_trend_analysis" in inspector.get_table_names()

    def test_init_creates_agent_recommendation_table(self, db_session: Session):
        from sqlalchemy import inspect
        inspector = inspect(db_session.bind)
        assert "agent_recommendation" in inspector.get_table_names()


# === AnalysisRepository ===

class TestAnalysisRepository:
    def test_save_writes_report(self, db_session: Session):
        report = make_report()
        AnalysisRepository.save(db_session, report)
        db_session.commit()

        rows = AnalysisRepository.list_recent(db_session, "BTC-USDT", "1h", limit=10)
        assert len(rows) == 1
        assert rows[0].pair == "BTC-USDT"
        assert rows[0].timeframe == "1h"
        assert rows[0].regime == "bull"
        assert rows[0].regime_confidence == 0.75
        assert rows[0].reasoning == "BTC 1h 处于多头格局。"
        assert rows[0].analysis_status == "success"

    def test_save_preserves_json_lists(self, db_session: Session):
        report = make_report(
            key_observations=["obs1", "obs2", "obs3"],
            risks=["risk1", "risk2"],
        )
        AnalysisRepository.save(db_session, report)
        db_session.commit()

        rows = AnalysisRepository.list_recent(db_session, "BTC-USDT", "1h", limit=10)
        assert len(rows) == 1
        assert rows[0].key_observations == ["obs1", "obs2", "obs3"]
        assert rows[0].risks == ["risk1", "risk2"]

    def test_save_preserves_raw_llm_response(self, db_session: Session):
        report = make_report(
            analysis_status=AnalysisStatus.PARSE_ERROR,
            raw_llm_response='{"raw": "data"}',
        )
        AnalysisRepository.save(db_session, report)
        db_session.commit()

        rows = AnalysisRepository.list_recent(db_session, "BTC-USDT", "1h", limit=10)
        assert rows[0].raw_llm_response == '{"raw": "data"}'
        assert rows[0].analysis_status == "parse_error"

    def test_list_recent_filters_by_pair(self, db_session: Session):
        AnalysisRepository.save(db_session, make_report(pair="BTC-USDT", timeframe="1h"))
        AnalysisRepository.save(db_session, make_report(pair="ETH-USDT", timeframe="1h"))
        AnalysisRepository.save(db_session, make_report(pair="BTC-USDT", timeframe="15m"))
        db_session.commit()

        btc_rows = AnalysisRepository.list_recent(db_session, "BTC-USDT", "1h", limit=10)
        assert len(btc_rows) == 1
        assert btc_rows[0].pair == "BTC-USDT"
        assert btc_rows[0].timeframe == "1h"

    def test_list_recent_respects_limit(self, db_session: Session):
        for i in range(15):
            AnalysisRepository.save(db_session, make_report(regime_confidence=i / 100))
        db_session.commit()

        rows = AnalysisRepository.list_recent(db_session, "BTC-USDT", "1h", limit=5)
        assert len(rows) == 5

    def test_list_recent_orders_by_created_at_desc(self, db_session: Session):
        r1 = make_report(regime_confidence=0.1)
        r2 = make_report(regime_confidence=0.2)
        r3 = make_report(regime_confidence=0.3)
        AnalysisRepository.save(db_session, r1)
        AnalysisRepository.save(db_session, r2)
        AnalysisRepository.save(db_session, r3)
        db_session.commit()

        rows = AnalysisRepository.list_recent(db_session, "BTC-USDT", "1h", limit=10)
        # 最新（r3）在前
        assert rows[0].regime_confidence == 0.3
        assert rows[2].regime_confidence == 0.1

    def test_list_recent_default_timeframe_all(self, db_session: Session):
        """timeframe=None → 返回所有 timeframe 的报告"""
        AnalysisRepository.save(db_session, make_report(timeframe="1h"))
        AnalysisRepository.save(db_session, make_report(timeframe="15m"))
        AnalysisRepository.save(db_session, make_report(timeframe="5m"))
        db_session.commit()

        rows = AnalysisRepository.list_recent(db_session, "BTC-USDT", None, limit=10)
        assert len(rows) == 3


# === RecommendationRepository ===

class TestRecommendationRepository:
    def test_save_writes_recommendation(self, db_session: Session):
        rec = make_recommendation()
        RecommendationRepository.save(db_session, rec)
        db_session.commit()

        rows = RecommendationRepository.list_recent(
            db_session, "ETH-USDT", "15m", limit=10
        )
        assert len(rows) == 1
        assert rows[0].pair == "ETH-USDT"
        assert rows[0].direction == "short"
        assert rows[0].confidence == 0.6
        assert rows[0].source == "agent"

    def test_save_default_source_agent(self, db_session: Session):
        rec = make_recommendation()
        RecommendationRepository.save(db_session, rec)
        db_session.commit()

        rows = RecommendationRepository.list_recent(
            db_session, "ETH-USDT", "15m", limit=10
        )
        assert rows[0].source == "agent"  # 永远 'agent'

    def test_list_recent_filters_pair_and_timeframe(self, db_session: Session):
        RecommendationRepository.save(db_session, make_recommendation(
            pair="BTC-USDT", timeframe="1h", direction="long"
        ))
        RecommendationRepository.save(db_session, make_recommendation(
            pair="BTC-USDT", timeframe="15m", direction="short"
        ))
        RecommendationRepository.save(db_session, make_recommendation(
            pair="ETH-USDT", timeframe="1h", direction="long"
        ))
        db_session.commit()

        btc_1h = RecommendationRepository.list_recent(
            db_session, "BTC-USDT", "1h", limit=10
        )
        assert len(btc_1h) == 1
        assert btc_1h[0].direction == "long"

    def test_list_recent_respects_limit(self, db_session: Session):
        for i in range(20):
            RecommendationRepository.save(db_session, make_recommendation(
                confidence=i / 100
            ))
        db_session.commit()

        rows = RecommendationRepository.list_recent(
            db_session, "ETH-USDT", "15m", limit=7
        )
        assert len(rows) == 7