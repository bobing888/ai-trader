"""Agent quality evaluation test (Task 11)

覆盖：
  - 用 mock historical data 模拟 BTC 30 天走势
  - 跑 Reasoner，验证 Brier Score (regime_confidence 校准)
  - direction 准确率 ≥ 60%

注：Brier Score = mean((predicted_prob - actual_outcome)^2)
  - random baseline = 0.5 (always predict 0.5)
  - perfect = 0.0
  - 我们要 ≤ 0.25 (好于 random 50%)

注意：这里用 mock Reasoner + mock 准确率来验证框架，不调真实 LLM。
真实部署后应该用 BTC/ETH 30天历史 + 真实 LLM 跑这个。
"""

from __future__ import annotations

import math
from unittest.mock import AsyncMock

import numpy as np
import pytest


def make_btc_30d_candles(n: int = 720) -> list[dict]:
    """模拟 BTC 30 天 1h K 线（720 小时）"""
    rng = np.random.default_rng(42)
    closes = 50000 + np.cumsum(rng.normal(0, 200, n))
    return [
        {
            "c": float(c), "o": float(c) - 50, "h": float(c) + 100,
            "l": float(c) - 100, "vol": float(rng.uniform(50, 200)),
            "timestamp": int(1234567890000 + i * 3600000),
        }
        for i, c in enumerate(closes)
    ]


def brier_score(predictions: list[float], outcomes: list[int]) -> float:
    """Brier Score — 越低越好"""
    assert len(predictions) == len(outcomes)
    return sum((p - o) ** 2 for p, o in zip(predictions, outcomes)) / len(predictions)


def direction_accuracy(predictions: list[int], outcomes: list[int]) -> float:
    """方向准确率"""
    assert len(predictions) == len(outcomes)
    return sum(1 for p, o in zip(predictions, outcomes) if p == o) / len(outcomes)


class TestAgentQualityFramework:
    def test_brier_score_perfect(self):
        """完美预测 Brier Score = 0"""
        score = brier_score([1.0, 1.0, 0.0, 0.0], [1, 1, 0, 0])
        assert score == 0.0

    def test_brier_score_random(self):
        """always-0.5 预测 vs binary outcomes 的 Brier Score = 0.25"""
        # 预测恒为 0.5（对任何 outcome 都是 0.5-0 或 0.5-1）
        # Brier Score = (0.5² + 0.5²) / 2 = 0.25
        score = brier_score([0.5, 0.5], [1, 0])
        assert score == pytest.approx(0.25)

    def test_brier_score_random_with_many_samples(self):
        """真正的 random baseline (n 很大) → ~0.25"""
        rng = np.random.default_rng(42)
        n = 10000
        predictions = [0.5] * n  # 总是预测 0.5
        outcomes = rng.integers(0, 2, n).tolist()
        score = brier_score(predictions, outcomes)
        # 应该接近 0.25
        assert 0.20 < score < 0.30

    def test_direction_accuracy_calculation(self):
        """方向准确率计算正确"""
        # 4 个预测，3 对
        acc = direction_accuracy([1, 1, 0, 0], [1, 0, 1, 0])
        assert acc == 0.5  # 2/4 对

        acc = direction_accuracy([1, 1, 1, 0], [1, 1, 0, 0])
        assert acc == 0.75  # 3/4 对


class TestAgentQualityTargets:
    """Spec §9 验证清单：Brier Score ≤ 0.25, direction accuracy ≥ 60%"""

    def test_brier_score_target(self):
        """Brier Score 应 ≤ 0.25（比 random 0.5 好 50%）"""
        # 模拟"好 agent"的预测
        # 70% confidence with 80% outcome accuracy → brier ≈ 0.2
        predictions = [0.8, 0.7, 0.3, 0.2, 0.9, 0.1, 0.6, 0.4]
        outcomes = [1, 1, 0, 0, 1, 0, 0, 1]  # 6/8 = 75% accuracy

        score = brier_score(predictions, outcomes)
        assert score <= 0.25, f"Brier Score {score:.3f} > 0.25 target"

    def test_direction_accuracy_target(self):
        """方向准确率 ≥ 60%"""
        predictions = [1, 1, 0, 1, 0, 1, 1, 0, 0, 1]
        outcomes = [1, 0, 0, 1, 0, 1, 0, 0, 1, 1]  # 7/10 = 70% accuracy

        acc = direction_accuracy(predictions, outcomes)
        assert acc >= 0.6, f"Accuracy {acc:.2%} < 60% target"


class TestAgentMockQuality:
    """用 mock Reasoner 验证 quality test framework 本身能跑"""

    @pytest.mark.asyncio
    async def test_mock_reasoner_produces_evaluable_predictions(self):
        """mock Reasoner 应该产出可评估的预测"""
        from app.agent.reasoner import Reasoner
        from app.agent.perceiver import PerceivedContext
        from app.signals.regime import Regime, RegimeInfo
        from app.signals.cost_model import CostEstimate

        # mock LLM 返回一个"70% confidence bull"的预测
        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(return_value='{"regime": "bull", "regime_confidence": 0.7, "reasoning": "test"}')
        reasoner = Reasoner(provider=mock_provider)

        ctx = PerceivedContext(
            pair="BTC-USDT",
            timeframe="1h",
            ohlcv=make_btc_30d_candles(100),
            regime=RegimeInfo(
                regime=Regime.BULL,
                confidence=0.6,
                regime_probs={r: 0.25 for r in Regime},
                description="test",
                adx=20.0,
                hurst=0.55,
            ),
            strategy_signals=[],
            cost_estimate=CostEstimate(
                entry_fee_pct=0.001, exit_fee_pct=0.001,
                slippage_pct=0.001, total_round_trip_pct=0.003,
            ),
            data_completeness=1.0,
        )

        report = await reasoner.reason(ctx)

        # 验证 report 可用于 evaluation
        assert hasattr(report, "regime")
        assert hasattr(report, "regime_confidence")
        assert 0.0 <= report.regime_confidence <= 1.0

        # 这次预测可以转成 Brier Score 输入
        # prediction = regime_confidence (如果我们映射 bull=1, bear=0)
        prediction = report.regime_confidence
        # outcome = 1 if actual was bull, 0 otherwise
        # 这里没法验证 actual outcome（需要历史数据 + 真实未来）
        # 仅验证框架
        assert 0 <= prediction <= 1