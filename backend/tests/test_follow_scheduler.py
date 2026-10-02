"""test_follow_scheduler — TDD: FollowScheduler 4 exit paths + price-fetch failure tolerated

- test_stop_loss_triggers
- test_target_triggers
- test_expired_triggers
- test_no_exit_when_in_range
- test_choppy_regime_no_reversal (covered by detector)
"""

from datetime import UTC, datetime, timedelta

from app.services.follow_scheduler import ExitVerdict, FollowScheduler


class _FakeFollow:
    def __init__(self, direction="long", stop_loss=None, target=None, hours_ago=0):
        self.direction = direction
        self.stop_loss = stop_loss
        self.target = target
        self.entry_time = datetime.now(UTC) - timedelta(hours=hours_ago)


def test_stop_loss_triggers_long():
    follow = _FakeFollow(direction="long", stop_loss=49500.0, target=None)
    verdict = FollowScheduler._evaluate_price(follow, 49000.0)
    assert verdict.should_exit is True
    assert verdict.reason == "stop_loss"


def test_stop_loss_does_not_trigger_when_price_above():
    follow = _FakeFollow(direction="long", stop_loss=49000.0, target=None)
    verdict = FollowScheduler._evaluate_price(follow, 50000.0)
    assert verdict.should_exit is False


def test_target_triggers_long():
    follow = _FakeFollow(direction="long", stop_loss=None, target=51000.0)
    verdict = FollowScheduler._evaluate_price(follow, 51500.0)
    assert verdict.should_exit is True
    assert verdict.reason == "target"


def test_target_triggers_short():
    """空头 target 应 <= 触发。"""
    follow = _FakeFollow(direction="short", stop_loss=None, target=49000.0)
    verdict = FollowScheduler._evaluate_price(follow, 48500.0)
    assert verdict.should_exit is True
    assert verdict.reason == "target"


def test_expired_triggers_after_24h():
    """hours_ago=25 → expired。"""
    follow = _FakeFollow(direction="long", stop_loss=None, target=None, hours_ago=25)
    verdict = FollowScheduler._evaluate_price(follow, 50000.0)
    assert verdict.should_exit is True
    assert verdict.reason == "expired"


def test_no_exit_when_in_range():
    """价格未触及 SL/TP，且未到期。"""
    follow = _FakeFollow(direction="long", stop_loss=49000.0, target=51000.0, hours_ago=1)
    verdict = FollowScheduler._evaluate_price(follow, 50500.0)
    assert verdict.should_exit is False


def test_stop_loss_priority_over_target():
    """同时满足 SL + TP 时，SL 优先（保守）。"""
    follow = _FakeFollow(direction="long", stop_loss=51000.0, target=51000.0)
    verdict = FollowScheduler._evaluate_price(follow, 51000.0)
    assert verdict.should_exit is True
    assert verdict.reason == "stop_loss"


def test_exit_verdict_has_exit_price():
    """verdict 应携带 exit_price 用于 PnL 计算。"""
    follow = _FakeFollow(direction="long", stop_loss=49000.0)
    verdict = FollowScheduler._evaluate_price(follow, 48800.0)
    assert isinstance(verdict, ExitVerdict)
    assert verdict.exit_price == 48800.0