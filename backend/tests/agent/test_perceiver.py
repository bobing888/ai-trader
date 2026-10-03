"""Tests for backend.app.agent.perceiver — 数据感知层.

覆盖（spec §9 + plan Task 3）：
  - 拉最近 100 根 K 线
  - 调 signals/regime.detect() 拿 RegimeInfo
  - 调 7 个 strategy pool 拿 StrategyResult list
  - 调 signals/cost_model.estimate_round_trip_cost() 拿 CostEstimate
  - data_completeness = 0-1（数据完整度）
  - 拒接非 BTC/ETH（btc-eth-scope Rule 1）
  - K 线 < 30 根 → 标 data_completeness < 1
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.agent.perceiver import PerceivedContext, Perceiver


# === Fixtures ===

def make_candles(n: int = 100, start_price: float = 50000.0) -> list[dict]:
    """生成 mock candles — 模拟 BTC 1h K 线"""
    rng = np.random.default_rng(42)
    closes = start_price + np.cumsum(rng.normal(0, 100, n))
    highs = closes + rng.uniform(50, 200, n)
    lows = closes - rng.uniform(50, 200, n)
    opens = closes + rng.normal(0, 50, n)
    volumes = rng.uniform(100, 500, n)
    timestamps = [
        int((datetime(2026, 10, 3, tzinfo=timezone.utc).timestamp() - (n - i) * 3600) * 1000)
        for i in range(n)
    ]
    return [
        {
            "o": float(o), "h": float(h), "l": float(l), "c": float(c),
            "vol": float(v), "timestamp": ts,
        }
        for o, h, l, c, v, ts in zip(opens, highs, lows, closes, volumes, timestamps)
    ]


# === Tests: PerceivedContext dataclass ===

class TestPerceivedContext:
    def test_creation_with_minimum_fields(self):
        ctx = PerceivedContext(
            pair="BTC-USDT",
            timeframe="1h",
            ohlcv=make_candles(100),
            regime=MagicMock(),  # RegimeInfo, mocked
            strategy_signals=[],
            cost_estimate=MagicMock(),  # CostEstimate, mocked
            data_completeness=1.0,
        )
        assert ctx.pair == "BTC-USDT"
        assert ctx.timeframe == "1h"
        assert len(ctx.ohlcv) == 100
        assert ctx.data_completeness == 1.0

    def test_fetched_at_defaults_to_utc(self):
        ctx = PerceivedContext(
            pair="BTC-USDT", timeframe="1h",
            ohlcv=[], regime=MagicMock(),
            strategy_signals=[], cost_estimate=MagicMock(),
            data_completeness=0.0,
        )
        assert ctx.fetched_at.tzinfo is not None
        assert ctx.fetched_at.tzinfo == timezone.utc


# === Tests: Perceiver.perceive() ===

class TestPerceiverHappyPath:
    @pytest.mark.asyncio
    async def test_perceive_returns_context_for_btc_1h(self):
        """happy path: BTC 1h 100 根 → 完整 PerceivedContext"""
        mock_candles = make_candles(100)

        with patch("app.agent.perceiver.OkxClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get_klines = AsyncMock(return_value=mock_candles)
            MockClient.return_value = mock_client_instance

            perceiver = Perceiver()
            ctx = await perceiver.perceive("BTC-USDT", "1h")

            assert ctx.pair == "BTC-USDT"
            assert ctx.timeframe == "1h"
            assert len(ctx.ohlcv) == 100
            assert ctx.data_completeness == 1.0
            mock_client_instance.get_klines.assert_awaited_once_with(
                symbol="BTC-USDT", interval="1h", limit=100
            )


class TestPerceiverScopeEnforcement:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("pair", ["SOL-USDT", "DOGE-USDT", "XRP-USDT", "BNB-USDT"])
    async def test_non_btc_eth_rejected(self, pair):
        """btc-eth-scope Rule 1：非 BTC/ETH 必须拒"""
        perceiver = Perceiver()
        with pytest.raises(ValueError, match="不在分析范围"):
            await perceiver.perceive(pair, "1h")


class TestPerceiverDataCompleteness:
    @pytest.mark.asyncio
    async def test_partial_data_lowers_completeness(self):
        """K 线 < 100 根 → data_completeness < 1.0"""
        mock_candles = make_candles(50)  # 只有 50 根

        with patch("app.agent.perceiver.OkxClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get_klines = AsyncMock(return_value=mock_candles)
            MockClient.return_value = mock_client_instance

            perceiver = Perceiver()
            ctx = await perceiver.perceive("BTC-USDT", "1h")

            assert len(ctx.ohlcv) == 50
            assert ctx.data_completeness == pytest.approx(0.5, rel=0.01)

    @pytest.mark.asyncio
    async def test_minimum_30_candles(self):
        """K 线 < 30 根 → regime 会回 CHOPPY（per regime.detect shim 行为）"""
        mock_candles = make_candles(20)

        with patch("app.agent.perceiver.OkxClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get_klines = AsyncMock(return_value=mock_candles)
            MockClient.return_value = mock_client_instance

            perceiver = Perceiver()
            ctx = await perceiver.perceive("ETH-USDT", "15m")

            assert len(ctx.ohlcv) == 20
            assert ctx.data_completeness == pytest.approx(0.2, rel=0.01)

    @pytest.mark.asyncio
    async def test_empty_candles(self):
        """K 线 0 根 → data_completeness = 0"""
        with patch("app.agent.perceiver.OkxClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get_klines = AsyncMock(return_value=[])
            MockClient.return_value = mock_client_instance

            perceiver = Perceiver()
            ctx = await perceiver.perceive("BTC-USDT", "1h")

            assert len(ctx.ohlcv) == 0
            assert ctx.data_completeness == 0.0


class TestPerceiverStrategyEvaluation:
    @pytest.mark.asyncio
    async def test_evaluates_all_strategies(self):
        """Perceiver 必须跑所有 7 个 strategy pool 策略"""
        from app.signals.strategy_pool import STRATEGY_INSTANCES

        mock_candles = make_candles(100)

        with patch("app.agent.perceiver.OkxClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get_klines = AsyncMock(return_value=mock_candles)
            MockClient.return_value = mock_client_instance

            perceiver = Perceiver()
            ctx = await perceiver.perceive("BTC-USDT", "1h")

            # StrategyResult 数量 = STRATEGY_INSTANCES 数量
            # 至少 7 个（实际可能更多，但每个都会跑）
            assert len(ctx.strategy_signals) == len(STRATEGY_INSTANCES)


class TestPerceiverRegime:
    @pytest.mark.asyncio
    async def test_regime_is_RegimeInfo(self):
        """regime 字段必须是 RegimeInfo 实例（从 signals.regime）"""
        from app.signals.regime import RegimeInfo

        mock_candles = make_candles(100)

        with patch("app.agent.perceiver.OkxClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get_klines = AsyncMock(return_value=mock_candles)
            MockClient.return_value = mock_client_instance

            perceiver = Perceiver()
            ctx = await perceiver.perceive("BTC-USDT", "1h")

            assert isinstance(ctx.regime, RegimeInfo)


class TestPerceiverCostModel:
    @pytest.mark.asyncio
    async def test_cost_estimate_is_CostEstimate(self):
        """cost_estimate 字段必须是 CostEstimate 实例"""
        from app.signals.cost_model import CostEstimate

        mock_candles = make_candles(100)

        with patch("app.agent.perceiver.OkxClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get_klines = AsyncMock(return_value=mock_candles)
            MockClient.return_value = mock_client_instance

            perceiver = Perceiver()
            ctx = await perceiver.perceive("BTC-USDT", "1h")

            assert isinstance(ctx.cost_estimate, CostEstimate)