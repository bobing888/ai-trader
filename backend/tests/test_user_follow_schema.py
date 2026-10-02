"""test_user_follow_schema — TDD: UserFollow.stake_amount default 100 USDT"""

from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, UserFollow


def _make_session():
    """in-memory SQLite 测试 session。"""
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng, autoflush=False, autocommit=False)()


def test_user_follow_has_stake_amount_default_100():
    """UserFollow 新建并 flush 后 stake_amount 应默认 100.0 USDT（用户 2026-10-02 决定）"""
    db = _make_session()
    try:
        follow = UserFollow(
            pair="BTC-USDT",
            timeframe="1h",
            direction="long",
            entry_price=50000.0,
            leverage=1,
            entry_time=datetime.now(UTC),
        )
        db.add(follow)
        db.commit()
        db.refresh(follow)
        assert follow.stake_amount == 100.0
    finally:
        db.close()


def test_user_follow_stake_amount_can_be_overridden():
    db = _make_session()
    try:
        follow = UserFollow(
            pair="ETH-USDT",
            timeframe="4h",
            direction="short",
            entry_price=3000.0,
            leverage=2,
            stake_amount=500.0,
            entry_time=datetime.now(UTC),
        )
        db.add(follow)
        db.commit()
        db.refresh(follow)
        assert follow.stake_amount == 500.0
    finally:
        db.close()