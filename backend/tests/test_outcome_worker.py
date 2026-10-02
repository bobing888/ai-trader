"""Test outcome_worker — trace_position 单一 record 的出场评估。

验证：
1. HIT_TP：价格触达 +0.5% → pnl_pct = gross - 费率
2. HIT_SL：价格触达 -0.3% → pnl_pct 接近 -0.5%
3. EXPIRED：超 max_hold → 强制出场
4. PENDING：未触发条件仍在窗口内
5. SHORT 方向反向检查
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import pytest

from app.services.outcome_worker import trace_position
from app.db.models import OutcomeLabel


@dataclass
class FakeRecord:
    """模拟 RecommendationHistory 字段。"""
    id: int
    pair: str
    timeframe: str
    direction: str
    entry_price: float
    target_pct: float = 0.005
    stop_pct: float = 0.003
    max_hold_minutes: int = 60
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    holding_minutes: int = 0


@dataclass
class FakeCandle:
    time: datetime
    high: float
    low: float
    close: float


def _mk_candle(price: float, base_time: datetime | None = None, minutes_offset: int = 0,
               spread: float = 0.01) -> FakeCandle:
    base = base_time or datetime.now(timezone.utc)
    return FakeCandle(
        time=base + timedelta(minutes=minutes_offset),
        high=price + spread,
        low=price - spread,
        close=price,
    )


@pytest.fixture
def base_record():
    return FakeRecord(
        id=1, pair="BTC-USDT", timeframe="1h",
        direction="long", entry_price=100.0,
    )


def test_hit_tp_when_price_up(base_record):
    """30 分钟后，价格 100.6（+0.6%，超过 +0.5% target）→ HIT_TP。"""
    base = base_record.created_at
    candles = [
        _mk_candle(100.1, base, 1),
        _mk_candle(100.6, base, 30),   # close 100.6
    ]
    decision = trace_position(
        base_record, candles,
        target_pct=0.005, stop_pct=0.003, max_hold_minutes=60,
    )
    assert decision.outcome_label == OutcomeLabel.HIT_TP
    # gross = +0.5% (tp hit at 100.5) - 0.21% (round trip) = +0.29%
    assert decision.pnl_pct > 0.002
    assert decision.pnl_pct < 0.004


def test_hit_sl_when_price_down(base_record):
    """价格跌破 stop_loss → HIT_SL。"""
    base = base_record.created_at
    candles = [
        _mk_candle(99.5, base, 1),    # 99.5 = -0.5%, below SL = -0.3%
        _mk_candle(99.6, base, 2),
    ]
    decision = trace_position(
        base_record, candles,
        target_pct=0.005, stop_pct=0.003, max_hold_minutes=60,
    )
    assert decision.outcome_label == OutcomeLabel.HIT_SL
    # SL hit at 99.7 (entry * (1 - 0.003)), gross = -0.3%, net = -0.51%
    assert decision.pnl_pct < -0.004
    assert decision.pnl_pct > -0.006


def test_expired_when_max_hold_exceeded(base_record):
    """max_hold_minutes=60, 蜡烛横盘超过 60min → EXPIRED。"""
    base = base_record.created_at
    # 90 分钟的横盘
    candles = [_mk_candle(100.0, base, i) for i in range(1, 91)]
    decision = trace_position(
        base_record, candles,
        target_pct=0.005, stop_pct=0.003, max_hold_minutes=60,
    )
    assert decision.outcome_label == OutcomeLabel.EXPIRED


def test_pending_when_within_window(base_record):
    """10 分钟横盘，未触发 TP/SL → PENDING。"""
    base = base_record.created_at
    candles = [_mk_candle(100.1, base, i) for i in range(1, 11)]
    decision = trace_position(
        base_record, candles,
        target_pct=0.005, stop_pct=0.003, max_hold_minutes=60,
    )
    assert decision.outcome_label == OutcomeLabel.PENDING


def test_short_direction_hit_tp(base_record):
    """short 方向，tp = entry * (1 - target_pct)。"""
    base_record.direction = "short"
    base = base_record.created_at
    # 跌到 99.4 (-0.6%, 触发 short tp +0.5%)
    candles = [_mk_candle(99.6, base, 1), _mk_candle(99.4, base, 30)]
    decision = trace_position(
        base_record, candles,
        target_pct=0.005, stop_pct=0.003, max_hold_minutes=60,
    )
    assert decision.outcome_label == OutcomeLabel.HIT_TP
    # gross = +0.5% (tp hit) - 0.21% = +0.29%
    assert decision.pnl_pct > 0.002


def test_short_direction_hit_sl(base_record):
    """short 方向，价格上涨超 stop → HIT_SL。"""
    base_record.direction = "short"
    base = base_record.created_at
    candles = [_mk_candle(100.6, base, 1)]   # +2%，远超 short SL +0.3%
    decision = trace_position(
        base_record, candles,
        target_pct=0.005, stop_pct=0.003, max_hold_minutes=60,
    )
    assert decision.outcome_label == OutcomeLabel.HIT_SL
    assert decision.pnl_pct < -0.003


def test_decision_returns_holding_minutes(base_record):
    """decision.holding_minutes 应为触发 candle 与 entry 的差。"""
    base = base_record.created_at
    candles = [_mk_candle(100.6, base, 30)]
    decision = trace_position(
        base_record, candles,
        target_pct=0.005, stop_pct=0.003, max_hold_minutes=60,
    )
    assert decision.outcome_label == OutcomeLabel.HIT_TP
    assert decision.holding_minutes == 30
    assert decision.exit_price == pytest.approx(100.5)  # tp price = 100 * 1.005