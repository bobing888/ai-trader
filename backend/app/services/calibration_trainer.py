"""Calibration trainer — 24h 自动重训 (lifespan 注册)。

从 RecommendationHistory 表扫描 (raw_confidence, actual_pnl_pct) 样本,
按 timeframe 聚合, ≥MIN_TRAIN_SAMPLES(100) 就调 train_calibrator()。

修复记录 (2026-10-03):
  - 旧版 train_calibrator() 在生产代码里**零 caller**,calibrated_confidence 永远 None
  - 现在 lifespan 启动 + 每 24h 重训一次,即使冷启动也能逐步走到 calibrated 状态
"""
from __future__ import annotations

import asyncio
import logging
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.signals.calibration import (
    MIN_TRAIN_SAMPLES,
    train_calibrator,
)
from app.db.models import RecommendationHistory

log = logging.getLogger(__name__)

TRAINER_LOOP_HOURS = 24
TRAINER_INTERVAL_SECONDS = TRAINER_LOOP_HOURS * 3600


def _collect_samples(db: Session, timeframe: str) -> list[tuple[float, float]]:
    """从 recommendation_history 拉 (raw_confidence, pnl_pct) 样本, 过滤 outcome_label != PENDING."""
    rows = db.execute(
        select(RecommendationHistory)
        .where(
            RecommendationHistory.timeframe == timeframe,
            RecommendationHistory.outcome_label.is_not(None),
            RecommendationHistory.outcome_label != "pending",
            RecommendationHistory.confidence.is_not(None),
            RecommendationHistory.pnl_pct.is_not(None),
        )
    ).scalars().all()
    return [(float(r.confidence), float(r.pnl_pct)) for r in rows]


def retrain_all_timeframes(db_factory) -> dict[str, int]:
    """扫描所有监控 timeframe, 样本够就训练。返回 {timeframe: sample_count}。"""
    results: dict[str, int] = {}
    for tf in settings.recommendation_timeframes:
        try:
            db: Session = db_factory()
            try:
                samples = _collect_samples(db, tf)
            finally:
                db.close()
            results[tf] = len(samples)
            if len(samples) >= MIN_TRAIN_SAMPLES:
                train_calibrator(tf, samples)
                log.info("[calibration_trainer] %s trained with %d samples", tf, len(samples))
            else:
                log.info(
                    "[calibration_trainer] %s skipped: %d < %d samples",
                    tf, len(samples), MIN_TRAIN_SAMPLES,
                )
        except Exception as e:
            log.warning("[calibration_trainer] %s failed: %s", tf, e)
            results[tf] = -1
    return results


async def calibration_trainer_loop(
    session_factory,
    interval_seconds: int = TRAINER_INTERVAL_SECONDS,
) -> None:
    """每 24h 重训一次 calibrator。 lifespan 中以 asyncio.create_task 启动。"""
    while True:
        try:
            log.info("[calibration_trainer] tick: scanning recommendation_history")
            # 阻塞部分放到 default executor 防止阻塞 event loop
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None, retrain_all_timeframes, session_factory,
            )
            log.info("[calibration_trainer] scan done: %s", results)
        except Exception as e:
            log.exception("[calibration_trainer] tick failed: %s", e)
        await asyncio.sleep(interval_seconds)
