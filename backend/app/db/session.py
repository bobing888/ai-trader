"""SQLite 数据库 session 管理"""

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


def _resolve_db_path() -> str:
    """优先使用 STRATEGIES_DB_PATH 环境变量，否则用 ./data/strategies.db"""
    p = Path(settings.strategies_db_path)
    if not p.is_absolute():
        p = Path("/app/data") / p
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
    from app.db.models import Strategy  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI Depends 用的 session 工厂。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
