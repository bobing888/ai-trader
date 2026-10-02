"""Per-timeframe Isotonic 校准 — 把 raw_confidence 映射为真实胜率估计。

训练样本: (raw_confidence, actual_pnl_pct) → 二值化 (pnl > 0) → Isotonic regression。

冷启动 < 100 样本: calibrate() 返 None, calibrated_confidence 字段写 NULL。

不依赖 sklearn — 用纯 numpy 实现 Pool Adjacent Violators Algorithm (PAVA)。
"""
from __future__ import annotations

import logging
import os
import pickle
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import numpy as np

log = logging.getLogger(__name__)

CALIBRATION_STORE = os.getenv("CALIBRATION_STORE", "backend/app/calibration_store")
MIN_TRAIN_SAMPLES = 100
MIN_TRAIN_SAMPLES_ABSOLUTE = 10   # < 此数直接报错
BRIER_THRESHOLD = 0.20

# 模块级 cache：{timeframe: CalibrationModel}
_calibrators: dict[str, "CalibrationModel"] = {}


@dataclass
class CalibrationModel:
    timeframe: str
    iso_x: np.ndarray = field(default_factory=lambda: np.array([]))
    iso_y: np.ndarray = field(default_factory=lambda: np.array([]))
    train_size: int = 0
    train_brier_score: float = 1.0
    trained_at: datetime | None = None

    @property
    def is_ready(self) -> bool:
        return self.train_size >= MIN_TRAIN_SAMPLES

    def predict(self, raw_conf: float) -> float:
        if not self.is_ready or len(self.iso_x) == 0:
            return float(np.clip(raw_conf, 0.0, 1.0))
        # Step interpolation: left of min(x) → y[0]; right → y[-1]
        if raw_conf <= self.iso_x[0]:
            return float(np.clip(self.iso_y[0], 0.0, 1.0))
        if raw_conf >= self.iso_x[-1]:
            return float(np.clip(self.iso_y[-1], 0.0, 1.0))
        # In-range: nearest bin
        idx = int(np.searchsorted(self.iso_x, raw_conf))
        idx = max(0, min(idx, len(self.iso_x) - 1))
        return float(np.clip(self.iso_y[idx], 0.0, 1.0))


class _PAVAIsotonic:
    """Pool Adjacent Violators Algorithm — 纯 numpy。

    Input: y (1-D target array), assumes x is uniform (we don't expose x because
    训练样本已经按 raw_confidence 排序后传入)。
    """

    @staticmethod
    def fit(sorted_targets: np.ndarray) -> np.ndarray:
        """Return monotonic-non-decreasing fitted y."""
        if len(sorted_targets) == 0:
            return np.array([])
        n = len(sorted_targets)
        # Each block = (sum, count)
        blocks: list[tuple[float, int]] = [(float(v), 1) for v in sorted_targets]
        i = 0
        while i < len(blocks) - 1:
            sum_i, n_i = blocks[i]
            sum_j, n_j = blocks[i + 1]
            avg_i = sum_i / n_i
            avg_j = sum_j / n_j
            if avg_i <= avg_j:
                i += 1
            else:
                merged_n = n_i + n_j
                merged_sum = sum_i + sum_j
                blocks[i] = (merged_sum, merged_n)
                blocks.pop(i + 1)
                if i > 0:
                    i -= 1
        # Reconstruct y
        iso_y = np.zeros(n)
        idx = 0
        for block_sum, block_n in blocks:
            iso_y[idx:idx + block_n] = block_sum / block_n
            idx += block_n
        return iso_y


def _store_path(timeframe: str) -> Path:
    store = Path(CALIBRATION_STORE)
    store.mkdir(parents=True, exist_ok=True)
    return store / f"{timeframe}.pkl"


def train_calibrator(
    timeframe: str,
    samples: Sequence[tuple[float, float]],
) -> CalibrationModel:
    """训练一个 per-timeframe Isotonic 校准器。

    Args:
        timeframe: e.g. "1m" / "5m" / "15m" / "1h" / "4h" / "1d"
        samples: list of (raw_confidence, actual_pnl_pct) pairs

    Returns:
        训练好的 CalibrationModel（已写入 .pkl）

    Raises:
        ValueError: < 10 样本
    """
    if len(samples) < MIN_TRAIN_SAMPLES_ABSOLUTE:
        raise ValueError(f"need ≥{MIN_TRAIN_SAMPLES_ABSOLUTE} samples, got {len(samples)}")

    raw = np.array([s[0] for s in samples], dtype=float)
    pnl = np.array([s[1] for s in samples], dtype=float)
    win = (pnl > 0).astype(float)

    # 按 raw 升序排
    sort_idx = np.argsort(raw)
    win_sorted = win[sort_idx]
    raw_sorted = raw[sort_idx]

    # PAVA
    iso_y = _PAVAIsotonic.fit(win_sorted)
    iso_x = raw_sorted  # 用原始 raw 作为 x

    # Brier score
    preds = np.array([float(np.interp(r, iso_x, iso_y)) for r in raw])
    brier = float(((preds - win) ** 2).mean())

    model = CalibrationModel(
        timeframe=timeframe,
        iso_x=iso_x,
        iso_y=iso_y,
        train_size=len(samples),
        train_brier_score=brier,
        trained_at=datetime.now(timezone.utc),
    )

    # 持久化（不论 Brier 是否合格 — 用于事后诊断；只有 is_ready=True 才会被 get_calibrator 加载）
    pkl_path = _store_path(timeframe)
    try:
        with open(pkl_path, "wb") as f:
            pickle.dump(model, f)
    except Exception as e:
        log.warning("calibration: failed to persist %s: %s", timeframe, e)

    # 内存 cache:仅 is_ready 时更新（否则保留旧版）
    if model.is_ready and brier <= BRIER_THRESHOLD:
        _calibrators[timeframe] = model
        log.info(
            "calibration: trained %s, n=%d, Brier=%.4f",
            timeframe, len(samples), brier,
        )
    elif not model.is_ready:
        log.info(
            "calibration: %s trained with only %d samples (need %d) — not ready",
            timeframe, len(samples), MIN_TRAIN_SAMPLES,
        )
    else:
        log.warning(
            "calibration: %s trained with Brier=%.4f > %.2f, NOT updating in-memory cache",
            timeframe, brier, BRIER_THRESHOLD,
        )
    return model


def get_calibrator(timeframe: str) -> CalibrationModel | None:
    """懒加载：先看内存 cache，无则从 .pkl 加载。"""
    if timeframe in _calibrators:
        return _calibrators[timeframe]
    pkl_path = _store_path(timeframe)
    if not pkl_path.exists():
        return None
    try:
        with open(pkl_path, "rb") as f:
            model = pickle.load(f)
    except Exception as e:
        log.warning("calibration: failed to load %s.pkl: %s", timeframe, e)
        return None
    if not model.is_ready:
        return None
    _calibrators[timeframe] = model
    return model


def calibrate(raw_confidence: float, timeframe: str) -> float | None:
    """获取校准后的胜率估计。

    Args:
        raw_confidence: 来自 aggregator 的原始 confidence (0~1)
        timeframe: 该 confidence 所属的 timeframe

    Returns:
        校准后的胜率 (0~1)；None 表示 calibrator 未就绪（冷启动）。
    """
    model = get_calibrator(timeframe)
    if model is None or not model.is_ready:
        return None
    return model.predict(float(raw_confidence))


def clear_cache() -> None:
    """清空内存 cache (测试用)"""
    _calibrators.clear()