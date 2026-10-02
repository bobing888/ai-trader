"""test_recommendation_history_schema — TDD: RecommendationHistory + RecommendationOutcome"""

from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, RecommendationHistory, RecommendationOutcome


def _make_session():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng, autoflush=False, autocommit=False)()


def test_recommendation_outcome_enum_values():
    assert RecommendationOutcome.HAS_SIGNAL.value == "has_signal"
    assert RecommendationOutcome.NO_SIGNAL.value == "no_signal"
    assert RecommendationOutcome.NO_DATA.value == "no_data"
    assert RecommendationOutcome.ERROR.value == "error"


def test_recommendation_history_roundtrip():
    db = _make_session()
    try:
        rec = RecommendationHistory(
            pair="BTC-USDT",
            timeframe="1h",
            has_signal=True,
            direction="long",
            confidence=0.85,
            regime="bull",
            regime_confidence=0.9,
            contributing_strategies='["momentum","breakout"]',
            reasons='["EMA金叉"]',
            suggested_leverage=2,
            min_agreement_used=2,
            fast_path=False,
            outcome=RecommendationOutcome.HAS_SIGNAL.value,
            scanned_at=datetime.now(UTC),
            source="okx",
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        fetched = db.query(RecommendationHistory).filter_by(id=rec.id).one()
        assert fetched.pair == "BTC-USDT"
        assert fetched.has_signal is True
        assert fetched.outcome == "has_signal"
        assert fetched.direction == "long"
        assert fetched.confidence == 0.85
    finally:
        db.close()


def test_recommendation_history_no_data_outcome():
    """NO_DATA 路径：has_signal=false, direction=None — 不应崩。"""
    db = _make_session()
    try:
        rec = RecommendationHistory(
            pair="ETH-USDT",
            timeframe="5m",
            has_signal=False,
            direction=None,
            confidence=None,
            regime=None,
            regime_confidence=None,
            outcome=RecommendationOutcome.NO_DATA.value,
            scanned_at=datetime.now(UTC),
            source="okx",
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        assert rec.has_signal is False
        assert rec.direction is None
        assert rec.outcome == "no_data"
    finally:
        db.close()


def test_recommendation_history_error_outcome():
    """ERROR 路径：recorder 算信号抛异常时。"""
    db = _make_session()
    try:
        rec = RecommendationHistory(
            pair="XRP-USDT",
            timeframe="1h",
            has_signal=False,
            direction=None,
            confidence=None,
            regime=None,
            regime_confidence=None,
            outcome=RecommendationOutcome.ERROR.value,
            scanned_at=datetime.now(UTC),
            source="okx",
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        assert rec.outcome == "error"
    finally:
        db.close()
