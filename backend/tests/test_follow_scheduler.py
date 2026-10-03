"""test_follow_scheduler — TDD: FollowScheduler 4 exit paths + price-fetch failure tolerated

- test_stop_loss_triggers
- test_target_triggers
- test_expired_triggers
- test_no_exit_when_in_range
- test_choppy_regime_no_reversal (covered by detector)
- test_signal_reversal_exits (Step 3-A: detect_reversal 接入 scheduler)
- test_signal_reversal_no_close_when_steady
- test_scan_pair_calls_detect_reversal_with_3min_history
- test_price_exit_does_not_skip_when_no_history
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.services.follow_scheduler import ExitVerdict, FollowScheduler


class _FakeFollow:
    def __init__(self, direction="long", stop_loss=None, target=None, hours_ago=0):
        self.direction = direction
        self.stop_loss = stop_loss
        self.target = target
        self.entry_time = datetime.now(UTC) - timedelta(hours=hours_ago)
        # D3 defaults — scheduler needs these to evaluate trailing stop
        self.entry_atr = None
        self.entry_price = None
        self.trailing_stop_enabled = 0
        self.partial_tp_enabled = 0
        self.current_stop_loss = stop_loss
        self.take_profit_1_price = None
        self.take_profit_2_price = None
        self.partial_tp_taken = 0
        self.remaining_size_pct = 1.0
        self.entry_price_ref = None
        self.risk_reward_ratio = None


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


# === Step 3-A: detect_reversal 接入 scheduler（B-Follow spec §4.2）===


class _FakeRec:
    """测试用 RecommendationHistory stand-in（不动 SQLAlchemy）。"""

    def __init__(
        self,
        direction: str | None = None,
        regime: str | None = None,
        scanned_at: datetime | None = None,
    ):
        self.direction = direction
        self.regime = regime
        self.scanned_at = scanned_at or datetime.now(UTC)


class _FakeFollowWithMeta(_FakeFollow):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.pair = "BTC-USDT"
        self.timeframe = "1h"


def test_signal_reversal_regime_flip_triggers_exit():
    """regime long→bear 的 OPEN long follow → 应触发 ai_signal_reversed 出场。"""
    follow = _FakeFollowWithMeta(direction="long")
    current = _FakeRec(direction="short", regime="bear")
    previous = _FakeRec(direction="long", regime="bull")

    verdict = FollowScheduler._evaluate_signal_reversal(follow, current, previous, [])
    assert verdict.should_exit is True
    assert verdict.reason == "ai_signal_reversed"


def test_signal_reversal_consecutive_reversal_triggers_exit():
    """连续 2 帧都跟 follow 方向相反（regime 不是 bull/bear/crisis 时）→ 仍触发。"""
    follow = _FakeFollowWithMeta(direction="long")
    now = datetime.now(UTC)
    current = _FakeRec(direction="short", regime="choppy", scanned_at=now)
    previous = _FakeRec(direction="short", regime="choppy", scanned_at=now - timedelta(seconds=60))

    verdict = FollowScheduler._evaluate_signal_reversal(follow, current, previous, [])
    assert verdict.should_exit is True
    assert verdict.reason == "ai_signal_reversed"


def test_signal_reversal_no_close_when_steady():
    """同 direction + 同 regime → 不触发。"""
    follow = _FakeFollowWithMeta(direction="long")
    current = _FakeRec(direction="long", regime="bull")
    previous = _FakeRec(direction="long", regime="bull")

    verdict = FollowScheduler._evaluate_signal_reversal(follow, current, previous, [])
    assert verdict.should_exit is False
    assert verdict.reason is None


def test_signal_reversal_returns_false_when_current_none():
    """current 缺帧（无 history）→ 不触发，让 price 评估兜底。"""
    follow = _FakeFollowWithMeta(direction="long")

    verdict = FollowScheduler._evaluate_signal_reversal(follow, None, None, [])
    assert verdict.should_exit is False
    assert verdict.reason is None


# === Step 3-C: _default_price_source 处理 OKX ticker 真实形状 ===


@pytest.mark.asyncio
async def test_default_price_source_reads_price_key():
    """OKX ticker 真实形状: {\"price\": 85777.5, \"change_24h\": ...}, 不是 {\"last\": ...}"""
    from app.data import okx
    from app.services import follow_scheduler as fs

    async def fake_get_ticker(pair):
        return {"price": 85777.5, "change_24h": 2.67}

    # monkeypatch okx_client.get_ticker
    original = okx.okx_client.get_ticker
    okx.okx_client.get_ticker = fake_get_ticker
    try:
        price = await fs._default_price_source("BTC-USDT")
    finally:
        okx.okx_client.get_ticker = original
    assert price == 85777.5


@pytest.mark.asyncio
async def test_default_price_source_handles_empty_ticker():
    """空 ticker (network down) → 返回 None, scheduler skip."""
    from app.data import okx
    from app.services import follow_scheduler as fs

    async def fake_get_ticker(pair):
        return None

    original = okx.okx_client.get_ticker
    okx.okx_client.get_ticker = fake_get_ticker
    try:
        price = await fs._default_price_source("BTC-USDT")
    finally:
        okx.okx_client.get_ticker = original
    assert price is None
