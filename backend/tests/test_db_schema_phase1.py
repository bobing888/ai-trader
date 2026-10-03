"""Test DB schema Phase 1 — verify RecommendationHistory extension + new tables.

验证：
1. RecommendationHistory 加了 6 个新字段
2. BacktestRun + BacktestTrade 表存在
3. OutcomeLabel 枚举值正确
"""
from app.db.models import (
    RecommendationHistory,
    BacktestRun,
    BacktestTrade,
    OutcomeLabel,
)


def test_recommendation_history_has_new_fields():
    cols = {c.name for c in RecommendationHistory.__table__.columns}
    for field in ("calibrated_confidence", "net_pnl_estimate",
                  "holding_minutes", "outcome_label", "pnl_pct", "closed_at"):
        assert field in cols, f"missing column {field}"


def test_backtest_run_table_exists():
    cols = {c.name for c in BacktestRun.__table__.columns}
    expected = {"id", "symbol", "timeframe", "strategies", "days",
                "fee_taker_bps", "slippage_bps", "min_confidence",
                "target_pct", "stop_pct", "max_hold_minutes",
                "started_at", "finished_at", "total_trades", "hit_rate",
                "net_pnl_pct", "sharpe_ratio", "max_drawdown_pct",
                "equity_curve", "status", "error_message"}
    missing = expected - cols
    assert not missing, f"BacktestRun missing columns: {missing}"


def test_backtest_trade_table_exists():
    cols = {c.name for c in BacktestTrade.__table__.columns}
    expected = {"id", "run_id", "symbol", "timeframe", "strategy_name",
                "entry_time", "entry_price", "exit_time", "exit_price",
                "raw_confidence", "calibrated_confidence", "target_pct",
                "stop_pct", "gross_pnl_pct", "fee_pct", "slippage_pct",
                "net_pnl_pct", "outcome", "holding_minutes"}
    missing = expected - cols
    assert not missing, f"BacktestTrade missing columns: {missing}"


def test_outcome_label_enum_values():
    values = {e.value for e in OutcomeLabel}
    assert values == {"pending", "hit_tp", "hit_sl", "expired", "hold"}