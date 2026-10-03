-- Agent tables — Trend Analysis Agent (Task 5)
-- 2026-10-03
--
-- 适用：init_db() 不会迁移已建表的库（旧部署升级时需要手动跑）。
-- 在本地开发 / 全新部署，Base.metadata.create_all 会自动建这些表 + 列。
--
-- 部署到 kbkkk-prod 时手动执行：
--   docker compose exec backend sqlite3 /app/data/strategies.db < /app/app/db/agent/migrations_agent.sql

-- ── ai_trend_analysis 表 ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ai_trend_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pair VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    regime VARCHAR(20) NOT NULL,
    regime_confidence FLOAT NOT NULL,
    reasoning TEXT NOT NULL,
    key_observations JSON NOT NULL DEFAULT '[]',
    risks JSON NOT NULL DEFAULT '[]',
    analysis_status VARCHAR(20) NOT NULL DEFAULT 'success',
    raw_llm_response TEXT,
    created_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ai_trend_pair_tf_created
    ON ai_trend_analysis (pair, timeframe, created_at);

CREATE INDEX IF NOT EXISTS idx_ai_trend_status
    ON ai_trend_analysis (analysis_status);


-- ── agent_recommendation 表 ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agent_recommendation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pair VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    confidence FLOAT NOT NULL,
    rationale TEXT NOT NULL,
    source VARCHAR(20) NOT NULL DEFAULT 'agent',
    created_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_rec_pair_tf_created
    ON agent_recommendation (pair, timeframe, created_at);
