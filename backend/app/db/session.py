"""SQLite 数据库 session 管理"""

import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


def _resolve_db_path() -> str:
    """优先使用 STRATEGIES_DB_PATH 环境变量,否则按环境自动选路径:
    - Docker 部署(/app 存在且可写): 用 /app/data/<file>
    - Host dev: 用 cwd + repo-relative ./data/<file>(避免 ROFS /app/data)
    """
    p = Path(settings.strategies_db_path)
    if p.is_absolute():
        p.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{p}"
    # Docker: /app 存在且可写 → 用 /app/data
    if Path("/app").is_dir() and os.access("/app", os.W_OK):
        p = Path("/app/data") / p
    else:
        # Host dev: 用 cwd + repo-relative ./data
        p = Path.cwd() / "data" / p
    p.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{p}"


engine = create_engine(
    _resolve_db_path(),
    connect_args={"check_same_thread": False},
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    """启动时调用 — create_all + migrate（如有需要）"""
    from app.db import Base  # noqa: F401  触发 model 注册
    from app.db.models import (
        RecommendationHistory,  # noqa: F401
        Strategy,  # noqa: F401
        UserFollow,  # noqa: F401
        BacktestRun,  # noqa: F401  # Phase 1 signal credibility
        BacktestTrade,  # noqa: F401
    )

    Base.metadata.create_all(bind=engine)

    # D3: in-place schema migration for existing user_follows tables
    # SQLite 不支持 ALTER TABLE ADD COLUMN with default, 用 try/except 兜底
    _apply_d3_migration()
    _apply_d1_d2_migration()


def _apply_d3_migration() -> None:
    """Idempotent migration: add D3 columns to user_follows if missing.

    SQLite 不支持 IF NOT EXISTS on ADD COLUMN，所以每个 ADD 都 try/except。
    失败说明 code 已缓存, skip。
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "user_follows" not in insp.get_table_names():
        return

    existing = {c["name"] for c in insp.get_columns("user_follows")}
    migrations: list[tuple[str, str]] = [
        ("trailing_stop_enabled", "INTEGER NOT NULL DEFAULT 1"),
        ("partial_tp_enabled", "INTEGER NOT NULL DEFAULT 1"),
        ("current_stop_loss", "REAL"),
        ("take_profit_1_price", "REAL"),
        ("take_profit_2_price", "REAL"),
        ("entry_atr", "REAL"),
        ("partial_tp_taken", "INTEGER NOT NULL DEFAULT 0"),
        ("remaining_size_pct", "REAL NOT NULL DEFAULT 1.0"),
        ("entry_price_ref", "REAL"),
        ("risk_reward_ratio", "REAL"),
    ]
    with engine.begin() as conn:
        for col, decl in migrations:
            if col not in existing:
                try:
                    conn.execute(text(f"ALTER TABLE user_follows ADD COLUMN {col} {decl}"))
                except Exception:
                    # Column already exists (race) or other — skip silently
                    pass


def _apply_d1_d2_migration() -> None:
    """Idempotent migration: add D1/D2 columns to recommendation_history if missing."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "recommendation_history" not in insp.get_table_names():
        return

    existing = {c["name"] for c in insp.get_columns("recommendation_history")}
    migrations: list[tuple[str, str]] = [
        ("entry_levels_json", "TEXT"),
        ("stop_loss_price", "REAL"),
        ("take_profit_1_price", "REAL"),
        ("take_profit_2_price", "REAL"),
        ("atr", "REAL"),
        ("risk_reward_ratio", "REAL"),
        ("current_price", "REAL"),
        ("quality", "VARCHAR(20)"),
        ("quality_reasons_json", "TEXT"),
    ]
    with engine.begin() as conn:
        for col, decl in migrations:
            if col not in existing:
                try:
                    conn.execute(text(f"ALTER TABLE recommendation_history ADD COLUMN {col} {decl}"))
                except Exception:
                    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI Depends 用的 session 工厂。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
