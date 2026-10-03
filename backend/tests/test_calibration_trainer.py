"""Test calibration_trainer — 从 recommendation_history 自动重训 calibrator。"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, RecommendationHistory, RecommendationOutcome
from app.services.calibration_trainer import _collect_samples, retrain_all_timeframes


@pytest.fixture
def tmp_db():
    """in-memory sqlite session."""
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    SessionLocal = sessionmaker(bind=eng, autoflush=False, autocommit=False)
    return SessionLocal()


def _make_record(
    db,
    *,
    timeframe: str = "1h",
    confidence: float = 0.6,
    pnl_pct: float = 0.002,
    outcome_label: str = "hit_tp",
    age_minutes: int = 60,
):
    scanned_at = datetime.now(UTC) - timedelta(minutes=age_minutes)
    rec = RecommendationHistory(
        pair="BTC-USDT",
        timeframe=timeframe,
        has_signal=True,
        direction="long",
        confidence=confidence,
        regime="bull",
        regime_confidence=0.5,
        outcome=RecommendationOutcome.HAS_SIGNAL.value,
        scanned_at=scanned_at,
        source="okx",
        outcome_label=outcome_label,
        pnl_pct=pnl_pct,
        closed_at=scanned_at + timedelta(minutes=5),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def test_collect_samples_filters_pending_and_none(tmp_db):
    """PENDING / None 应当被过滤掉."""
    _make_record(tmp_db, outcome_label="pending", confidence=0.7, pnl_pct=None)
    _make_record(tmp_db, outcome_label="hit_tp", confidence=0.65, pnl_pct=0.003)
    _make_record(tmp_db, outcome_label="hit_sl", confidence=0.55, pnl_pct=-0.002)

    samples = _collect_samples(tmp_db, "1h")
    # 第一条被过滤 (PENDING),后两条保留
    assert len(samples) == 2
    confidences = [s[0] for s in samples]
    assert 0.65 in confidences
    assert 0.55 in confidences


def test_collect_samples_per_timeframe(tmp_db):
    """不同 timeframe 互不干扰."""
    _make_record(tmp_db, timeframe="1h", confidence=0.6, pnl_pct=0.001)
    _make_record(tmp_db, timeframe="4h", confidence=0.7, pnl_pct=0.002)

    samples_1h = _collect_samples(tmp_db, "1h")
    samples_4h = _collect_samples(tmp_db, "4h")
    assert len(samples_1h) == 1
    assert samples_1h[0][0] == 0.6
    assert len(samples_4h) == 1
    assert samples_4h[0][0] == 0.7


def test_retrain_skips_when_samples_below_threshold(tmp_db, monkeypatch):
    """样本 < 100 时不调 train_calibrator."""
    from app.services import calibration_trainer as trainer_mod

    called_with: list = []

    def _spy_train(tf, samples):
        called_with.append((tf, len(samples)))
        return None

    monkeypatch.setattr(trainer_mod, "train_calibrator", _spy_train)
    # 只写 5 条 < 100
    for i in range(5):
        _make_record(tmp_db, confidence=0.5 + i * 0.05, pnl_pct=0.001 * (i + 1))

    results = retrain_all_timeframes(lambda: tmp_db)
    # 5 < 100 → 不调 train_calibrator
    assert all(v < 100 for v in results.values() if v > 0)
    assert called_with == [], f"应不调用 train_calibrator,实际调了: {called_with}"


def test_retrain_calls_train_when_samples_above_threshold(tmp_db, monkeypatch):
    """样本 ≥ 100 时调 train_calibrator."""
    from app.services import calibration_trainer as trainer_mod

    called_with: list = []

    def _spy_train(tf, samples):
        called_with.append((tf, len(samples)))
        return None

    monkeypatch.setattr(trainer_mod, "train_calibrator", _spy_train)
    # 写 105 条 1h 记录
    for i in range(105):
        _make_record(
            tmp_db,
            timeframe="1h",
            confidence=0.5 + (i % 50) * 0.01,
            pnl_pct=0.001 * (i % 7),
        )

    results = retrain_all_timeframes(lambda: tmp_db)
    assert ("1h", 105) in called_with, f"应调 train_calibrator('1h', 105 samples), 实际 {called_with}"
