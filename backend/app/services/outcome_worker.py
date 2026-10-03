"""outcome_worker — 每 5 分钟扫 pending 推荐记录，按 TP/SL/EXPIRED 自动评估。

cold start 时 (n < 100) outcome_worker.py 暂时无 calibration 数据，
但 trace_position 本身不依赖 calibration — 它基于真实 OHLCV 评估出场。
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RecommendationHistory, OutcomeLabel
from app.signals.cost_model import estimate_round_trip_cost

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
    """评估单一 record 的出场。

    Args:
        record: 需含 entry_price / direction / created_at 属性
        candles_since_open: 开仓以来的真实 K 线（含 OHLC）
        target_pct: 止盈比例 (e.g. 0.005 = 0.5%)
        stop_pct: 止损比例 (e.g. 0.003 = 0.3%)
        max_hold_minutes: 最长持仓时间

    Returns:
        OutcomeDecision（label / net_pnl / holding_minutes / exit_price）
    """
    entry_price = float(record.entry_price)
    direction = record.direction
    cost = estimate_round_trip_cost().total_round_trip_pct

    # Initialize holding_min from first candle (or 0 if no candles)
    if candles_since_open:
        holding_min = _infer_holding_min(candles_since_open[0], record.created_at)
    else:
        holding_min = 0
    exit_price = entry_price
    label = OutcomeLabel.PENDING

    for candle in candles_since_open:
        # Update holding_minutes on every candle (last value wins)
        holding_min = _infer_holding_min(candle, record.created_at)
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

    if label == OutcomeLabel.PENDING and holding_min >= max_hold_minutes:
        label = OutcomeLabel.EXPIRED
        if candles_since_open:
            exit_price = float(candles_since_open[-1].close)

    # 计算 net PnL (扣费)
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


def _infer_holding_min(candle, created_at) -> int:
    """从 candle 时间减去 created_at 推算持仓分钟数。"""
    if candle is None:
        return 0
    c_time = getattr(candle, "time", None) or getattr(candle, "ts", None)
    if c_time is None:
        return 0
    if isinstance(c_time, (int, float)):
        c_dt = datetime.fromtimestamp(c_time, tz=timezone.utc)
    else:
        c_dt = c_time if c_time.tzinfo else c_time.replace(tzinfo=timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    delta = c_dt - created_at
    return max(0, int(delta.total_seconds() // 60))


# ── Background loop ─────────────────────────────────────────────────────────

async def outcome_worker_loop(
    session_factory,
    okx_client,
    interval_seconds: int = OUTCOME_LOOP_SECONDS,
    max_records_per_tick: int = 50,
):
    """每 5 分钟扫 pending → trace → 写 DB。

    Args:
        session_factory: callable 返回 SQLAlchemy Session
        okx_client: 需有 get_klines(symbol, interval, limit) async method
        interval_seconds: 间隔（默认 300 = 5 min）
        max_records_per_tick: 每次最多处理记录数（防 OOM）
    """
    while True:
        try:
            await _close_pending_once(session_factory, okx_client, max_records_per_tick)
        except Exception as e:
            log.exception("outcome_worker error: %s", e)
        await asyncio.sleep(interval_seconds)


async def _close_pending_once(session_factory, okx_client, max_records: int):
    with session_factory() as session:  # type: Session
        pending = session.execute(
            select(RecommendationHistory)
            .where(RecommendationHistory.outcome_label == OutcomeLabel.PENDING.value)
            .limit(max_records)
        ).scalars().all()

        for record in pending:
            entry_price = _get_entry_price(record)
            if entry_price is None:
                continue
            record.entry_price = entry_price  # cache for future use
            try:
                # 拉自 record.created_at 至今的 K 线 (limit 300 上限)
                candles_raw = await okx_client.get_klines(
                    record.pair, record.timeframe, limit=300,
                )
            except Exception as e:
                log.warning("outcome_worker: skip record %s (klines err: %s)", record.id, e)
                continue

            decision = trace_position(
                record, candles_raw,
                target_pct=DEFAULT_TARGET_PCT,
                stop_pct=DEFAULT_STOP_PCT,
                max_hold_minutes=DEFAULT_MAX_HOLD_MINUTES,
            )
            record.outcome_label = decision.outcome_label.value
            record.pnl_pct = decision.pnl_pct
            record.holding_minutes = decision.holding_minutes
            record.closed_at = datetime.now(timezone.utc)
        session.commit()


def _get_entry_price(record) -> float | None:
    """从 record 取 entry_price — fallback 到 recommendation signal close 时点的 close 价。"""
    if record.entry_price:
        return float(record.entry_price)
    # 用 created_at 时刻的 close 价格作为 fallback
    if record.reasons:
        # reasons 是 JSON 字符串（recorder 写入），从中抽 entry_hint
        try:
            import json
            parsed = json.loads(record.reasons)
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                if "entry_price" in parsed[0]:
                    return float(parsed[0]["entry_price"])
        except Exception:
            pass
    return None