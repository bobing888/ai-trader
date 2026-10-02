"""SQLAlchemy ORM 模型 — Strategy + Follow 持久化"""

from datetime import UTC, datetime, timezone
from enum import StrEnum

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserFollowStatus(StrEnum):
    """UserFollow.status 合法值（与 §6.2.1 schema + API 一致）。"""
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class FollowSource(StrEnum):
    """UserFollow.source 合法值。"""
    AI_RECOMMENDATION = "ai_recommendation"
    MANUAL = "manual"


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


class UserFollow(Base):
    """用户跟单记录（§6.2.1 B-Follow schema）。

    与 AI recommendations 双表分离：跟单时 snapshot AI 价位，但允许用户
    手动覆盖 entry/stop/target。PnL mock 计算（不接 freqtrade 实盘）。

    状态机: OPEN → CLOSED（出场）| CANCELLED（撤销未入场）。
    """

    __tablename__ = "user_follows"
    __table_args__ = (
        Index("idx_user_follows_status", "status", "entry_time"),
        Index("idx_user_follows_pair", "pair", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 可空 — 用户手填跟单时为 None
    recommendation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    pair: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # long|short|neutral

    # 实际入场价 — 跟单时 snapshot AI 价位，用户可手动覆盖
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    target: Mapped[float | None] = mapped_column(Float, nullable=True)
    leverage: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # 状态机 — 用 str 列 + 枚举校验
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=UserFollowStatus.OPEN.value,
    )

    # PnL mock — 出场后填
    pnl_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl_abs: Mapped[float | None] = mapped_column(Float, nullable=True)

    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(
        String(40), nullable=True,  # manual|stop_loss|target|expired|ai_signal_reversed
    )

    source: Mapped[str] = mapped_column(
        String(40), nullable=False, default=FollowSource.MANUAL.value,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
