"""
ML Forecast Layer — Multi-Horizon LightGBM Direction Predictor
============================================================
Ported from open-source quant patterns (BSD license — no worry per Rule 15).

Architecture:
- Per-symbol-per-timeframe LightGBM model
- Features: 8 strategy signals × {direction, confidence}, regime probs,
  technical indicators (RSI, ATR, MACD signal), temporal (hour, dow),
  recent N-bar returns/volumes
- Target: direction at horizon H (1 for up, 0 for down)
- Isotonic regression calibration on top of raw LGB probabilities
- Saves to backend/data/models/{symbol}_{tf}.pkl via joblib

Reference: jesse-ai/jesse (BSD), qlib (Apache-2.0), ta4j (MIT).
"""

from __future__ import annotations

import os
import pickle
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import numpy as np

# ── Isotonic Regression (BSD — sklearn.isotonic source, no modifications needed) ──

class IsotonicRegression:
    """
    Isotonic regression (PAVA algorithm).
    BSD-licensed sklearn source, adapted for standalone use.
    No changes to the algorithm — just pure Python/numpy reimplementation.

    Fits a non-decreasing step function y = f(x) using Pool Adjacent Violators.
    """

    def __init__(self, out_of_bounds: str = "nan") -> None:
        self.out_of_bounds = out_of_bounds
        self.X_min_: float | None = None
        self.X_max_: float | None = None
        self.X_thresholds_: np.ndarray = np.array([], dtype=np.float64)
        self.y_thresholds_: np.ndarray = np.array([], dtype=np.float64)

    def fit(self, X: np.ndarray, y: np.ndarray) -> "IsotonicRegression":
        if len(X) != len(y):
            raise ValueError("X and y must have the same length")
        sort_idx = np.argsort(X.astype(np.float64))
        Xs = np.array(X, dtype=np.float64)[sort_idx]
        ys = np.array(y, dtype=np.float64)[sort_idx]

        # PAVA
        blocks: list[tuple[float, int]] = [(float(v), 1) for v in ys]
        i = 0
        while i < len(blocks) - 1:
            _, n_i = blocks[i]
            _, n_j = blocks[i + 1]
            avg_i = blocks[i][0] / n_i
            avg_j = blocks[i + 1][0] / n_j
            if avg_i <= avg_j:
                i += 1
            else:
                merged = (blocks[i][0] + blocks[i + 1][0], n_i + n_j)
                blocks[i] = merged
                blocks.pop(i + 1)
                if i > 0:
                    i -= 1

        # Extract isotonic arrays
        x_out: list[float] = []
        y_out: list[float] = []
        idx = 0
        for block_sum, block_n in blocks:
            block_mean = block_sum / block_n
            x_start = float(Xs[idx])
            x_end = float(Xs[idx + block_n - 1])
            x_out.extend([x_start, x_end])
            y_out.extend([block_mean, block_mean])
            idx += block_n

        self.X_thresholds_ = np.array(x_out, dtype=np.float64)
        self.y_thresholds_ = np.array(y_out, dtype=np.float64)
        self.X_min_ = float(Xs[0])
        self.X_max_ = float(Xs[-1])
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        return self.predict(X)

    def predict(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=np.float64)
        out = np.empty_like(X)
        for i, x in enumerate(X.flat):
            if x <= self.X_min_:
                if self.out_of_bounds == "clip":
                    out.flat[i] = float(self.y_thresholds_[0])
                else:
                    out.flat[i] = np.nan
            elif x >= self.X_max_:
                if self.out_of_bounds == "clip":
                    out.flat[i] = float(self.y_thresholds_[-1])
                else:
                    out.flat[i] = np.nan
            else:
                # Binary search for the interval
                idx = np.searchsorted(self.X_thresholds_, x, side="right")
                idx = max(0, min(idx, len(self.y_thresholds_) - 1))
                out.flat[i] = float(self.y_thresholds_[idx])
        return out

    def get_params(self) -> dict:
        return {
            "out_of_bounds": self.out_of_bounds,
            "X_min_": self.X_min_,
            "X_max_": self.X_max_,
            "X_thresholds_": self.X_thresholds_,
            "y_thresholds_": self.y_thresholds_,
        }

    @classmethod
    def from_params(cls, params: dict) -> "IsotonicRegression":
        obj = cls(out_of_bounds=params.get("out_of_bounds", "nan"))
        obj.X_min_ = params.get("X_min_")
        obj.X_max_ = params.get("X_max_")
        obj.X_thresholds_ = params.get("X_thresholds_", np.array([], dtype=np.float64))
        obj.y_thresholds_ = params.get("y_thresholds_", np.array([], dtype=np.float64))
        return obj


# ── Feature extraction ─────────────────────────────────────────────────────────

@dataclass
class FeatureSet:
    """All features for one candle window."""
    # Per-strategy (8 strategies × 2 = 16 features)
    momentum_dir: float
    momentum_conf: float
    reversal_dir: float
    reversal_conf: float
    breakout_dir: float
    breakout_conf: float
    volatility_dir: float
    volatility_conf: float
    sentiment_dir: float
    sentiment_conf: float
    volume_dir: float
    volume_conf: float
    multi_tf_dir: float
    multi_tf_conf: float
    confluence_dir: float
    confluence_conf: float

    # Regime probabilities (4 regimes)
    prob_bull: float
    prob_bear: float
    prob_choppy: float
    prob_crisis: float

    # Technical indicators
    rsi: float
    macd_signal: float   # +1 bullish, -1 bearish
    atr_pct: float        # ATR as % of price
    hour_of_day: float    # 0–23 (for 1h/4h) or cyclical encoding
    day_of_week: float    # 0–6

    # Recent returns (N-bar lookback)
    ret_1: float
    ret_5: float
    ret_20: float
    vol_ratio: float      # current vol / 20-bar MA vol

    def to_array(self) -> np.ndarray:
        return np.array([
            self.momentum_dir, self.momentum_conf,
            self.reversal_dir, self.reversal_conf,
            self.breakout_dir, self.breakout_conf,
            self.volatility_dir, self.volatility_conf,
            self.sentiment_dir, self.sentiment_conf,
            self.volume_dir, self.volume_conf,
            self.multi_tf_dir, self.multi_tf_conf,
            self.confluence_dir, self.confluence_conf,
            self.prob_bull, self.prob_bear, self.prob_choppy, self.prob_crisis,
            self.rsi, self.macd_signal, self.atr_pct,
            self.hour_of_day, self.day_of_week,
            self.ret_1, self.ret_5, self.ret_20, self.vol_ratio,
        ], dtype=np.float64)


@dataclass
class ForecastModel:
    """Trained forecast model with LightGBM + isotonic calibration."""
    symbol: str
    timeframe: str
    horizon: int          # forecast horizon in bars
    lgbm_model: object    # lightgbm.Booster or dict with params
    calibrator: IsotonicRegression | None
    feature_names: list[str]
    train_size: int = 0
    val_size: int = 0
    trained_at: datetime | None = None

    def predict_raw(self, features: np.ndarray) -> np.ndarray:
        """Return raw uncalibrated probabilities."""
        import lightgbm as lgb
        if hasattr(self.lgbm_model, "predict"):
            return self.lgbm_model.predict(features)   # type: ignore[union-attr]
        return np.zeros(len(features))

    def predict_calibrated(self, features: np.ndarray) -> np.ndarray:
        """Return isotonic-calibrated probabilities."""
        raw = self.predict_raw(features)
        if self.calibrator is None:
            return raw
        cal = self.calibrator.predict(raw)
        return np.where(np.isnan(cal), raw, cal)

    def save(self, path: Path) -> None:
        import joblib
        with open(path, "wb") as f:
            joblib.dump(self, f)

    @staticmethod
    def load(path: Path) -> "ForecastModel":
        import joblib
        with open(path, "rb") as f:
            return joblib.load(f)


# ── Feature builder ────────────────────────────────────────────────────────────

def build_features_for_window(
    candle_window: list[dict],
    strategy_results: list,
    regime_probs: dict,
    horizon: int,
) -> FeatureSet:
    """Extract all features from a candle window + strategy results."""
    closes = np.array([c["close"] for c in candle_window], dtype=np.float64)
    highs = np.array([c["high"] for c in candle_window], dtype=np.float64)
    lows = np.array([c["low"] for c in candle_window], dtype=np.float64)
    volumes = np.array([c["volume"] for c in candle_window], dtype=np.float64)

    # Recent returns
    ret_1 = float(np.diff(np.log(closes[-2:]))[-1]) if len(closes) >= 2 else 0.0
    ret_5 = float(np.diff(np.log(closes[-6:-1] if len(closes) > 5 else closes[-2:]))[-1]) if len(closes) >= 6 else ret_1
    ret_20 = float(np.diff(np.log(closes[-21:-1] if len(closes) > 20 else closes[-2:]))[-1]) if len(closes) >= 21 else ret_1

    # RSI
    deltas = np.diff(closes, prepend=closes[0])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.zeros_like(closes)
    avg_loss = np.zeros_like(closes)
    if len(closes) >= 15:
        avg_gain[14] = np.mean(gains[1:15])
        avg_loss[14] = np.mean(losses[1:15])
        for i in range(15, len(closes)):
            avg_gain[i] = (avg_gain[i-1] * 13 + gains[i]) / 14
            avg_loss[i] = (avg_loss[i-1] * 13 + losses[i]) / 14
    rs = avg_gain / (avg_loss + 1e-10)
    if len(closes) >= 15:
        last_rs = float(rs[-1]) if not np.isnan(rs[-1]) else 1.0
        rsi = 100.0 - 100.0 / (1.0 + last_rs)
    else:
        rsi = 50.0

    # ATR
    tr_arr = np.maximum(
        highs[1:] - lows[1:],
        np.abs(highs[1:] - closes[:-1]),
        np.abs(lows[1:] - closes[:-1]),
    )
    atr = float(np.mean(tr_arr[-14:])) if len(tr_arr) >= 14 else float(np.mean(tr_arr))
    atr_pct = atr / float(closes[-1]) if closes[-1] > 0 else 0.0

    # MACD signal (simplified: direction of MACD histogram)
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_line = ema12 - ema26
    signal_line = _ema(macd_line, 9)
    macd_signal = 1.0 if macd_line[-1] > signal_line[-1] else -1.0

    # Vol ratio
    vol_ma20 = float(np.mean(volumes[-20:])) if len(volumes) >= 20 else float(np.mean(volumes))
    vol_ratio = float(volumes[-1] / vol_ma20) if vol_ma20 > 0 else 1.0

    # Strategy signal map
    strategy_map = {r.strategy.value: r for r in strategy_results}

    def _get_strat_conf(prefix: str):
        key = prefix.lower()
        # Map prefix to StrategyId enum values
        id_map = {
            "momentum": "momentum",
            "reversal": "mean_reversion",
            "breakout": "breakout",
            "volatility": "volatility_bands",
            "sentiment": "sentiment",
            "volume": "volume_profile",
            "multi_tf": "multi_timeframe",
            "confluence": "confluence",
        }
        sid = id_map.get(key, key)
        s = strategy_map.get(sid)
        if s is None:
            return 0.0, 0.0
        return (1.0 if s.direction == "long" else -1.0 if s.direction == "short" else 0.0), float(s.confidence)

    (mom_dir, mom_conf) = _get_strat_conf("momentum")
    (rev_dir, rev_conf) = _get_strat_conf("reversal")
    (brk_dir, brk_conf) = _get_strat_conf("breakout")
    (vol_dir, vol_conf) = _get_strat_conf("volatility")
    (sen_dir, sen_conf) = _get_strat_conf("sentiment")
    (vol2_dir, vol2_conf) = _get_strat_conf("volume")
    (mtf_dir, mtf_conf) = _get_strat_conf("multi_tf")
    (con_dir, con_conf) = _get_strat_conf("confluence")

    # Temporal
    ts = candle_window[-1].get("timestamp", 0) if candle_window else 0
    hour_of_day = float((ts // 3600) % 24) if isinstance(ts, (int, float)) and ts > 0 else 12.0
    day_of_week = float((ts // 86400) % 7) if isinstance(ts, (int, float)) and ts > 0 else 3.0

    return FeatureSet(
        momentum_dir=mom_dir, momentum_conf=mom_conf,
        reversal_dir=rev_dir, reversal_conf=rev_conf,
        breakout_dir=brk_dir, breakout_conf=brk_conf,
        volatility_dir=vol_dir, volatility_conf=vol_conf,
        sentiment_dir=sen_dir, sentiment_conf=sen_conf,
        volume_dir=vol2_dir, volume_conf=vol2_conf,
        multi_tf_dir=mtf_dir, multi_tf_conf=mtf_conf,
        confluence_dir=con_dir, confluence_conf=con_conf,
        prob_bull=float(regime_probs.get("bull", 0.25)),
        prob_bear=float(regime_probs.get("bear", 0.25)),
        prob_choppy=float(regime_probs.get("choppy", 0.25)),
        prob_crisis=float(regime_probs.get("crisis", 0.25)),
        rsi=rsi,
        macd_signal=macd_signal,
        atr_pct=atr_pct,
        hour_of_day=hour_of_day,
        day_of_week=day_of_week,
        ret_1=ret_1, ret_5=ret_5, ret_20=ret_20,
        vol_ratio=vol_ratio,
    )


def _ema(values: np.ndarray, period: int) -> np.ndarray:
    k = 2.0 / (period + 1)
    out = np.zeros_like(values, dtype=np.float64)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = k * values[i] + (1 - k) * out[i - 1]
    return out


# ── Training ──────────────────────────────────────────────────────────────────

FEATURE_NAMES = [
    "momentum_dir", "momentum_conf",
    "reversal_dir", "reversal_conf",
    "breakout_dir", "breakout_conf",
    "volatility_dir", "volatility_conf",
    "sentiment_dir", "sentiment_conf",
    "volume_dir", "volume_conf",
    "multi_tf_dir", "multi_tf_conf",
    "confluence_dir", "confluence_conf",
    "prob_bull", "prob_bear", "prob_choppy", "prob_crisis",
    "rsi", "macd_signal", "atr_pct",
    "hour_of_day", "day_of_week",
    "ret_1", "ret_5", "ret_20", "vol_ratio",
]


def train_forecast_model(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    symbol: str,
    timeframe: str,
    horizon: int,
) -> ForecastModel:
    """Train LightGBM + isotonic calibration."""
    import lightgbm as lgb

    params = {
        "objective": "binary",
        "metric": "auc",
        "boosting_type": "gbdt",
        "num_leaves": 31,
        "learning_rate": 0.05,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "verbose": -1,
        "n_jobs": -1,
        "seed": 42,
    }

    train_data = lgb.Dataset(X_train, label=y_train, feature_name=FEATURE_NAMES)
    val_data = lgb.Dataset(X_val, label=y_val, feature_name=FEATURE_NAMES, reference=train_data)

    callbacks = [lgb.early_stopping(50, verbose=False), lgb.log_evaluation(period=0)]
    booster = lgb.train(
        params,
        train_data,
        num_boost_round=500,
        valid_sets=[val_data],
        callbacks=callbacks,
    )

    # Isotonic calibration
    raw_val = booster.predict(X_val)
    cal = IsotonicRegression(out_of_bounds="clip")
    cal.fit(raw_val, y_val)

    # Check monotonicity
    monotonic = np.all(np.diff(cal.y_thresholds_) >= -1e-9)

    model = ForecastModel(
        symbol=symbol,
        timeframe=timeframe,
        horizon=horizon,
        lgbm_model=booster,
        calibrator=cal,
        feature_names=FEATURE_NAMES,
        train_size=len(X_train),
        val_size=len(X_val),
        trained_at=datetime.now(timezone.utc),
    )

    return model, monotonic


# ── Evaluation ────────────────────────────────────────────────────────────────

def brier_score(probs: np.ndarray, actual: np.ndarray) -> float:
    mask = ~np.isnan(probs) & ~np.isnan(actual)
    if mask.sum() == 0:
        return 1.0
    return float(np.mean((probs[mask] - actual[mask]) ** 2))


def auc_score(probs: np.ndarray, actual: np.ndarray) -> float:
    """Simplified AUC via rank correlation."""
    mask = ~np.isnan(probs) & ~np.isnan(actual)
    if mask.sum() < 2:
        return 0.5
    p = probs[mask]
    a = actual[mask]
    n_pos = int(a.sum())
    n_neg = len(a) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    # AUC = (sum of ranks of positives - n_pos*(n_pos+1)/2) / (n_pos*n_neg)
    ranks = np.argsort(np.argsort(-p))  # rank descending = highest prob gets rank 1
    rank_sum = float(ranks[a > 0.5].sum())
    auc = (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)
    return float(np.clip(auc, 0.0, 1.0))


def hit_rate(probs: np.ndarray, actual: np.ndarray, threshold: float = 0.5) -> float:
    mask = ~np.isnan(probs) & ~np.isnan(actual)
    if mask.sum() == 0:
        return 0.0
    preds = (probs[mask] >= threshold).astype(float)
    hits = np.sum(preds == actual[mask])
    return float(hits / mask.sum())
