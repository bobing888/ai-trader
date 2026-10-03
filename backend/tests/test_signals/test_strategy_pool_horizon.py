"""
test_strategy_pool_horizon.py — Task 3
验证每个 strategy dataclass 都声明了 horizon_tier + informative_timeframes
"""

import pytest


def test_each_strategy_declares_horizon_tier():
    """每个策略都必须声明 horizon_tier 和 informative_timeframes。"""
    from app.signals.strategy_pool import STRATEGY_INSTANCES
    from app.signals.horizon import HorizonTier

    for strategy_id, strategy in STRATEGY_INSTANCES.items():
        assert hasattr(strategy, "horizon_tier"), (
            f"{strategy_id.value} missing horizon_tier"
        )
        assert hasattr(strategy, "informative_timeframes"), (
            f"{strategy_id.value} missing informative_timeframes"
        )
        assert isinstance(strategy.horizon_tier, HorizonTier), (
            f"{strategy_id.value}.horizon_tier must be HorizonTier, got {type(strategy.horizon_tier)}"
        )
        assert isinstance(strategy.informative_timeframes, list), (
            f"{strategy_id.value}.informative_timeframes must be list, got {type(strategy.informative_timeframes)}"
        )
        assert all(isinstance(tf, str) for tf in strategy.informative_timeframes), (
            f"{strategy_id.value}.informative_timeframes must contain strings"
        )


def test_strategy_pool_has_at_least_one_p0():
    """至少要有 1 个 P0 策略（长期或跨月）。"""
    from app.signals.strategy_pool import STRATEGY_INSTANCES
    from app.signals.horizon import HorizonTier

    p0_strategies = [
        s for s in STRATEGY_INSTANCES.values()
        if s.horizon_tier.is_p0
    ]
    assert len(p0_strategies) >= 1, (
        f"Expected >= 1 P0 strategies, got {len(p0_strategies)}"
    )


def test_strategy_pool_has_p1_and_p2_and_p3():
    """至少各有 1 个 P1 / P2 / P3 策略。"""
    from app.signals.strategy_pool import STRATEGY_INSTANCES
    from app.signals.horizon import HorizonTier

    p1 = [s for s in STRATEGY_INSTANCES.values() if s.horizon_tier.is_p1]
    p2 = [s for s in STRATEGY_INSTANCES.values() if s.horizon_tier.is_p2]
    p3 = [s for s in STRATEGY_INSTANCES.values() if s.horizon_tier.is_p3]

    assert len(p1) >= 1, f"Expected >= 1 P1 strategies, got {len(p1)}"
    assert len(p2) >= 1, f"Expected >= 1 P2 strategies, got {len(p2)}"
    assert len(p3) >= 1, f"Expected >= 1 P3 strategies, got {len(p3)}"


def test_all_8_strategies_tagged():
    """确保 8 个策略全部被标记（覆盖率兜底）。"""
    from app.signals.strategy_pool import STRATEGY_INSTANCES, StrategyId

    expected_ids = {
        StrategyId.MOMENTUM,
        StrategyId.REVERSAL,
        StrategyId.BREAKOUT,
        StrategyId.VOLATILITY,
        StrategyId.SENTIMENT,
        StrategyId.VOLUME,
        StrategyId.MULTI_TF,
        StrategyId.CONFLUENCE,
    }
    assert set(STRATEGY_INSTANCES.keys()) == expected_ids, (
        f"Expected 8 strategy IDs, got {set(STRATEGY_INSTANCES.keys())}"
    )
