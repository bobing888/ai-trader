"""test_signal_change_detector — TDD: 8 cases per spec §7.1

1. regime flip long→bear 立即触发
2. 3 分钟窗口外不触发
3. previous=None 不触发
4. 连续 2 帧反转 → 触发 consecutive_reversal
5. 单帧反转 → 不触发
6. choppy regime flip 不触发
7. 同 direction 不反转
8. lookback 缺帧时 tolerate（只看 previous + current）
"""

from datetime import UTC, datetime, timedelta

from app.db.models import (
    RecommendationHistory,
    UserFollow,
)
from app.services.signal_change_detector import detect_reversal


def _make_follow(direction: str = "long") -> UserFollow:
    return UserFollow(
        id=1,
        pair="BTC-USDT",
        timeframe="1h",
        direction=direction,
        entry_price=50000.0,
        leverage=1,
        status="open",
        stake_amount=100.0,
        entry_time=datetime.now(UTC),
    )


def _make_rec(
    direction: str | None,
    regime: str | None,
    scanned_minutes_ago: int = 0,
) -> RecommendationHistory:
    return RecommendationHistory(
        pair="BTC-USDT",
        timeframe="1h",
        has_signal=True,
        direction=direction,
        confidence=0.8,
        regime=regime,
        regime_confidence=0.9,
        outcome="has_signal",
        scanned_at=datetime.now(UTC) - timedelta(minutes=scanned_minutes_ago),
        source="okx",
    )


def test_regime_flip_long_to_bear_triggers_immediately():
    """case 1: regime 长 follower + 此刻 regime 转 bear → regime_flip。"""
    follow = _make_follow("long")
    current = _make_rec("short", "bear")
    verdict = detect_reversal(follow, current, previous=None, lookback_history=[])
    assert verdict.reversed is True
    assert verdict.reason == "regime_flip"


def test_regime_flip_short_to_bull_triggers_immediately():
    """case 1b: 空头 follower + regime 转 bull → regime_flip。"""
    follow = _make_follow("short")
    current = _make_rec("long", "bull")
    verdict = detect_reversal(follow, current, previous=None, lookback_history=[])
    assert verdict.reversed is True
    assert verdict.reason == "regime_flip"


def test_outside_3min_window_does_not_trigger():
    """case 2: previous 距 current 5 分钟 → 不在窗口内 → 不触发。"""
    follow = _make_follow("long")
    previous = _make_rec("long", "bull", scanned_minutes_ago=5)  # older
    current = _make_rec("short", "bull", scanned_minutes_ago=0)
    verdict = detect_reversal(follow, current, previous, lookback_history=[previous])
    assert verdict.reversed is False


def test_no_previous_does_not_trigger():
    """case 3: 进程重启后第一帧 → previous=None → 不触发（避免误判）。"""
    follow = _make_follow("long")
    current = _make_rec("short", "bull")
    verdict = detect_reversal(follow, current, previous=None, lookback_history=[])
    assert verdict.reversed is False


def test_consecutive_2_reversals_trigger():
    """case 4: previous + current 都是反方向 → consecutive_reversal。"""
    follow = _make_follow("long")
    previous = _make_rec("short", "bull", scanned_minutes_ago=1)
    current = _make_rec("short", "bull", scanned_minutes_ago=0)
    lookback = [previous, current]
    verdict = detect_reversal(follow, current, previous, lookback_history=lookback)
    assert verdict.reversed is True
    assert verdict.reason == "consecutive_reversal"


def test_single_reversal_does_not_trigger():
    """case 5: 只有 current 反 → previous 同方向 → 不触发（避免噪声）。"""
    follow = _make_follow("long")
    previous = _make_rec("long", "bull", scanned_minutes_ago=1)
    current = _make_rec("short", "bull", scanned_minutes_ago=0)
    lookback = [previous, current]
    verdict = detect_reversal(follow, current, previous, lookback_history=lookback)
    assert verdict.reversed is False


def test_choppy_regime_flip_does_not_trigger():
    """case 6: choppy regime 噪声大 → 不算 flip。"""
    follow = _make_follow("long")
    current = _make_rec("short", "choppy")
    verdict = detect_reversal(follow, current, previous=None, lookback_history=[])
    assert verdict.reversed is False


def test_same_direction_no_reversal():
    """case 7: 跟单 long，current 也 long → 不触发。"""
    follow = _make_follow("long")
    current = _make_rec("long", "bull")
    verdict = detect_reversal(follow, current, previous=None, lookback_history=[])
    assert verdict.reversed is False


def test_lookback_missing_frames_tolerated():
    """case 8: lookback 只 1 帧，但 previous + current 都是反方向 → 仍判定。"""
    follow = _make_follow("long")
    previous = _make_rec("short", "bull", scanned_minutes_ago=1)
    current = _make_rec("short", "bull", scanned_minutes_ago=0)
    # lookback 空 — 只看 previous + current
    verdict = detect_reversal(follow, current, previous, lookback_history=[])
    assert verdict.reversed is True
    assert verdict.reason == "consecutive_reversal"


def test_regime_flip_takes_priority_over_consecutive():
    """优先级: regime_flip 优先于 consecutive。"""
    follow = _make_follow("long")
    previous = _make_rec("long", "bull", scanned_minutes_ago=10)  # outside
    current = _make_rec("short", "bear", scanned_minutes_ago=0)  # regime flip
    verdict = detect_reversal(follow, current, previous, lookback_history=[])
    # regime_flip 优先 — 即使 consecutive 不满足也触发
    assert verdict.reversed is True
    assert verdict.reason == "regime_flip"
