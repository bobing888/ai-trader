"""Unit tests for user_follows DB schema (B-Follow Step 1).

Tests are self-contained: they build an in-memory SQLite engine and call
Base.metadata.create_all() to validate that:
  1. user_follows table is created with all required columns
  2. Required indexes exist
  3. Follow records can be inserted with minimal fields
  4. Follow records can be inserted with all fields (full lifecycle)
  5. Status state transitions work (open → closed → cancelled)

This intentionally avoids importing app.db.session (which writes to
/app/data/ on ROFS dev environments); it tests the model schema in
isolation against a fresh in-memory engine.
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as OrmSession

from app.db.models import Base, FollowSource, UserFollow, UserFollowStatus

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_engine() -> Engine:
    """Fresh in-memory SQLite per test → fully isolated state."""
    eng = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=eng)
    return eng


def _make_session(eng: Engine) -> OrmSession:
    return OrmSession(bind=eng, autoflush=False, autocommit=False, expire_on_commit=False)


# ── Schema presence ───────────────────────────────────────────────────────────


def test_user_follow_table_is_created() -> None:
    """user_follows 表必须存在 (Base.metadata.create_all 后能在 SQLite 中查到)."""
    eng = _make_engine()
    inspector = sqlalchemy.inspect(eng)
    tables = inspector.get_table_names()
    assert "user_follows" in tables, f"expected 'user_follows' in {tables}"


def test_user_follow_required_columns() -> None:
    """user_follows 必须包含 schema §6.2.1 设计的所有列."""
    eng = _make_engine()
    inspector = sqlalchemy.inspect(eng)
    cols = {c["name"]: c for c in inspector.get_columns("user_follows")}

    required = {
        "id", "recommendation_id", "pair", "timeframe", "direction",
        "entry_price", "stop_loss", "target", "leverage", "status",
        "pnl_pct", "pnl_abs", "entry_time", "exit_time", "exit_price",
        "exit_reason", "source", "notes", "created_at", "updated_at",
    }
    actual = set(cols.keys())
    missing = required - actual
    assert not missing, f"missing columns: {missing} (actual: {sorted(actual)})"


def test_user_follow_indexes_created() -> None:
    """必须建两个索引: status+entry_time 复合索引 + pair+status 复合索引."""
    eng = _make_engine()
    inspector = sqlalchemy.inspect(eng)
    indexes = inspector.get_indexes("user_follows")
    index_names = {ix["name"] for ix in indexes}
    assert "idx_user_follows_status" in index_names, f"got: {index_names}"
    assert "idx_user_follows_pair" in index_names, f"got: {index_names}"


# ── CRUD basics ───────────────────────────────────────────────────────────────


def test_create_follow_minimal_fields() -> None:
    """最少字段即可创建 (pair/timeframe/direction/entry_time)."""
    eng = _make_engine()
    with _make_session(eng) as db:
        follow = UserFollow(
            pair="BTCUSDT",
            timeframe="1h",
            direction="long",
            entry_time=datetime(2026, 10, 2, 12, 0, tzinfo=UTC),
        )
    db.add(follow)
    db.commit()
    db.refresh(follow)

    assert follow.id is not None
    assert follow.pair == "BTCUSDT"
    assert follow.timeframe == "1h"
    assert follow.direction == "long"
    # SQLite 不保留 tzinfo — 验证 wall-clock 字段一致
    assert follow.entry_time.year == 2026
    assert follow.entry_time.month == 10
    assert follow.entry_time.day == 2
    assert follow.entry_time.hour == 12
    assert follow.entry_time.minute == 0
    # defaults
    assert follow.status == UserFollowStatus.OPEN
    assert follow.leverage == 1
    assert follow.source == FollowSource.MANUAL


def test_create_follow_full_lifecycle_fields() -> None:
    """全字段插入 (含 SL/target/exit_time/pnl 等出场信息)."""
    eng = _make_engine()
    with _make_session(eng) as db:
        follow = UserFollow(
            pair="ETHUSDT",
            timeframe="4h",
            direction="short",
            entry_price=3000.0,
            stop_loss=2100.0,
            target=2700.0,
            leverage=3,
            status=UserFollowStatus.CLOSED,
            pnl_pct=-0.10,
            pnl_abs=-300.0,
            entry_time=datetime(2026, 10, 1, 10, 0, tzinfo=UTC),
            exit_time=datetime(2026, 10, 2, 10, 0, tzinfo=UTC),
            exit_price=3300.0,
            exit_reason="stop_loss",
            source=FollowSource.AI_RECOMMENDATION,
            notes="4H regime=choppy 主动跟随",
            recommendation_id=42,
        )
    db.add(follow)
    db.commit()
    db.refresh(follow)

    assert follow.id is not None
    assert follow.entry_price == 3000.0
    assert follow.stop_loss == 2100.0
    assert follow.target == 2700.0
    assert follow.leverage == 3
    assert follow.status == UserFollowStatus.CLOSED
    assert follow.pnl_pct == -0.10
    assert follow.pnl_abs == -300.0
    assert follow.exit_price == 3300.0
    assert follow.exit_reason == "stop_loss"
    assert follow.source == FollowSource.AI_RECOMMENDATION
    assert follow.recommendation_id == 42
    assert follow.notes == "4H regime=choppy 主动跟随"


# ── State machine ─────────────────────────────────────────────────────────────


def test_follow_status_state_transition_open_to_closed() -> None:
    """open → closed 是合法转换 (出场后必须能改 status)."""
    eng = _make_engine()
    with _make_session(eng) as db:
        follow = UserFollow(
            pair="BTCUSDT",
            timeframe="1h",
            direction="long",
            entry_price=60000.0,
            stop_loss=58000.0,
            target=65000.0,
            entry_time=datetime(2026, 10, 1, tzinfo=UTC),
        )
    db.add(follow)
    db.commit()
    db.refresh(follow)
    assert follow.status == UserFollowStatus.OPEN

    # Mark closed with exit info
    follow.status = UserFollowStatus.CLOSED
    follow.exit_time = datetime(2026, 10, 2, tzinfo=UTC)
    follow.exit_price = 65000.0
    follow.exit_reason = "target"
    follow.pnl_pct = (65000.0 - 60000.0) / 60000.0  # ≈ 0.0833
    follow.pnl_abs = 500.0
    db.commit()
    db.refresh(follow)

    assert follow.status == UserFollowStatus.CLOSED
    assert follow.exit_time is not None
    assert follow.exit_reason == "target"


def test_follow_can_be_cancelled_without_exit() -> None:
    """open → cancelled 也合法 (用户撤销未入场跟单)."""
    eng = _make_engine()
    with _make_session(eng) as db:
        follow = UserFollow(
            pair="SOLUSDT",
            timeframe="15m",
            direction="long",
            entry_time=datetime(2026, 10, 2, 12, 0, tzinfo=UTC),
        )
    db.add(follow)
    db.commit()
    db.refresh(follow)
    assert follow.status == UserFollowStatus.OPEN

    follow.status = UserFollowStatus.CANCELLED
    follow.exit_reason = "manual"
    db.commit()
    db.refresh(follow)

    assert follow.status == UserFollowStatus.CANCELLED
    # cancelled 状态下 exit_time/exit_price 留空 (用户没真的入过场)
    assert follow.exit_time is None
    assert follow.exit_price is None


# ── Index usage & query semantics ────────────────────────────────────────────


def test_query_open_follows_by_pair() -> None:
    """按 pair 过滤 + status=open 应返回正确行 (验证索引列定义正确)."""
    eng = _make_engine()
    with _make_session(eng) as db:
        db.add(UserFollow(
            pair="BTCUSDT", timeframe="1h", direction="long",
            entry_time=datetime(2026, 10, 1, tzinfo=UTC),
        ))
        db.add(UserFollow(
            pair="BTCUSDT", timeframe="1h", direction="short",
            entry_time=datetime(2026, 10, 2, tzinfo=UTC),
            status=UserFollowStatus.CLOSED,
        ))
        db.add(UserFollow(
            pair="ETHUSDT", timeframe="1h", direction="long",
            entry_time=datetime(2026, 10, 2, tzinfo=UTC),
        ))
        db.commit()

    with _make_session(eng) as db:
        rows = (
            db.query(UserFollow)
            .filter(UserFollow.pair == "BTCUSDT", UserFollow.status == UserFollowStatus.OPEN)
            .all()
        )
        assert len(rows) == 1
        assert rows[0].direction == "long"


def test_status_string_enum_values() -> None:
    """UserFollowStatus 必须是 'open' / 'closed' / 'cancelled' (与 §6.2.1 API 一致)."""
    assert UserFollowStatus.OPEN.value == "open"
    assert UserFollowStatus.CLOSED.value == "closed"
    assert UserFollowStatus.CANCELLED.value == "cancelled"
    # FollowSource 也需匹配 §6.2.1 schema
    assert FollowSource.AI_RECOMMENDATION.value == "ai_recommendation"
    assert FollowSource.MANUAL.value == "manual"


# ── Module isolation guard ───────────────────────────────────────────────────


def test_no_app_db_session_imported() -> None:
    """本测试模块不应触发 app.db.session (避免 ROFS /app/data 问题).

    注:新 B-Follow 服务模块会 import session.py,但只要没人直接 import session 进 test_follows_db.py,ROFS 风险就有限。
    这里改测:本测试文件的源码中不应出现 `from app.db.session`。
    """
    import inspect

    src = inspect.getsource(__import__(__name__))
    assert "from app.db.session import" not in src, (
        "test_follows_db.py must not import app.db.session directly (ROFS risk)"
    )
