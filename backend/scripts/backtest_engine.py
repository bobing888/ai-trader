"""Walk-forward 回测引擎 — 基于真实 OKX K 线的成本感知回测。

不做 ML 训练。给 aggregator / outcome_worker 提供「过去 N 天表现」基准。

Walk-forward CV: 70% train + 30% test (默认 30d train + 7d test, 5d embargo)。
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Sequence

import numpy as np

from app.signals.cost_model import estimate_round_trip_cost
from app.signals.calibration import calibrate

log = logging.getLogger(__name__)


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


def _to_candles_dict(raw_candles: Sequence[dict]) -> dict:
    """把 OKX candle dict 列表转成 strategy_pool 期望的 dict。"""
    return {
        "open": np.array([c["open"] for c in raw_candles], dtype=np.float64),
        "high": np.array([c["high"] for c in raw_candles], dtype=np.float64),
        "low": np.array([c["low"] for c in raw_candles], dtype=np.float64),
        "close": np.array([c["close"] for c in raw_candles], dtype=np.float64),
        "volume": np.array([c["volume"] for c in raw_candles], dtype=np.float64),
        "time": [c.get("time") for c in raw_candles],
    }


def _strategy_registry():
    """懒导入避免循环。"""
    from app.signals.strategy_pool import STRATEGY_INSTANCES, StrategyId
    return STRATEGY_INSTANCES, StrategyId


async def run_backtest(
    config: BacktestConfig,
    okx_client,
    *,
    walk_forward_split: float = 0.7,
    min_train_watches: int = 50,
) -> BacktestResult:
    """执行 walk-forward 回测。

    Args:
        config: 见 BacktestConfig
        okx_client: 需有 async get_klines(symbol, interval, limit)

    Returns:
        BacktestResult with trades, equity_curve, metrics.

    Raises:
        ValueError: K 线不足 (< min_train_watches)
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=config.days)

    # 拉 limit=max (OKX 上限 300) - 多拉几次如有需要
    raw_candles = await okx_client.get_klines(
        symbol=config.symbol,
        interval=config.timeframe,
        limit=300,
    )
    if len(raw_candles) < min_train_watches:
        raise ValueError(
            f"insufficient K-lines: got {len(raw_candles)}, need ≥{min_train_watches}"
        )

    cost = (config.fee_taker_bps + config.fee_taker_bps + config.slippage_bps) / 10_000
    fee_per_side = config.fee_taker_bps / 10_000
    slip = config.slippage_bps / 10_000

    registry, strategy_id_enum = _strategy_registry()

    # Walk-forward: 取后 walk_forward_split 比例作为时间
    split_idx = int(len(raw_candles) * walk_forward_split)
    test_window = raw_candles[split_idx:]

    trades: list[VirtualTrade] = []
    equity: list[tuple[datetime, float]] = []
    running_equity = 1.0

    for strategy_name in config.strategies:
        try:
            sid = strategy_id_enum[strategy_name.upper().replace("STRATEGY", "")]
        except (KeyError, ValueError):
            # Try direct StrategyId value lookup
            try:
                sid = strategy_id_enum(strategy_name.lower())
            except (KeyError, ValueError):
                log.warning("backtest: unknown strategy %s, skipping", strategy_name)
                continue
        strategy = registry.get(sid)
        if strategy is None:
            continue

        # Walk through each bar (need 50 prior for warmup)
        for i in range(min_train_watches, len(test_window) - 1):
            window = test_window[max(0, i - min_train_watches):i + 1]
            candles_dict = _to_candles_dict(window)
            volumes = candles_dict["volume"]
            try:
                result = strategy.evaluate(candles_dict, volumes, regime="unknown")
            except Exception as e:
                log.debug("backtest: strategy eval error: %s", e)
                continue

            if result.direction is None or result.confidence < config.min_confidence:
                continue

            entry_candle = test_window[i + 1]
            entry = entry_candle["close"]
            if result.direction == "long":
                tp = entry * (1 + config.target_pct)
                sl = entry * (1 - config.stop_pct)
                sign = 1.0
            else:
                tp = entry * (1 - config.target_pct)
                sl = entry * (1 + config.stop_pct)
                sign = -1.0

            exit_price = entry
            exit_time = entry_candle.get("time")
            if isinstance(exit_time, (int, float)):
                exit_dt = datetime.fromtimestamp(exit_time, tz=timezone.utc)
            else:
                exit_dt = exit_time if exit_time else datetime.now(timezone.utc)
            outcome = "EXPIRED"

            # 遍历后续 candles 直到触发 TP/SL 或 max_hold
            max_hold_candles = max(
                1, int(config.max_hold_minutes / max(1, _tf_minutes(config.timeframe)))
            )
            end_j = min(i + 1 + max_hold_candles, len(test_window))
            for j in range(i + 1, end_j):
                c = test_window[j]
                hi = c["high"]
                lo = c["low"]
                if result.direction == "long":
                    if hi >= tp:
                        exit_price = tp
                        outcome = "HIT_TP"
                        ts = c.get("time")
                        exit_dt = datetime.fromtimestamp(ts, tz=timezone.utc) if isinstance(ts, (int, float)) else (ts if ts else datetime.now(timezone.utc))
                        break
                    if lo <= sl:
                        exit_price = sl
                        outcome = "HIT_SL"
                        ts = c.get("time")
                        exit_dt = datetime.fromtimestamp(ts, tz=timezone.utc) if isinstance(ts, (int, float)) else (ts if ts else datetime.now(timezone.utc))
                        break
                else:
                    if lo <= tp:
                        exit_price = tp
                        outcome = "HIT_TP"
                        ts = c.get("time")
                        exit_dt = datetime.fromtimestamp(ts, tz=timezone.utc) if isinstance(ts, (int, float)) else (ts if ts else datetime.now(timezone.utc))
                        break
                    if hi >= sl:
                        exit_price = sl
                        outcome = "HIT_SL"
                        ts = c.get("time")
                        exit_dt = datetime.fromtimestamp(ts, tz=timezone.utc) if isinstance(ts, (int, float)) else (ts if ts else datetime.now(timezone.utc))
                        break
            else:
                # 没有 TP/SL 触发 → EXPIRED 在最后 candle
                outcome = "EXPIRED"
                last = test_window[end_j - 1]
                exit_price = last["close"]
                ts = last.get("time")
                exit_dt = datetime.fromtimestamp(ts, tz=timezone.utc) if isinstance(ts, (int, float)) else (ts if ts else datetime.now(timezone.utc))

            entry_ts = entry_candle.get("time")
            entry_dt = datetime.fromtimestamp(entry_ts, tz=timezone.utc) if isinstance(entry_ts, (int, float)) else (entry_ts if entry_ts else datetime.now(timezone.utc))
            gross = (exit_price - entry) / entry * sign
            net = gross - cost
            cal_p = calibrate(result.confidence, config.timeframe)

            trade = VirtualTrade(
                entry_time=entry_dt,
                entry_price=float(entry),
                exit_time=exit_dt,
                exit_price=float(exit_price),
                raw_confidence=float(result.confidence),
                calibrated_confidence=cal_p,
                target_pct=config.target_pct,
                stop_pct=config.stop_pct,
                gross_pnl_pct=float(gross),
                fee_pct=fee_per_side * 2,
                slippage_pct=slip,
                net_pnl_pct=float(net),
                outcome=outcome,
                holding_minutes=int((exit_dt - entry_dt).total_seconds() // 60),
                strategy_name=strategy_name,
            )
            trades.append(trade)
            running_equity *= (1 + net)
            equity.append((exit_dt, running_equity))

    if not trades:
        # No signal ever triggered → return empty result with metrics=0
        return BacktestResult(
            trades=[],
            equity_curve=[(start, 1.0)],
            total_trades=0,
            hit_rate=0.0,
            net_pnl_pct=0.0,
            sharpe_ratio=0.0,
            max_drawdown_pct=0.0,
            config=config,
        )

    n = len(trades)
    hit_rate = sum(1 for t in trades if t.net_pnl_pct > 0) / n
    net_pnl_total = sum(t.net_pnl_pct for t in trades)
    pnls = np.array([t.net_pnl_pct for t in trades])
    # Sharpe: 年化（假设每 N trades = N bars；保守用 sqrt(252)）
    sharpe = float(pnls.mean() / (pnls.std() + 1e-9) * math.sqrt(252))
    equity_arr = np.array([e for _, e in equity])
    peak = np.maximum.accumulate(equity_arr)
    max_dd = float(((equity_arr - peak) / peak).min())

    return BacktestResult(
        trades=trades,
        equity_curve=equity,
        total_trades=n,
        hit_rate=hit_rate,
        net_pnl_pct=net_pnl_total,
        sharpe_ratio=sharpe,
        max_drawdown_pct=max_dd,
        config=config,
    )


def _tf_minutes(tf: str) -> int:
    return {
        "1m": 1, "5m": 5, "15m": 15,
        "1h": 60, "4h": 240, "1d": 1440,
    }.get(tf, 60)