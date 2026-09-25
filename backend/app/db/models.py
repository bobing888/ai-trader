"""SQLAlchemy ORM 模型 — Strategy 持久化"""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Strategy(Base):
    """交易策略元数据。

    `code` 字段保存策略的 Python 源码或 JSON 配置（取决于 strategy_type）。
    """

    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    strategy_type: Mapped[str] = mapped_column(String(40), nullable=False, default="custom")
    # source: manual | github:<owner/repo> | builtin
    source: Mapped[str] = mapped_column(String(120), nullable=False, default="manual")
    # parameters 是策略参数 (dict)
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # code 是策略源码（如果有）
    code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # status: enabled | disabled
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="enabled")
    # 权重（用于组合权重投票）
    weight: Mapped[float] = mapped_column(nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
