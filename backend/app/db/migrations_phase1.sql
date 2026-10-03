-- Phase 1 signal credibility — 手动 SQL 迁移 (SQLite)
-- 2026-10-02
--
-- 适用：init_db() 不会迁移已建表的库（旧部署升级时需要手动跑）。
-- 在本地开发 / 全新部署，Base.metadata.create_all 会自动建这些表 + 列。
--
-- 部署到 kbkkk-prod 时手动执行：
--   docker compose exec backend sqlite3 /app/data/strategies.db < /app/app/db/migrations_phase1.sql

-- ── RecommendationHistory 新字段 ──
ALTER TABLE recommendation_history ADD COLUMN calibrated_confidence REAL;
ALTER TABLE recommendation_history ADD COLUMN net_pnl_estimate REAL;
ALTER TABLE recommendation_history ADD COLUMN holding_minutes INTEGER;
ALTER TABLE recommendation_history ADD COLUMN outcome_label VARCHAR(20);
ALTER TABLE recommendation_history ADD COLUMN pnl_pct REAL;
ALTER TABLE recommendation_history ADD COLUMN closed_at DATETIME;
-- 2026-10-03 进/离场时间窗口
ALTER TABLE recommendation_history ADD COLUMN entry_window_minutes INTEGER;
ALTER TABLE recommendation_history ADD COLUMN exit_window_minutes INTEGER;

CREATE INDEX IF NOT EXISTS idx_reco_history_tf_outcome
    ON recommendation_history(timeframe, outcome_label);

-- ── BacktestRun 表 ──
CREATE TABLE IF NOT EXISTS backtest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    strategies JSON NOT NULL DEFAULT '[]',
    days INTEGER NOT NULL DEFAULT 30,
    fee_taker_bps REAL NOT NULL DEFAULT 8.0,
    slippage_bps REAL NOT NULL DEFAULT 5.0,
    min_confidence REAL NOT NULL DEFAULT 0.6,
    target_pct REAL NOT NULL DEFAULT 0.005,
    stop_pct REAL NOT NULL DEFAULT 0.003,
    max_hold_minutes INTEGER NOT NULL DEFAULT 60,
    started_at DATETIME NOT NULL,
    finished_at DATETIME,
    total_trades INTEGER NOT NULL DEFAULT 0,
    hit_rate REAL NOT NULL DEFAULT 0.0,
    net_pnl_pct REAL NOT NULL DEFAULT 0.0,
    sharpe_ratio REAL NOT NULL DEFAULT 0.0,
    max_drawdown_pct REAL NOT NULL DEFAULT 0.0,
    equity_curve JSON NOT NULL DEFAULT '[]',
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_backtest_runs_symbol_status
    ON backtest_runs(symbol, status);
CREATE INDEX IF NOT EXISTS idx_backtest_runs_started_at
    ON backtest_runs(started_at);

-- ── BacktestTrade 表 ──
CREATE TABLE IF NOT EXISTS backtest_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    strategy_name VARCHAR(60) NOT NULL,
    entry_time DATETIME NOT NULL,
    entry_price REAL NOT NULL,
    exit_time DATETIME NOT NULL,
    exit_price REAL NOT NULL,
    raw_confidence REAL NOT NULL,
    calibrated_confidence REAL,
    target_pct REAL NOT NULL,
    stop_pct REAL NOT NULL,
    gross_pnl_pct REAL NOT NULL,
    fee_pct REAL NOT NULL,
    slippage_pct REAL NOT NULL,
    net_pnl_pct REAL NOT NULL,
    outcome VARCHAR(20) NOT NULL,
    holding_minutes INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_backtest_trades_run_id
    ON backtest_trades(run_id);