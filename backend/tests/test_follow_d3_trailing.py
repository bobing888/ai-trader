"""D3 测试 — live trailing stop + partial TP

测试目标：
- FollowScheduler._evaluate_d3() 正确触发 partial TP（TP1 触达时）
- Wilder ATR trailing 正确计算 SL 移动
- _close_sync 支持 partial TP（exit_size_pct < 1.0）
- _update_trailing_sl 持久化 current_stop_loss
- _evaluate_price 在 trailing_stop 触发时返回 correct verdict
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.db.models import UserFollow
from app.services.follow_scheduler import (
    ExitVerdict,
    FollowScheduler,
)


def _make_follow(
    direction: str = "long",
    entry_price: float = 100.0,
    current_stop_loss: float | None = 95.0,
    stop_loss: float | None = 95.0,
    take_profit_1_price: float | None = 110.0,
    take_profit_2_price: float | None = 115.0,
    entry_atr: float | None = 5.0,
    entry_price_ref: float | None = None,
    partial_tp_taken: int = 0,
    trailing_stop_enabled: int = 1,
    partial_tp_enabled: int = 1,
) -> UserFollow:
    """构造 mock follow (不写 DB，纯逻辑测试)."""
    f = UserFollow(
        id=1,
        pair="BTC-USDT",
        timeframe="1h",
        direction=direction,
        entry_price=entry_price,
        stop_loss=stop_loss,
        target=take_profit_2_price,
        leverage=2,
        stake_amount=100.0,
        status="open",
        entry_time=datetime.now(UTC) - timedelta(hours=1),
        current_stop_loss=current_stop_loss,
        take_profit_1_price=take_profit_1_price,
        take_profit_2_price=take_profit_2_price,
        entry_atr=entry_atr,
        partial_tp_taken=partial_tp_taken,
        partial_tp_enabled=partial_tp_enabled,
        trailing_stop_enabled=trailing_stop_enabled,
        entry_price_ref=entry_price_ref or entry_price,
        remaining_size_pct=1.0,
    )
    return f


# === partial TP ===

def test_d3_partial_tp_long_triggers_at_tp1():
    """做多 + current_price >= TP1 → partial_tp + exit_size_pct=0.5"""
    f = _make_follow(direction="long", entry_price=100.0, take_profit_1_price=110.0)
    verdict = FollowScheduler._evaluate_price(f, current_price=112.0)
    assert verdict.should_exit
    assert verdict.reason == "partial_tp"
    assert verdict.exit_size_pct == 0.5
    assert verdict.new_stop_loss == f.entry_price  # SL 移到 entry（保本）


def test_d3_partial_tp_short_triggers_at_tp1():
    """做空 + current_price <= TP1 → partial_tp"""
    f = _make_follow(
        direction="short",
        entry_price=100.0,
        take_profit_1_price=90.0,
        current_stop_loss=110.0,
        stop_loss=110.0,
    )
    verdict = FollowScheduler._evaluate_price(f, current_price=88.0)
    assert verdict.should_exit
    assert verdict.reason == "partial_tp"
    assert verdict.exit_size_pct == 0.5


def test_d3_partial_tp_skipped_when_already_taken():
    """partial_tp_taken=1 → 不再触发 partial TP（让 target/trailing 接管）"""
    f = _make_follow(direction="long", entry_price=100.0, take_profit_1_price=110.0, partial_tp_taken=1)
    verdict = FollowScheduler._evaluate_price(f, current_price=112.0)
    assert verdict.reason != "partial_tp"


def test_d3_partial_tp_disabled_skips():
    """partial_tp_enabled=0 → 跳过 partial TP 评估"""
    f = _make_follow(
        direction="long",
        entry_price=100.0,
        take_profit_1_price=110.0,
        partial_tp_enabled=0,
    )
    verdict = FollowScheduler._evaluate_price(f, current_price=112.0)
    assert verdict.reason != "partial_tp"


# === Wilder ATR trailing ===

def test_d3_trailing_sl_moves_up_for_long():
    """做多 + profit >= 1×ATR → new SL > current_sl（SL 移动）"""
    f = _make_follow(
        direction="long",
        entry_price=100.0,
        current_stop_loss=95.0,
        entry_atr=5.0,
    )
    # current_price=106 → profit=6 → profit_atr=1.2 (>= 1.0)
    # 候选 SL = entry_ref + (1.2 - 1) * 5 = 100 + 1.0 = 101
    verdict = FollowScheduler._evaluate_price(f, current_price=106.0)
    assert not verdict.should_exit
    assert verdict.new_stop_loss is not None
    assert verdict.new_stop_loss > f.current_stop_loss
    expected = 100.0 + (6.0 - 5.0) * 1.0
    assert abs(verdict.new_stop_loss - expected) < 0.01


def test_d3_trailing_sl_moves_down_for_short():
    """做空 + profit >= 1×ATR + 未触发 partial TP → new SL < current_sl（SL 下移）"""
    f = _make_follow(
        direction="short",
        entry_price=100.0,
        current_stop_loss=110.0,
        stop_loss=110.0,
        take_profit_1_price=95.0,
        take_profit_2_price=90.0,
        entry_atr=5.0,
        partial_tp_taken=1,  # 跳过 partial_tp 评估
    )
    # current_price=96 → profit=4 → profit_atr=0.8 < 1.0 (不激活)
    # 用 price=93.5 → profit=6.5 → profit_atr=1.3 (>= 1.0) → 但 TP1=95 partial TP 优先
    # 真正测试：partial_tp_taken=1 + price=96 → 不触发 partial，profit_atr=0.8 < 1.0
    # 调整：take_profit_1_price=99.5（极接近 entry）+ price=96
    f2 = _make_follow(
        direction="short",
        entry_price=100.0,
        current_stop_loss=110.0,
        stop_loss=110.0,
        take_profit_1_price=99.5,   # 极接近 entry，不触达
        take_profit_2_price=90.0,
        entry_atr=5.0,
    )
    # current_price=96 → profit=4 → profit_atr=0.8 < 1.0
    # 改用：price=92 → profit=8 → profit_atr=1.6 (>= 1.0)
    # 但 partial_tp_taken=0 + price=92 < TP1=99.5 → 触发 partial
    # 唯一 path：partial_tp_taken=1 跳过 partial，再 price=92 + profit_atr=1.6
    f3 = _make_follow(
        direction="short",
        entry_price=100.0,
        current_stop_loss=110.0,
        stop_loss=110.0,
        take_profit_1_price=99.5,
        take_profit_2_price=90.0,
        entry_atr=5.0,
        partial_tp_taken=1,   # 跳过 partial_tp 评估
    )
    # current_price=92 → profit=8 → profit_atr=1.6
    # 候选 SL = entry_ref - (1.6 - 1) * 5 = 100 - 3.0 = 97
    verdict = FollowScheduler._evaluate_price(f3, current_price=92.0)
    assert not verdict.should_exit
    assert verdict.new_stop_loss is not None
    assert verdict.new_stop_loss < f3.current_stop_loss


def test_d3_trailing_stop_triggers_when_price_falls_below_sl():
    """做多 + current_price 跌穿 trailing SL → trailing_stop 出场"""
    f = _make_follow(
        direction="long",
        entry_price=100.0,
        current_stop_loss=95.0,
        take_profit_1_price=110.0,
        take_profit_2_price=120.0,
        entry_atr=2.0,
        partial_tp_taken=1,  # 跳过 partial_tp 检查
    )
    # current_price=108 → profit_atr=4 → trailing 激活
    # 候选 SL = 100 + (4 - 1) * 2 = 106
    verdict_move = FollowScheduler._evaluate_price(f, current_price=108.0)
    assert not verdict_move.should_exit
    assert verdict_move.new_stop_loss == 106.0
    # 模拟 DB 已 persist new SL
    f.current_stop_loss = verdict_move.new_stop_loss
    # price=105.5 < 106 → 触发 trailing_stop
    verdict = FollowScheduler._evaluate_price(f, current_price=105.5)
    assert verdict.should_exit
    assert verdict.reason == "trailing_stop"


def test_d3_trailing_below_activation_no_movement():
    """profit < 1×ATR → 不激活 trailing（保留初始 SL）"""
    f = _make_follow(
        direction="long",
        entry_price=100.0,
        current_stop_loss=95.0,
        entry_atr=10.0,   # 大 ATR 让 profit_atr 难达 1.0
    )
    # current_price=105 → profit=5 → profit_atr=0.5
    verdict = FollowScheduler._evaluate_price(f, current_price=105.0)
    assert not verdict.should_exit
    assert verdict.new_stop_loss is None


def test_d3_trailing_disabled_skips():
    """trailing_stop_enabled=0 → 跳过 trailing 逻辑"""
    f = _make_follow(
        direction="long",
        entry_price=100.0,
        current_stop_loss=95.0,
        entry_atr=5.0,
        trailing_stop_enabled=0,
    )
    verdict = FollowScheduler._evaluate_price(f, current_price=106.0)
    assert verdict.new_stop_loss is None


# === 集成: partial TP + trailing 链路 ===

def test_d3_partial_tp_then_trailing_long():
    """做多：partial TP1 触发后，剩余 50% 走 trailing，盈利继续扩 → trailing 移动 SL"""
    f = _make_follow(
        direction="long",
        entry_price=100.0,
        current_stop_loss=100.0,
        take_profit_1_price=110.0,
        take_profit_2_price=120.0,
        entry_atr=5.0,
        partial_tp_taken=1,
    )
    # current_price=107 → profit_atr=1.4 → 激活 trailing
    # 候选 SL = 100 + (1.4 - 1) * 5 = 102
    verdict = FollowScheduler._evaluate_price(f, current_price=107.0)
    assert not verdict.should_exit
    assert verdict.new_stop_loss is not None
    assert verdict.new_stop_loss > 100.0


def test_d3_no_entry_atr_falls_back_to_legacy():
    """无 entry_atr（老数据/手工跟单） → 跳过 D3，用原 stop_loss + take_profit_2 判定"""
    f = _make_follow(
        direction="long",
        entry_price=100.0,
        current_stop_loss=95.0,
        stop_loss=95.0,
        take_profit_2_price=110.0,
        entry_atr=None,
    )
    verdict = FollowScheduler._evaluate_price(f, current_price=112.0)
    assert verdict.should_exit
    assert verdict.reason == "target"


# === ExitVerdict 字段 ===

def test_d3_exit_verdict_default_size_is_1():
    """未指定 exit_size_pct → 默认 1.0（全平）"""
    v = ExitVerdict(should_exit=True, reason="stop_loss", exit_price=95.0)
    assert v.exit_size_pct == 1.0
    assert v.new_stop_loss is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])