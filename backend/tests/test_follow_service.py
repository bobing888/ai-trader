"""test_follow_service — TDD: FollowService CRUD + PnL mock compute (spec §4.4)"""


from app.services.follow_service import FollowService


def test_compute_pnl_long_profit():
    """1x 多 + 2% 涨幅 → +2% pnl = +2 USDT (100 stake)。"""
    pct, abs_ = FollowService.compute_pnl(
        entry_price=50000.0,
        exit_price=51000.0,
        direction="long",
        leverage=1,
        stake_amount=100.0,
    )
    assert pct == 0.02
    assert abs_ == 2.0


def test_compute_pnl_short_profit():
    """1x 空 + 2% 跌幅 → +2% pnl。"""
    pct, abs_ = FollowService.compute_pnl(
        entry_price=50000.0,
        exit_price=49000.0,
        direction="short",
        leverage=1,
        stake_amount=100.0,
    )
    assert pct == 0.02
    assert abs_ == 2.0


def test_compute_pnl_long_loss():
    """1x 多 + 1% 跌 → -1% pnl = -1 USDT。"""
    pct, abs_ = FollowService.compute_pnl(
        entry_price=50000.0,
        exit_price=49500.0,
        direction="long",
        leverage=1,
        stake_amount=100.0,
    )
    assert pct == -0.01
    assert abs_ == -1.0


def test_compute_pnl_with_leverage_5x():
    """5x 多 + 1% 涨幅 → +5% pnl。"""
    pct, _ = FollowService.compute_pnl(
        entry_price=50000.0,
        exit_price=50500.0,
        direction="long",
        leverage=5,
        stake_amount=100.0,
    )
    assert pct == 0.05


def test_compute_pnl_zero_stake():
    """stake=0 → abs pnl 0（兼容 stake_amount 可选）。"""
    _, abs_ = FollowService.compute_pnl(
        entry_price=50000.0,
        exit_price=51000.0,
        direction="long",
        leverage=1,
        stake_amount=0.0,
    )
    assert abs_ == 0.0


def test_compute_pnl_default_stake_uses_class_default():
    """不传 stake_amount → 默认 100.0。"""
    _, abs_ = FollowService.compute_pnl(
        entry_price=50000.0,
        exit_price=51000.0,
        direction="long",
        leverage=1,
    )
    assert abs_ == 2.0


# === CRUD tests ===

def test_create_follow_sets_defaults():
    """create() 应填 status=open / entry_time=now / stake_amount=100。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.models import Base, UserFollow

    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng, autoflush=False, autocommit=False)
    db = Session()
    try:
        follow = FollowService.create(db, {
            "pair": "BTC-USDT",
            "timeframe": "1h",
            "direction": "long",
            "entry_price": 50000.0,
            "leverage": 1,
        })
        assert isinstance(follow, UserFollow)
        assert follow.id is not None
        assert follow.status == "open"
        assert follow.stake_amount == 100.0
    finally:
        db.close()


def test_close_follow_writes_pnl():
    """close() 应算 pnl_pct + pnl_abs 并设 status=closed。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.models import Base

    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng, autoflush=False, autocommit=False)
    db = Session()
    try:
        follow = FollowService.create(db, {
            "pair": "ETH-USDT",
            "timeframe": "4h",
            "direction": "long",
            "entry_price": 3000.0,
            "leverage": 1,
        })
        closed = FollowService.close(db, follow.id, exit_price=3100.0, exit_reason="target")
        assert closed.status == "closed"
        assert closed.exit_price == 3100.0
        assert closed.exit_reason == "target"
        # (3100-3000)/3000 * 1 = 3.333% pnl
        assert abs(closed.pnl_pct - 0.0333) < 1e-3
        # pnl_abs = 0.0333 * 100 = 3.33 USDT
        assert abs(closed.pnl_abs - 3.33) < 0.1
    finally:
        db.close()


def test_close_already_closed_raises():
    """close() 已 closed 的跟单 → 抛 ValueError。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.models import Base

    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng, autoflush=False, autocommit=False)
    db = Session()
    try:
        follow = FollowService.create(db, {
            "pair": "SOL-USDT",
            "timeframe": "1h",
            "direction": "short",
            "entry_price": 100.0,
            "leverage": 1,
        })
        FollowService.close(db, follow.id, exit_price=99.0, exit_reason="manual")
        try:
            FollowService.close(db, follow.id, exit_price=98.0, exit_reason="manual")
            raise AssertionError("should raise")
        except ValueError:
            pass
    finally:
        db.close()


def test_cancel_follow_sets_cancelled_status():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.models import Base

    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng, autoflush=False, autocommit=False)
    db = Session()
    try:
        follow = FollowService.create(db, {
            "pair": "BNB-USDT",
            "timeframe": "1h",
            "direction": "long",
            "entry_price": 600.0,
            "leverage": 1,
        })
        cancelled = FollowService.cancel(db, follow.id, reason="manual_cancel")
        assert cancelled.status == "cancelled"
    finally:
        db.close()


def test_list_follows_filters_by_status():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.models import Base

    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng, autoflush=False, autocommit=False)
    db = Session()
    try:
        f1 = FollowService.create(db, {
            "pair": "BTC-USDT", "timeframe": "1h", "direction": "long",
            "entry_price": 50000.0, "leverage": 1,
        })
        f2 = FollowService.create(db, {
            "pair": "ETH-USDT", "timeframe": "1h", "direction": "long",
            "entry_price": 3000.0, "leverage": 1,
        })
        FollowService.close(db, f2.id, exit_price=3100.0, exit_reason="target")

        open_only = FollowService.list(db, status="open")
        closed_only = FollowService.list(db, status="closed")
        all_ = FollowService.list(db, status="all")
        assert len(open_only) == 1
        assert open_only[0].id == f1.id
        assert len(closed_only) == 1
        assert closed_only[0].id == f2.id
        assert len(all_) == 2
    finally:
        db.close()
