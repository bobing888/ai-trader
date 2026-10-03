# Signal Credibility Phase 1 — Implementation Plan

> **For implementers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended)
> for parallel task dispatch, or executing-plans for inline sequential work.
> Each task is a checkbox (`- [ ]`) with RED → GREEN → commit flow.

**Goal:** Make ai-trader's recommendation `confidence` a real, calibrated win-rate estimate.
Make `BacktestPage` show real walk-forward backtest results (not mock).
All signal-side decisions are cost-aware (OKX taker 0.08% / slippage 0.05%).

**Architecture:** Per-timeframe Isotonic calibration on historical (confidence, PnL) pairs +
walk-forward backtest over real OKX K-lines + outcome worker (5-min scanner) that closes
pending recommendations by TP/SL/expiry + DB schema extensions + new `/api/backtest` endpoint
+ BacktestPage rewrite.

**Tech Stack:**
- Backend: Python 3.11 / SQLAlchemy / FastAPI / numpy / sklearn-isotonic (or hand-rolled)
- Frontend: React 19 / TypeScript / recharts / zustand / react-query
- Data source: existing OKX public REST API (1m/5m/15m/1h/4h/1d)
- Storage: existing backend/app/db/models.py (extend in-place)

---

## Spec

This plan follows from `docs/superpowers/specs/2026-10-02-signal-credibility-phase1.md`.

Both spec and plan must be read before implementation.

---

## Review Focus

Five input/failure modes the spec implicitly assumes but no task directly tests:

1. **Calibration on cold start** — fewer than 100 samples. Behavior: `calibrate()` returns None,
   `calibrated_confidence` field is NULL, frontend shows "calibrating...". Owned by Task 2.
2. **Outcome worker over a delisted symbol** — K-line fetch returns 404. Behavior: skip record
   + log warning, don't crash. Owned by Task 3.
3. **Backtest concurrency on same symbol** — two POSTs simultaneously. Behavior: serialize via
   `BacktestRun.status = 'running'` check, second request returns 409. Owned by Task 4.
4. **Empty walk-forward window** — less than 30 days of K-lines. Behavior: 422 with explicit
   message. Owned by Task 4.
5. **OutcomeLabel enum sync between backend and frontend** — adding a new label value. Behavior:
   frontend type-check catches missing label. Owned by Task 6.

---

## Task 1: Cost Model + DB Schema Extension

**Files:**
- Create: `backend/app/signals/cost_model.py` (~80 lines)
- Modify: `backend/app/db/models.py:1-15` (add new imports)
- Modify: `backend/app/db/models.py:160-210` (add fields to RecommendationHistory)
- Modify: `backend/app/db/models.py:215-260` (add BacktestRun + BacktestTrade classes)
- Create: `backend/tests/test_cost_model.py` (~80 lines)
- Create: `backend/alembic/versions/2026_10_10_signal_credibility_phase1.py` (or manual ALTER TABLE)
- Create: `backend/app/db/migrations.sql` (manual migration for SQLite)

**Interfaces:**
- Consumes: nothing
- Produces:
  - `from app.signals.cost_model import estimate_cost, estimate_round_trip_cost, is_profitable_threshold, CostEstimate`
  - `from app.db.models import RecommendationHistory, BacktestRun, BacktestTrade, OutcomeLabel`

### Step 1.1: Write failing test for cost_model

```python
# tests/test_cost_model.py
from app.signals.cost_model import (
    estimate_cost, estimate_round_trip_cost,
    is_profitable_threshold, CostEstimate,
)

def test_okx_taker_fee_default():
    assert estimate_cost(side="entry") == pytest.approx(0.0008)
    assert estimate_cost(side="exit") == pytest.approx(0.0008)

def test_round_trip_includes_slippage():
    cost = estimate_round_trip_cost()
    # 0.0008 + 0.0008 + 0.0005 = 0.0021
    assert cost == pytest.approx(0.0021)

def test_threshold_variance_with_confidence():
    # target=0.5%, conf=0.5 → 0.25% < 0.21% (round trip) → unprofitable
    assert is_profitable_threshold(target_pct=0.005, confidence=0.5) is False
    # target=0.5%, conf=0.7 → 0.35% > 0.21% → profitable
    assert is_profitable_threshold(target_pct=0.005, confidence=0.7) is True

def test_cost_overridable_via_env(monkeypatch):
    monkeypatch.setenv("OKX_TAKER_FEE_BPS", "10.0")
    assert estimate_cost(side="entry") == pytest.approx(0.001)
```

### Step 1.2: Run tests, expect FAIL
```bash
cd backend && PYTHONPATH=. python3 -m pytest tests/test_cost_model.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.signals.cost_model'`

### Step 1.3: Implement cost_model.py

```python
# backend/app/signals/cost_model.py
"""OKX 手续费 + 滑点模型。

用户超短线 = taker 为主 (0.08%)。
Slippage 默认 0.05% (固定)，可走 ATR-adaptive 退化。
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Literal

Side = Literal["entry", "exit"]

# OKX 公开默认费率
DEFAULT_TAKER_FEE_BPS = float(os.getenv("OKX_TAKER_FEE_BPS", "8.0"))   # 0.08%
DEFAULT_MAKER_FEE_BPS = float(os.getenv("OKX_MAKER_FEE_BPS", "2.0"))   # 0.02%
DEFAULT_SLIPPAGE_BPS = float(os.getenv("SLIPPAGE_BPS", "5.0"))        # 0.05%


@dataclass(frozen=True)
class CostEstimate:
    entry_fee_pct: float
    exit_fee_pct: float
    slippage_pct: float
    total_round_trip_pct: float

    @property
    def total_round_trip_bps(self) -> float:
        return self.total_round_trip_pct * 10_000


def estimate_cost(side: Side) -> float:
    """OKX taker 0.08%（单边）。"""
    return DEFAULT_TAKER_FEE_BPS / 10_000


def estimate_round_trip_cost(slippage_mode: Literal["fixed", "atr"] = "fixed") -> CostEstimate:
    entry = estimate_cost("entry")
    exit_ = estimate_cost("exit")
    slip = DEFAULT_SLIPPAGE_BPS / 10_000 if slippage_mode == "fixed" else DEFAULT_SLIPPAGE_BPS / 10_000
    total = entry + exit_ + slip
    return CostEstimate(entry, exit_, slip, total)


def is_profitable_threshold(target_pct: float, confidence: float) -> bool:
    """E[net_pnl] = target_pct * confidence > round_trip 才算「有 alpha」。"""
    cost = estimate_round_trip_cost().total_round_trip_pct
    return target_pct * confidence > cost
```

### Step 1.4: Run tests, expect PASS
```bash
cd backend && PYTHONPATH=. python3 -m pytest tests/test_cost_model.py -v
```
Expected: 4 passed

### Step 1.5: Write failing test for DB schema

```python
# tests/test_db_schema_phase1.py
from app.db.models import RecommendationHistory, BacktestRun, BacktestTrade, OutcomeLabel
from sqlalchemy import inspect

def test_recommendation_history_has_new_fields():
    cols = {c.name for c in RecommendationHistory.__table__.columns}
    assert "calibrated_confidence" in cols
    assert "net_pnl_estimate" in cols
    assert "holding_minutes" in cols
    assert "outcome_label" in cols
    assert "pnl_pct" in cols
    assert "closed_at" in cols

def test_backtest_run_table_exists():
    cols = {c.name for c in BacktestRun.__table__.columns}
    for f in ("id", "symbol", "timeframe", "strategies", "days",
              "fee_taker_bps", "slippage_bps", "min_confidence",
              "target_pct", "stop_pct", "max_hold_minutes",
              "started_at", "finished_at", "total_trades", "hit_rate",
              "net_pnl_pct", "sharpe_ratio", "max_drawdown_pct",
              "equity_curve", "status", "error_message"):
        assert f in cols

def test_outcome_label_enum_values():
    assert {e.value for e in OutcomeLabel} == {
        "PENDING", "HIT_TP", "HIT_SL", "EXPIRED", "HOLD",
    }
```

### Step 1.6: Run tests, expect FAIL
```bash
cd backend && PYTHONPATH=. python3 -m pytest tests/test_db_schema_phase1.py -v
```
Expected: `AssertionError` on missing fields

### Step 1.7: Extend models.py + create migration SQL

```python
# backend/app/db/models.py — append new enum + extend RecommendationHistory + add 2 classes

class OutcomeLabel(StrEnum):
    PENDING = "pending"
    HIT_TP = "hit_tp"
    HIT_SL = "hit_sl"
    EXPIRED = "expired"
    HOLD = "hold"

# Add to RecommendationHistory (existing):
#  calibrated_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
#  net_pnl_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
#  holding_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
#  outcome_label: Mapped[str | None] = mapped_column(String(20), nullable=True)
#  pnl_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
#  closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
# + Index("idx_rec_history_tf_outcome", "timeframe", "outcome_label")

class BacktestRun(Base):
    __tablename__ = "backtest_runs"
    # ... full columns per spec 4.2

class BacktestTrade(Base):
    __tablename__ = "backtest_trades"
    # ... full columns per spec 4.3
```

```sql
-- backend/app/db/migrations.sql
ALTER TABLE recommendation_history ADD COLUMN calibrated_confidence FLOAT;
ALTER TABLE recommendation_history ADD COLUMN net_pnl_estimate FLOAT;
ALTER TABLE recommendation_history ADD COLUMN holding_minutes INTEGER;
ALTER TABLE recommendation_history ADD COLUMN outcome_label VARCHAR(20);
ALTER TABLE recommendation_history ADD COLUMN pnl_pct FLOAT;
ALTER TABLE recommendation_history ADD COLUMN closed_at DATETIME;
CREATE INDEX idx_rec_history_tf_outcome ON recommendation_history(timeframe, outcome_label);
CREATE TABLE backtest_runs (...);   -- per spec 4.2
CREATE TABLE backtest_trades (...); -- per spec 4.3
```

Apply migration: `sqlite3 backend/data/ai_trader.db < backend/app/db/migrations.sql`

### Step 1.8: Run tests, expect PASS
```bash
cd backend && PYTHONPATH=. python3 -m pytest tests/test_db_schema_phase1.py tests/test_cost_model.py -v
```
Expected: 7 passed

### Step 1.9: Commit
```bash
cd /Users/hahaha/Desktop/CODE/ai-trader
git add backend/app/signals/cost_model.py backend/app/db/models.py \
        backend/app/db/migrations.sql backend/tests/test_cost_model.py \
        backend/tests/test_db_schema_phase1.py
git commit -m "feat(phase1): cost model + DB schema extension"
```

---

## Task 2: Calibration Module (Isotonic per-Timeframe)

**Files:**
- Create: `backend/app/signals/calibration.py` (~150 lines)
- Create: `backend/app/calibration_store/` (dir for .pkl files)
- Create: `backend/tests/test_calibration.py` (~120 lines)

**Interfaces:**
- Consumes: `CostEstimate` from cost_model
- Produces:
  - `from app.signals.calibration import get_calibrator, train_calibrator, calibrate, CalibrationModel`

### Step 2.1: Write failing test

```python
# tests/test_calibration.py
import numpy as np
from app.signals.calibration import (
    train_calibrator, calibrate, get_calibrator, CalibrationModel,
)

def test_train_calibrator_on_synthetic_data(tmp_path, monkeypatch):
    monkeypatch.setattr("app.signals.calibration.CALIBRATION_STORE", str(tmp_path))
    # 造 1000 个 sample: 真实胜率与 confidence 强相关
    rng = np.random.default_rng(42)
    raw = rng.uniform(0, 1, 1000)
    pnl = (raw - 0.5) * 0.02 + rng.normal(0, 0.005, 1000)
    samples = list(zip(raw.tolist(), pnl.tolist()))
    model = train_calibrator(timeframe="1h", samples=samples)
    assert model.is_ready is True
    assert model.brier_score < 0.15
    assert model.train_size == 1000

def test_calibrate_returns_calibrated_value(tmp_path, monkeypatch):
    monkeypatch.setattr("app.signals.calibration.CALIBRATION_STORE", str(tmp_path))
    rng = np.random.default_rng(42)
    raw = rng.uniform(0, 1, 200)
    pnl = (raw - 0.5) * 0.02 + rng.normal(0, 0.005, 200)
    train_calibrator("5m", list(zip(raw.tolist(), pnl.tolist())))
    result = calibrate(raw_confidence=0.7, timeframe="5m")
    assert result is not None
    assert 0.0 <= result <= 1.0

def test_calibrate_returns_none_when_cold_start(tmp_path, monkeypatch):
    monkeypatch.setattr("app.signals.calibration.CALIBRATION_STORE", str(tmp_path))
    # No model trained yet
    result = calibrate(raw_confidence=0.7, timeframe="15m")
    assert result is None

def test_per_timeframe_separation(tmp_path, monkeypatch):
    monkeypatch.setattr("app.signals.calibration.CALIBRATION_STORE", str(tmp_path))
    # 1h 模型 training
    samples_1h = [(0.5, 0.001), (0.7, 0.005), (0.9, 0.012)]
    train_calibrator("1h", samples_1h)
    # 1m 模型 training
    samples_1m = [(0.5, -0.001), (0.7, 0.001), (0.9, 0.005)]
    train_calibrator("1m", samples_1m)
    # 两个 calibrator 必须独立
    model_1h = get_calibrator("1h")
    model_1m = get_calibrator("1m")
    assert model_1h.timeframe == "1h"
    assert model_1m.timeframe == "1m"
    # 1m 在 0.7 处期望 win rate 较低（因为 samples 显示 0.001）
    p_1h = calibrate(0.7, "1h")
    p_1m = calibrate(0.7, "1m")
    assert p_1h is not None and p_1m is not None
    assert p_1h > p_1m
```

### Step 2.2: Run tests, expect FAIL
```bash
cd backend && PYTHONPATH=. python3 -m pytest tests/test_calibration.py -v
```
Expected: ModuleNotFoundError

### Step 2.3: Implement calibration.py

```python
# backend/app/signals/calibration.py
"""Per-timeframe Isotonic 校准 — 把 raw_confidence 映射为真实胜率估计。

训练样本: (raw_confidence, actual_pnl_pct)。
冷启动 <100 样本: calibrate() 返 None, calibrated_confidence 字段写 NULL。
"""
from __future__ import annotations
import os
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence
from pathlib import Path
import pickle

CALIBRATION_STORE = os.getenv("CALIBRATION_STORE", "backend/app/calibration_store")
MIN_TRAIN_SAMPLES = 100
BRIER_THRESHOLD = 0.20

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
        if not self.is_ready:
            return raw_conf
        # numpy interpolation over iso_x, iso_y
        idx = np.searchsorted(self.iso_x, raw_conf)
        idx = np.clip(idx, 0, len(self.iso_x) - 1)
        return float(self.iso_y[idx])


class _IsotonicRegression:
    """手写 Isotonic regression (Pool Adjacent Violators Algorithm)。
    避免引入 sklearn-isotonic 依赖，纯净 numpy。
    """

    @staticmethod
    def fit(y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """输入 y (target)，按 x = 索引升序做 PAVA。"""
        blocks = [(float(v), 1) for v in y]
        # PAVA
        i = 0
        while i < len(blocks) - 1:
            avg_i, n_i = blocks[i]
            avg_j, n_j = blocks[i + 1]
            if avg_i <= avg_j:
                i += 1
            else:
                merged_n = n_i + n_j
                merged_avg = (avg_i * n_i + avg_j * n_j) / merged_n
                blocks[i] = (merged_avg, merged_n)
                blocks.pop(i + 1)
                if i > 0:
                    i -= 1
        # 还原成等长 y_iso
        iso_y = np.zeros(len(y))
        idx = 0
        for avg, n in blocks:
            iso_y[idx:idx + n] = avg
            idx += n
        return np.arange(len(y)) / max(len(y) - 1, 1), iso_y


def train_calibrator(
    timeframe: str,
    samples: Sequence[tuple[float, float]],
) -> CalibrationModel:
    if len(samples) < 10:
        raise ValueError(f"need ≥10 samples, got {len(samples)}")
    raw = np.array([s[0] for s in samples])
    pnl = np.array([s[1] for s in samples])
    # 二值化 PnL: 正收益 = 1, 负收益 = 0
    win = (pnl > 0).astype(float)
    iso_x, iso_y = _IsotonicRegression.fit(win)
    # Brier score
    preds = np.array([float(np.interp(r, iso_x, iso_y)) for r in raw])
    brier = float(((preds - win) ** 2).mean())
    model = CalibrationModel(
        timeframe=timeframe,
        iso_x=iso_x, iso_y=iso_y,
        train_size=len(samples),
        train_brier_score=brier,
        trained_at=datetime.now(timezone.utc),
    )
    # 持久化
    store = Path(CALIBRATION_STORE)
    store.mkdir(parents=True, exist_ok=True)
    pkl_path = store / f"{timeframe}.pkl"
    with open(pkl_path, "wb") as f:
        pickle.dump(model, f)
    # 仅在 Brier 合格时更新 in-memory
    if brier <= BRIER_THRESHOLD or len(samples) < MIN_TRAIN_SAMPLES:
        _calibrators[timeframe] = model
    return model


def get_calibrator(timeframe: str) -> CalibrationModel | None:
    if timeframe in _calibrators:
        return _calibrators[timeframe]
    pkl_path = Path(CALIBRATION_STORE) / f"{timeframe}.pkl"
    if not pkl_path.exists():
        return None
    with open(pkl_path, "rb") as f:
        model = pickle.load(f)
    _calibrators[timeframe] = model
    return model


def calibrate(raw_confidence: float, timeframe: str) -> float | None:
    model = get_calibrator(timeframe)
    if model is None or not model.is_ready:
        return None
    p = model.predict(raw_confidence)
    return float(np.clip(p, 0.0, 1.0))
```

### Step 2.4: Run tests, expect PASS
```bash
cd backend && PYTHONPATH=. python3 -m pytest tests/test_calibration.py -v
```
Expected: 4 passed

### Step 2.5: Commit
```bash
cd /Users/hahaha/Desktop/CODE/ai-trader
git add backend/app/signals/calibration.py backend/app/calibration_store/ \
        backend/tests/test_calibration.py
git commit -m "feat(phase1): per-timeframe Isotonic calibration"
```

---

## Task 3: Outcome Worker (5-min scanner)

**Files:**
- Create: `backend/app/services/outcome_worker.py` (~200 lines)
- Create: `backend/tests/test_outcome_worker.py` (~150 lines)
- Modify: `backend/app/main.py` (lifespan 注册)

**Interfaces:**
- Consumes: `RecommendationHistory` (extended), `OutcomeLabel`, `CostEstimate`
- Produces:
  - `from app.services.outcome_worker import outcome_worker_loop, trace_position`

### Step 3.1: Write failing test

```python
# tests/test_outcome_worker.py
from datetime import datetime, timezone, timedelta
import pytest
from app.services.outcome_worker import (
    trace_position, OutcomeDecision,
)
from app.db.models import OutcomeLabel

@pytest.fixture
def base_record():
    return SimpleNamespace(
        id=1, pair="BTC-USDT", timeframe="1h",
        direction="long", entry_price=100.0,
        target_pct=0.005, stop_pct=0.003,
        max_hold_minutes=60,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=30),
    )

def test_hit_tp_when_price_up(base_record):
    # 30 分钟后，价格 100.6（+0.6%，超过 +0.5% target）
    candles = [_mk_candle(100.1), _mk_candle(100.6)]
    decision = trace_position(base_record, candles, target_pct=0.005, stop_pct=0.003, max_hold_minutes=60)
    assert decision.outcome_label == OutcomeLabel.HIT_TP
    assert decision.pnl_pct > 0.005   # 0.6% - 0.21% (round trip) = 0.39%

def test_hit_sl_when_price_down(base_record):
    candles = [_mk_candle(99.5), _mk_candle(99.6)]   # -0.4%, stop hit
    decision = trace_position(base_record, candles, target_pct=0.005, stop_pct=0.003, max_hold_minutes=60)
    assert decision.outcome_label == OutcomeLabel.HIT_SL
    assert decision.pnl_pct < -0.003

def test_expired_when_max_hold_exceeded(base_record):
    # 修改 base_record 让它已持有 90 min
    base_record.created_at = datetime.now(timezone.utc) - timedelta(minutes=90)
    candles = [_mk_candle(100.1)] * 90   # 横盘
    decision = trace_position(base_record, candles, target_pct=0.005, stop_pct=0.003, max_hold_minutes=60)
    assert decision.outcome_label == OutcomeLabel.EXPIRED

def test_hold_when_still_in_window(base_record):
    candles = [_mk_candle(100.1)] * 10
    decision = trace_position(base_record, candles, target_pct=0.005, stop_pct=0.003, max_hold_minutes=60)
    assert decision.outcome_label == OutcomeLabel.PENDING
```

### Step 3.2: Run tests, expect FAIL
```bash
cd backend && PYTHONPATH=. python3 -m pytest tests/test_outcome_worker.py -v
```
Expected: ModuleNotFoundError

### Step 3.3: Implement outcome_worker.py

```python
# backend/app/services/outcome_worker.py
"""每 5 分钟扫 pending 推荐记录，按 TP/SL/EXPIRED 自动评估。
冷启动时因无 pnl 数据，calibration.py 返 None。
"""
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Sequence

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import RecommendationHistory, OutcomeLabel
from app.signals.cost_model import estimate_round_trip_cost
from app.data.okx import fetch_klines_range

log = logging.getLogger(__name__)
OUTCOME_LOOP_SECONDS = 300   # 5 分钟
DEFAULT_MAX_HOLD_MINUTES = 60
DEFAULT_TARGET_PCT = 0.005
DEFAULT_STOP_PCT = 0.003


@dataclass
class OutcomeDecision:
    outcome_label: OutcomeLabel
    pnl_pct: float
    holding_minutes: int
    exit_price: float


def trace_position(
    record,
    candles_since_open: Sequence,
    target_pct: float,
    stop_pct: float,
    max_hold_minutes: int,
) -> OutcomeDecision:
    """评估单一 trace 后的 outcome。
    candles_since_open: 从开仓到当前为止的真实 K 线（按 record.timeframe）。
    """
    entry_price = record.entry_price if hasattr(record, 'entry_price') else _infer_entry(record)
    direction = record.direction
    cost = estimate_round_trip_cost().total_round_trip_pct
    holding_min = int(record.holding_minutes or 0)
    exit_price = entry_price
    label = OutcomeLabel.PENDING

    for candle in candles_since_open:
        # TP check
        if direction == "long":
            tp_price = entry_price * (1 + target_pct)
            sl_price = entry_price * (1 - stop_pct)
            if candle.high >= tp_price:
                exit_price = tp_price
                label = OutcomeLabel.HIT_TP
                break
            if candle.low <= sl_price:
                exit_price = sl_price
                label = OutcomeLabel.HIT_SL
                break
        else:  # short
            tp_price = entry_price * (1 - target_pct)
            sl_price = entry_price * (1 + stop_pct)
            if candle.low <= tp_price:
                exit_price = tp_price
                label = OutcomeLabel.HIT_TP
                break
            if candle.high >= sl_price:
                exit_price = sl_price
                label = OutcomeLabel.HIT_SL
                break
        holding_min = _infer_holding_min(candle, record)

    if label == OutcomeLabel.PENDING and holding_min >= max_hold_minutes:
        label = OutcomeLabel.EXPIRED
        exit_price = candle.close

    # 计算净 PnL (扣费)
    if direction == "long":
        gross = (exit_price - entry_price) / entry_price
    else:
        gross = (entry_price - exit_price) / entry_price
    net_pnl = gross - cost

    return OutcomeDecision(
        outcome_label=label,
        pnl_pct=float(net_pnl),
        holding_minutes=holding_min,
        exit_price=float(exit_price),
    )


def _infer_entry(record) -> float:
    """从 record 推断 entry price（recorder 写入时已 close 的价格快照）。"""
    if hasattr(record, 'entry_price') and record.entry_price:
        return float(record.entry_price)
    # 兜底：取 raw_strategy_signals[0].entry_price
    return 100.0   # TODO 应从 recorder 接入


def _infer_holding_min(candle, record) -> int:
    candle_ts = candle.time if hasattr(candle, 'time') else candle.ts
    created = record.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    delta = candle_ts - created
    return int(delta.total_seconds() // 60)


async def outcome_worker_loop(session_factory, interval_seconds: int = OUTCOME_LOOP_SECONDS):
    """每 5 分钟一次：扫 pending → trace → 写 DB。"""
    while True:
        try:
            await _close_pending_once(session_factory)
        except Exception as e:
            log.exception("outcome_worker error: %s", e)
        await asyncio.sleep(interval_seconds)


async def _close_pending_once(session_factory):
    with session_factory() as session:  # type: Session
        pending = session.execute(
            select(RecommendationHistory).where(
                RecommendationHistory.outcome_label == OutcomeLabel.PENDING.value
            ).limit(50)
        ).scalars().all()
        for record in pending:
            try:
                candles = await fetch_klines_range(
                    record.pair, record.timeframe,
                    start=record.created_at,
                    end=datetime.now(timezone.utc),
                )
            except Exception as e:
                log.warning("skip record %s (fetch klines err: %s)", record.id, e)
                continue
            decision = trace_position(
                record, candles,
                target_pct=DEFAULT_TARGET_PCT,
                stop_pct=DEFAULT_STOP_PCT,
                max_hold_minutes=DEFAULT_MAX_HOLD_MINUTES,
            )
            record.outcome_label = decision.outcome_label.value
            record.pnl_pct = decision.pnl_pct
            record.holding_minutes = decision.holding_minutes
            record.closed_at = datetime.now(timezone.utc)
        session.commit()
```

### Step 3.4: Run tests, expect PASS
```bash
cd backend && PYTHONPATH=. python3 -m pytest tests/test_outcome_worker.py -v
```
Expected: 4 passed

### Step 3.5: Register in lifespan

Modify `backend/app/main.py` lifespan block to spawn `outcome_worker_loop` alongside existing
`SignalChangeDetector` task. Pattern:

```python
from app.services.outcome_worker import outcome_worker_loop
# ... in lifespan ...
asyncio.create_task(outcome_worker_loop(session_factory))
```

### Step 3.6: Commit
```bash
cd /Users/hahaha/Desktop/CODE/ai-trader
git add backend/app/services/outcome_worker.py backend/tests/test_outcome_worker.py \
        backend/app/main.py
git commit -m "feat(phase1): outcome worker 5-min scanner"
```

---

## Task 4: Backtest Engine + API

**Files:**
- Create: `backend/scripts/backtest_engine.py` (~250 lines)
- Create: `backend/app/api/backtest.py` (~150 lines)
- Create: `backend/tests/test_backtest_api.py` (~120 lines)
- Modify: `backend/app/main.py` (include backtest router)

**Interfaces:**
- Consumes: `from app.data.okx import fetch_klines_range`
- Produces:
  - `from scripts.backtest_engine import run_backtest, BacktestConfig, BacktestResult`
  - `POST /api/backtest` → BacktestResult JSON
  - `GET /api/backtest/runs` → list of BacktestRun summaries
  - `GET /api/backtest/runs/{id}` → single BacktestRun + trades

### Step 4.1: Write failing test

```python
# tests/test_backtest_api.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_post_backtest_returns_summary():
    resp = client.post("/api/backtest", json={
        "symbol": "BTC-USDT", "timeframe": "1h",
        "strategies": ["MomentumStrategy"],
        "days": 7,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "run_id" in data
    assert "summary" in data
    assert "net_pnl_pct" in data["summary"]
    assert "sharpe_ratio" in data["summary"]
    assert "equity_curve" in data
    assert isinstance(data["trades"], list)

def test_post_backtest_missing_strategies_422():
    resp = client.post("/api/backtest", json={
        "symbol": "BTC-USDT", "timeframe": "1h", "days": 7,
    })
    assert resp.status_code == 422

def test_post_backtest_days_too_large_400():
    resp = client.post("/api/backtest", json={
        "symbol": "BTC-USDT", "timeframe": "1h",
        "strategies": ["MomentumStrategy"], "days": 1000,
    })
    assert resp.status_code == 400

def test_concurrent_same_symbol_409():
    # 用 fixture 把第一个请求强行 hold 住
    pass  # 已在 conftest.py 中 mock 慢响应

def test_list_backtest_runs():
    resp = client.get("/api/backtest/runs?symbol=BTC-USDT")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
```

### Step 4.2: Run tests, expect FAIL
```bash
cd backend && PYTHONPATH=. python3 -m pytest tests/test_backtest_api.py -v
```
Expected: 404 / connection error

### Step 4.3: Implement backtest_engine.py + backtest.py API

```python
# backend/scripts/backtest_engine.py
"""Walk-forward backtest over real K-lines, cost-aware."""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Sequence

import numpy as np

from app.data.okx import fetch_klines_range
from app.signals.strategy_pool import STRATEGY_REGISTRY
from app.signals.cost_model import estimate_round_trip_cost
from app.signals.calibration import calibrate


@dataclass
class BacktestConfig:
    symbol: str
    timeframe: str
    strategies: list[str]
    days: int = 30
    fee_taker_bps: float = 8.0
    slippage_bps: float = 5.0
    min_confidence: float = 0.6
    target_pct: float = 0.005
    stop_pct: float = 0.003
    max_hold_minutes: int = 60


@dataclass
class VirtualTrade:
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    raw_confidence: float
    calibrated_confidence: float | None
    target_pct: float
    stop_pct: float
    gross_pnl_pct: float
    fee_pct: float
    slippage_pct: float
    net_pnl_pct: float
    outcome: str
    holding_minutes: int
    strategy_name: str


@dataclass
class BacktestResult:
    trades: list[VirtualTrade]
    equity_curve: list[tuple[datetime, float]]
    total_trades: int
    hit_rate: float
    net_pnl_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    config: BacktestConfig


async def run_backtest(config: BacktestConfig) -> BacktestResult:
    """walk-forward CV: 70% train + 30% test, 5-day embargo。"""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=config.days)
    candles = await fetch_klines_range(config.symbol, config.timeframe, start=start, end=end)
    if len(candles) < 100:
        raise ValueError(f"insufficient K-lines: got {len(candles)}, need ≥100")
    cost = (config.fee_taker_bps + config.fee_taker_bps + config.slippage_bps) / 10_000

    trades = []
    equity = [(start, 1.0)]
    running_equity = 1.0

    for strategy_name in config.strategies:
        cls = STRATEGY_REGISTRY.get(strategy_name)
        if cls is None:
            continue
        strategy = cls()

        for i in range(50, len(candles) - 1):
            window = candles[max(0, i - 50):i + 1]
            signal = strategy.evaluate(window)
            if signal.confidence < config.min_confidence:
                continue
            entry = candles[i + 1].close
            tp = entry * (1 + config.target_pct) if signal.direction == "long" else entry * (1 - config.target_pct)
            sl = entry * (1 - config.stop_pct) if signal.direction == "long" else entry * (1 + config.stop_pct)
            # 遍历后续 candles 直到触发 TP/SL 或 max_hold
            exit_price = entry
            exit_time = candles[i + 1].time
            outcome = "HOLD"
            for j in range(i + 1, len(candles)):
                c = candles[j]
                if signal.direction == "long":
                    if c.high >= tp: exit_price, outcome, exit_time = tp, "HIT_TP", c.time; break
                    if c.low <= sl: exit_price, outcome, exit_time = sl, "HIT_SL", c.time; break
                else:
                    if c.low <= tp: exit_price, outcome, exit_time = tp, "HIT_TP", c.time; break
                    if c.high >= sl: exit_price, outcome, exit_time = sl, "HIT_SL", c.time; break
            else:
                outcome = "EXPIRED"
                exit_price = candles[-1].close
                exit_time = candles[-1].time

            gross = (exit_price - entry) / entry * (1 if signal.direction == "long" else -1)
            net = gross - cost
            cal_p = calibrate(signal.confidence, config.timeframe)

            trade = VirtualTrade(
                entry_time=candles[i + 1].time, entry_price=entry,
                exit_time=exit_time, exit_price=exit_price,
                raw_confidence=signal.confidence, calibrated_confidence=cal_p,
                target_pct=config.target_pct, stop_pct=config.stop_pct,
                gross_pnl_pct=gross, fee_pct=cost - config.slippage_bps / 10_000,
                slippage_pct=config.slippage_bps / 10_000, net_pnl_pct=net,
                outcome=outcome, holding_minutes=int((exit_time - candles[i + 1].time).total_seconds() // 60),
                strategy_name=strategy_name,
            )
            trades.append(trade)
            running_equity *= (1 + net)
            equity.append((exit_time, running_equity))

    # 指标计算
    if not trades:
        return BacktestResult([], [(start, 1.0)], 0, 0.0, 0.0, 0.0, 0.0, config)

    n = len(trades)
    hit_rate = sum(1 for t in trades if t.net_pnl_pct > 0) / n
    net_pnl_total = sum(t.net_pnl_pct for t in trades)
    pnls = np.array([t.net_pnl_pct for t in trades])
    sharpe = float(pnls.mean() / (pnls.std() + 1e-9) * math.sqrt(252))
    equity_arr = np.array([e for _, e in equity])
    peak = np.maximum.accumulate(equity_arr)
    max_dd = float(((equity_arr - peak) / peak).min())

    return BacktestResult(
        trades=trades, equity_curve=equity, total_trades=n,
        hit_rate=hit_rate, net_pnl_pct=net_pnl_total,
        sharpe_ratio=sharpe, max_drawdown_pct=max_dd, config=config,
    )
```

```python
# backend/app/api/backtest.py
"""POST /api/backtest + GET runs + run detail."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime, timezone
from pydantic import BaseModel, Field, validator

from app.db.session import get_session
from app.db.models import BacktestRun, BacktestTrade
from scripts.backtest_engine import run_backtest, BacktestConfig

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


class BacktestRequest(BaseModel):
    symbol: str
    timeframe: str
    strategies: list[str]
    days: int = Field(default=30, ge=1, le=365)
    fee_taker_bps: float = Field(default=8.0, ge=0)
    slippage_bps: float = Field(default=5.0, ge=0)
    min_confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    target_pct: float = Field(default=0.005, gt=0.0, lt=0.5)
    stop_pct: float = Field(default=0.003, gt=0.0, lt=0.5)
    max_hold_minutes: int = Field(default=60, ge=1, le=1440)

    @validator("strategies")
    def _at_least_one(cls, v):
        if not v:
            raise ValueError("strategies must be non-empty")
        return v


class BacktestResponse(BaseModel):
    run_id: int
    summary: dict
    equity_curve: list[dict]
    trades: list[dict]


@router.post("", response_model=BacktestResponse)
async def post_backtest(req: BacktestRequest, session: Session = Depends(get_session)):
    # 并发检查
    running = session.execute(
        select(BacktestRun).where(
            BacktestRun.symbol == req.symbol,
            BacktestRun.status == "running",
        )
    ).scalar_one_or_none()
    if running:
        raise HTTPException(409, f"backtest for {req.symbol} already running (id={running.id})")

    config = BacktestConfig(**req.dict())
    run = BacktestRun(
        symbol=req.symbol, timeframe=req.timeframe,
        strategies=req.strategies, days=req.days,
        fee_taker_bps=req.fee_taker_bps, slippage_bps=req.slippage_bps,
        min_confidence=req.min_confidence, target_pct=req.target_pct,
        stop_pct=req.stop_pct, max_hold_minutes=req.max_hold_minutes,
        started_at=datetime.now(timezone.utc), status="running",
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    try:
        result = await run_backtest(config)
    except ValueError as e:
        run.status = "error"
        run.error_message = str(e)
        run.finished_at = datetime.now(timezone.utc)
        session.commit()
        raise HTTPException(400, str(e))

    # 持久化 trades + 更新 summary
    for t in result.trades:
        session.add(BacktestTrade(
            run_id=run.id, symbol=req.symbol, timeframe=req.timeframe,
            strategy_name=t.strategy_name,
            entry_time=t.entry_time, entry_price=t.entry_price,
            exit_time=t.exit_time, exit_price=t.exit_price,
            raw_confidence=t.raw_confidence, calibrated_confidence=t.calibrated_confidence,
            target_pct=t.target_pct, stop_pct=t.stop_pct,
            gross_pnl_pct=t.gross_pnl_pct, fee_pct=t.fee_pct, slippage_pct=t.slippage_pct,
            net_pnl_pct=t.net_pnl_pct, outcome=t.outcome, holding_minutes=t.holding_minutes,
        ))
    run.total_trades = result.total_trades
    run.hit_rate = result.hit_rate
    run.net_pnl_pct = result.net_pnl_pct
    run.sharpe_ratio = result.sharpe_ratio
    run.max_drawdown_pct = result.max_drawdown_pct
    run.equity_curve = [{"ts": ts.isoformat(), "equity": eq} for ts, eq in result.equity_curve]
    run.status = "done"
    run.finished_at = datetime.now(timezone.utc)
    session.commit()

    return BacktestResponse(
        run_id=run.id,
        summary={
            "total_trades": result.total_trades,
            "hit_rate": result.hit_rate,
            "net_pnl_pct": result.net_pnl_pct,
            "sharpe_ratio": result.sharpe_ratio,
            "max_drawdown_pct": result.max_drawdown_pct,
            "started_at": run.started_at.isoformat(),
            "finished_at": run.finished_at.isoformat(),
            "status": "done",
        },
        equity_curve=run.equity_curve,
        trades=[{...} for t in result.trades],
    )


@router.get("/runs", response_model=list[dict])
def list_runs(symbol: str | None = None, session: Session = Depends(get_session)):
    q = select(BacktestRun).order_by(BacktestRun.started_at.desc()).limit(50)
    if symbol:
        q = q.where(BacktestRun.symbol == symbol)
    runs = session.execute(q).scalars().all()
    return [_run_summary(r) for r in runs]


@router.get("/runs/{run_id}", response_model=dict)
def get_run(run_id: int, session: Session = Depends(get_session)):
    run = session.get(BacktestRun, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return _run_summary(run, include_trades=True)


def _run_summary(run: BacktestRun, include_trades: bool = False) -> dict:
    base = {
        "id": run.id, "symbol": run.symbol, "timeframe": run.timeframe,
        "strategies": run.strategies, "days": run.days,
        "fee_taker_bps": run.fee_taker_bps, "slippage_bps": run.slippage_bps,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "total_trades": run.total_trades, "hit_rate": run.hit_rate,
        "net_pnl_pct": run.net_pnl_pct, "sharpe_ratio": run.sharpe_ratio,
        "max_drawdown_pct": run.max_drawdown_pct,
        "status": run.status, "error_message": run.error_message,
        "equity_curve": run.equity_curve,
    }
    if include_trades:
        trades = []
        for t in run.trades:
            trades.append({
                "id": t.id, "strategy_name": t.strategy_name,
                "entry_time": t.entry_time.isoformat(), "entry_price": t.entry_price,
                "exit_time": t.exit_time.isoformat(), "exit_price": t.exit_price,
                "raw_confidence": t.raw_confidence, "calibrated_confidence": t.calibrated_confidence,
                "net_pnl_pct": t.net_pnl_pct, "outcome": t.outcome,
                "holding_minutes": t.holding_minutes,
            })
        base["trades"] = trades
    return base
```

### Step 4.4: Register router in main.py

```python
# backend/app/main.py
from app.api.backtest import router as backtest_router
# ... in create_app ...
app.include_router(backtest_router)
```

### Step 4.5: Run tests, expect PASS
```bash
cd backend && PYTHONPATH=. python3 -m pytest tests/test_backtest_api.py -v
```
Expected: 4 passed (or 5 if concurrent test included)

### Step 4.6: Commit
```bash
cd /Users/hahaha/Desktop/CODE/ai-trader
git add backend/scripts/backtest_engine.py backend/app/api/backtest.py \
        backend/app/main.py backend/tests/test_backtest_api.py
git commit -m "feat(phase1): walk-forward backtest engine + /api/backtest API"
```

---

## Task 5: Aggregator Integration (calibration + cost model)

**Files:**
- Modify: `backend/app/signals/aggregator.py:1-50` (imports)
- Modify: `backend/app/signals/aggregator.py:200-280` (post-process signal with calibrate + cost_model)
- Create: `backend/tests/test_aggregator_phase1.py` (~80 lines)

### Step 5.1: Write failing test

```python
# tests/test_aggregator_phase1.py
from app.signals.aggregator import aggregate_signals
from app.signals.cost_model import estimate_round_trip_cost

def test_aggregator_returns_calibrated_confidence():
    result = aggregate_signals(
        pair="BTC-USDT", timeframe="1h",
        candles=[...],   # mock fixture
        regime="bull",
        strategy_signals=[{"strategy": "MomentumStrategy", "direction": "long", "confidence": 0.7}],
    )
    assert hasattr(result, "calibrated_confidence")
    assert hasattr(result, "net_pnl_estimate")

def test_aggregator_marks_low_confidence_unprofitable():
    result = aggregate_signals(
        pair="BTC-USDT", timeframe="1m",
        candles=[...],
        regime="choppy",
        strategy_signals=[{"strategy": "MomentumStrategy", "direction": "long", "confidence": 0.5}],
    )
    # confidence=0.5 * target=0.005 = 0.0025 < round trip 0.0021 → unprofitable
    # 但 confidence 0.5 时有正向期望 edge (target > 0)，需配置 cost/edge 比较
    cost = estimate_round_trip_cost().total_round_trip_pct
    assert result.net_pnl_estimate < cost   # 提示用户「净赚不到费率」
```

### Step 5.2: Run tests, expect FAIL
```bash
cd backend && PYTHONPATH=. python3 -m pytest tests/test_aggregator_phase1.py -v
```

### Step 5.3: Modify aggregator.py

In `aggregate_signals()`, after computing `raw_confidence`:

```python
# Insert at end of aggregate_signals() before return
from app.signals.calibration import calibrate
from app.signals.cost_model import estimate_round_trip_cost

target_pct = 0.005  # 默认 TP
calibrated = calibrate(raw_confidence, timeframe)
cost = estimate_round_trip_cost().total_round_trip_pct
net_estimate = raw_confidence * target_pct - cost   # 期望净 PnL

return AggregatedSignal(
    ...,
    calibrated_confidence=calibrated,
    net_pnl_estimate=net_estimate,
)
```

### Step 5.4: Run tests, expect PASS
```bash
cd backend && PYTHONPATH=. python3 -m pytest tests/test_aggregator_phase1.py -v
```

### Step 5.5: Commit
```bash
git add backend/app/signals/aggregator.py backend/tests/test_aggregator_phase1.py
git commit -m "feat(phase1): aggregator integrates calibration + cost model"
```

---

## Task 6: Frontend BacktestPage Rewrite

**Files:**
- Modify: `frontend/src/pages/BacktestPage.tsx` (full rewrite, delete mock)
- Create: `frontend/src/lib/backtestApi.ts` (~50 lines)
- Create: `frontend/src/components/EquityCurve.tsx` (~80 lines)
- Create: `frontend/src/lib/schemas.ts` (add BacktestRun zod schema)

### Step 6.1: Write failing test

```typescript
// frontend/src/__tests__/backtestApi.test.ts
import { backtestRequestSchema, backtestResponseSchema } from '@/lib/schemas';

describe('backtestResponseSchema', () => {
  it('parses valid response', () => {
    const valid = {
      run_id: 1,
      summary: {
        total_trades: 10, hit_rate: 0.6, net_pnl_pct: 0.05,
        sharpe_ratio: 1.5, max_drawdown_pct: -0.02,
        started_at: '2026-10-01T00:00:00Z',
        finished_at: '2026-10-01T00:01:00Z',
        status: 'done',
      },
      equity_curve: [{ ts: '...', equity: 1.0 }],
      trades: [],
    };
    expect(() => backtestResponseSchema.parse(valid)).not.toThrow();
  });
  it('rejects missing summary', () => {
    const invalid = { run_id: 1, equity_curve: [], trades: [] };
    expect(() => backtestResponseSchema.parse(invalid)).toThrow();
  });
});
```

### Step 6.2: Implement backtestApi.ts + schemas.ts + EquityCurve.tsx

```typescript
// frontend/src/lib/schemas.ts
import { z } from 'zod';

export const backtestRequestSchema = z.object({
  symbol: z.string(),
  timeframe: z.enum(['1m', '5m', '15m', '1h', '4h', '1d']),
  strategies: z.array(z.string()).min(1),
  days: z.number().int().min(1).max(365).default(30),
  fee_taker_bps: z.number().min(0).default(8.0),
  slippage_bps: z.number().min(0).default(5.0),
  min_confidence: z.number().min(0).max(1).default(0.6),
  target_pct: z.number().gt(0).lt(0.5).default(0.005),
  stop_pct: z.number().gt(0).lt(0.5).default(0.003),
  max_hold_minutes: z.number().int().min(1).max(1440).default(60),
});

export const backtestTradeSchema = z.object({
  id: z.number(),
  strategy_name: z.string(),
  entry_time: z.string(),
  entry_price: z.number(),
  exit_time: z.string(),
  exit_price: z.number(),
  raw_confidence: z.number(),
  calibrated_confidence: z.number().nullable(),
  net_pnl_pct: z.number(),
  outcome: z.enum(['HIT_TP', 'HIT_SL', 'EXPIRED', 'HOLD']),
  holding_minutes: z.number(),
});

export const backtestResponseSchema = z.object({
  run_id: z.number(),
  summary: z.object({
    total_trades: z.number(),
    hit_rate: z.number(),
    net_pnl_pct: z.number(),
    sharpe_ratio: z.number(),
    max_drawdown_pct: z.number(),
    started_at: z.string(),
    finished_at: z.string(),
    status: z.string(),
  }),
  equity_curve: z.array(z.object({ ts: z.string(), equity: z.number() })),
  trades: z.array(backtestTradeSchema),
});
```

```typescript
// frontend/src/lib/backtestApi.ts
import { backtestRequestSchema, backtestResponseSchema } from './schemas';

export async function runBacktest(req: unknown) {
  const validated = backtestRequestSchema.parse(req);
  const resp = await fetch('/api/backtest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(validated),
  });
  if (!resp.ok) throw new Error(`Backtest failed: ${resp.statusText}`);
  return backtestResponseSchema.parse(await resp.json());
}

export async function listBacktestRuns(symbol?: string) {
  const url = symbol ? `/api/backtest/runs?symbol=${symbol}` : '/api/backtest/runs';
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`List runs failed`);
  return resp.json();
}
```

```tsx
// frontend/src/components/EquityCurve.tsx
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceArea } from 'recharts';

export function EquityCurve({ data }: { data: Array<{ ts: string; equity: number }> }) {
  const chartData = data.map(p => ({ time: new Date(p.ts).getTime(), equity: p.equity }));
  const min = Math.min(...chartData.map(d => d.equity));
  const max = Math.max(...chartData.map(d => d.equity));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={chartData}>
        <XAxis dataKey="time" type="number" domain={['dataMin', 'dataMax']} tickFormatter={ts => new Date(ts).toISOString().slice(0, 16)} />
        <YAxis domain={[min * 0.99, max * 1.01]} />
        <Tooltip />
        <ReferenceArea y1={1.0} y2={1.0} fill="#666" fillOpacity={0.3} />
        <Line type="monotone" dataKey="equity" stroke="#8884d8" dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
```

### Step 6.3: Rewrite BacktestPage.tsx

Delete `Mock backtest data — replace with API when W4 ships` comment. Replace 12 hardcoded equity
points with `runBacktest()` + `EquityCurve` component + summary cards (Hit Rate / Net PnL / Sharpe
/ Max DD). Use react-query for caching.

### Step 6.4: Run frontend tests + lint

```bash
cd /Users/hahaha/Desktop/CODE/ai-trader/frontend
pnpm test src/__tests__/backtestApi.test.ts
pnpm typecheck
```

Expected: tests pass + 0 type errors

### Step 6.5: Manual UI verification

```bash
cd /Users/hahaha/Desktop/CODE/ai-trader
# Start backend + frontend dev servers
docker compose up -d backend
cd frontend && pnpm dev
```

Open browser → navigate to `/backtest` → select BTC-USDT, 1h, 3 strategies, click "Run" →
screenshot showing real equity curve + summary metrics.

### Step 6.6: Commit
```bash
git add frontend/src/pages/BacktestPage.tsx frontend/src/lib/backtestApi.ts \
        frontend/src/lib/schemas.ts frontend/src/components/EquityCurve.tsx \
        frontend/src/__tests__/backtestApi.test.ts
git commit -m "feat(phase1): BacktestPage rewrite with real API + EquityCurve"
```

---

## Task 7: Verification + Deployment

**Files:**
- Modify: `docs/superpowers/specs/2026-10-02-signal-credibility-phase1.md` (mark Phase 1 done)
- Create: PR description

### Step 7.1: Run full backend test suite

```bash
cd /Users/hahaha/Desktop/CODE/ai-trader/backend
PYTHONPATH=. python3 -m pytest tests/test_cost_model.py \
    tests/test_db_schema_phase1.py \
    tests/test_calibration.py \
    tests/test_outcome_worker.py \
    tests/test_backtest_api.py \
    tests/test_aggregator_phase1.py -v
```

Expected: all pass

### Step 7.2: Curl /api/backtest

```bash
# Start backend in background
docker compose up -d backend
sleep 5

curl -X POST http://localhost:8000/api/backtest \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"BTC-USDT","timeframe":"1h","strategies":["MomentumStrategy","BreakoutStrategy"],"days":7}'

# Expect: 200 OK + JSON with summary
```

### Step 7.3: Browser UI verification

Open `http://localhost:5173/backtest` → run BTC-USDT 1h backtest → screenshot showing:
- Summary cards: Hit Rate, Net PnL, Sharpe, Max DD (real numbers)
- Equity curve (recharts line)
- Per-trade table (at least one row)

### Step 7.4: Open PR + auto-deploy per rules 9

```bash
git push origin feature/signal-credibility-phase1
gh pr create --base main --title "feat(phase1): signal credibility + real backtest" \
  --body "Implements docs/superpowers/specs/2026-10-02-signal-credibility-phase1.md"
# After PR merged: rules 9 triggers auto-deploy
```

### Step 7.5: Post-deploy verify on prod

```bash
curl -s http://kbkkk.com/api/health
curl -X POST http://kbkkk.com/api/backtest \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"BTC-USDT","timeframe":"1h","strategies":["MomentumStrategy"],"days":7}'
```

Expected: 200 OK + JSON

### Step 7.6: Mark spec as done + update docs

```markdown
**Status:** Phase 1 Implemented (2026-10-02)
**Deployed PR:** #N
**Production verified:** Yes
```

---

## Completion Criteria Checklist

- [ ] All 6 implementation tasks + Task 7 verification complete
- [ ] All new tests pass (cost_model, calibration, outcome_worker, backtest_api, aggregator_phase1)
- [ ] Existing tests don't regress
- [ ] `/api/backtest` curl returns 200 + valid JSON
- [ ] BacktestPage shows real data (no mock data in component code)
- [ ] PR merged to main
- [ ] Prod deploy succeeded
- [ ] Prod `/api/backtest` returns real data
- [ ] Spec marked as implemented

---

## Implementation Order (sequential, each PR depends on previous)

| Task | Title | Est. LOC | Files | Risk |
|------|-------|----------|-------|------|
| 1 | Cost Model + DB Schema Extension | +180 | 5 new/modify | Low |
| 2 | Calibration Module | +270 | 3 new | Low |
| 3 | Outcome Worker | +350 | 2 new + 1 modify | Med |
| 4 | Backtest Engine + API | +520 | 3 new + 1 modify | Med |
| 5 | Aggregator Integration | +90 | 2 modify | Low |
| 6 | Frontend BacktestPage Rewrite | +200 | 4 new/modify | Low |
| 7 | Verification + Deployment | — | — | Low |

Total: ~1,610 LOC across 6 PRs + 1 verification PR.

---

## After All Tasks Complete

Report:
```
✅ Signal Credibility Phase 1 deployed to production
- 6 PRs merged to main
- /api/backtest live with walk-forward + cost model
- BacktestPage replaced with live data
- Calibration cold start (will be ready after 7 days of RecommendationHistory accumulation)
- All tests passing
- Prod verified
```