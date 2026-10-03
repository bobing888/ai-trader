"""Perceiver — 数据感知层（Task 3）.

职责：
  1. 拉最近 100 根 K 线（OKX HTTP）
  2. 调 signals/regime.detect() 拿 RegimeInfo
  3. 跑 7 个 strategy pool 策略拿 StrategyResult list
  4. 调 signals/cost_model.estimate_round_trip_cost() 拿 CostEstimate
  5. 算 data_completeness（0-1）

不做什么：
  - 不调 LLM
  - 不写 DB
  - 不改 signals/* 任何文件（只读）

参考 spec: docs/superpowers/specs/2026-10-03-trend-analysis-agent.md §3-4
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.agent.schemas import ALLOWED_PAIRS, ALLOWED_TIMEFRAMES
from app.data.okx import OkxClient
from app.signals.cost_model import CostEstimate, estimate_round_trip_cost
from app.signals.regime import RegimeDetector, RegimeInfo
from app.signals.strategy_pool import (
    STRATEGY_INSTANCES,
    Strategy,
    StrategyId,
    StrategyResult,
)


# === Constants ===

# 期望 K 线根数（用于算 data_completeness）
TARGET_CANDLES = 100

# 策略最少需要多少根 K 线才能 evaluate
MIN_CANDLES_FOR_STRATEGY = 30


# === PerceivedContext dataclass ===

@dataclass(frozen=True)
class PerceivedContext:
    """Perceiver 产出的完整感知快照 — 喂给 Reasoner"""

    pair: str
    timeframe: str
    ohlcv: list[dict]                    # 最近 N 根 K 线
    regime: RegimeInfo
    strategy_signals: list[StrategyResult]
    cost_estimate: CostEstimate
    data_completeness: float             # 0-1
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# === Perceiver ===

class Perceiver:
    """数据感知器 — 拉 signals/* 输出 + OHLCV"""

    def __init__(self, okx_client: OkxClient | None = None) -> None:
        self._client = okx_client or OkxClient()

    async def perceive(self, pair: str, timeframe: str) -> PerceivedContext:
        """主入口 — 拉数据 + 算感知快照

        Args:
            pair: 交易对 (BTC-USDT or ETH-USDT)
            timeframe: 时间周期 (5m / 15m / 1h / 1d)

        Returns:
            PerceivedContext

        Raises:
            ValueError: pair 不在 BTC/ETH 范围
            ValueError: timeframe 不在 5m/15m/1h/1d
        """
        # 1. 范围校验（btc-eth-scope Rule 1）
        if pair not in ALLOWED_PAIRS:
            raise ValueError(
                f"{pair} 不在分析范围。AI-Trader 当前只覆盖 {ALLOWED_PAIRS}。"
                "其他币种请用 freqtrade / 其他工具。"
            )
        if timeframe not in ALLOWED_TIMEFRAMES:
            raise ValueError(
                f"timeframe {timeframe} 不在允许范围 {ALLOWED_TIMEFRAMES}"
            )

        # 2. 拉 K 线
        ohlcv = await self._client.get_klines(
            symbol=pair, interval=timeframe, limit=TARGET_CANDLES
        )

        # 3. 算 data_completeness（0-1）
        data_completeness = min(1.0, len(ohlcv) / TARGET_CANDLES)

        # 4. 调 regime detector
        regime_info: RegimeInfo = RegimeDetector.detect(ohlcv, timeframe=timeframe)

        # 5. 跑所有 strategy pool 策略
        strategy_signals = self._evaluate_strategies(ohlcv, regime_info)

        # 6. 算 cost estimate
        cost_estimate: CostEstimate = estimate_round_trip_cost(slippage_mode="atr")

        return PerceivedContext(
            pair=pair,
            timeframe=timeframe,
            ohlcv=ohlcv,
            regime=regime_info,
            strategy_signals=strategy_signals,
            cost_estimate=cost_estimate,
            data_completeness=data_completeness,
        )

    def _evaluate_strategies(
        self, ohlcv: list[dict], regime_info: RegimeInfo
    ) -> list[StrategyResult]:
        """跑 STRATEGY_INSTANCES 所有策略"""
        if not ohlcv or len(ohlcv) < MIN_CANDLES_FOR_STRATEGY:
            # 数据不足时返回空 list（regime 会标 CHOPPY 已够）
            return []

        # 转 candles 字典格式（strategy_pool 期望的）
        candles_dict = {
            "open": [c.get("o", c.get("open", 0.0)) for c in ohlcv],
            "high": [c.get("h", c.get("high", 0.0)) for c in ohlcv],
            "low": [c.get("l", c.get("low", 0.0)) for c in ohlcv],
            "close": [c.get("c", c.get("close", 0.0)) for c in ohlcv],
        }
        volumes = [c.get("vol", c.get("volume", 1.0)) for c in ohlcv]
        import numpy as np
        volumes_arr = np.array(volumes, dtype=np.float64)

        regime_name = regime_info.regime.value
        results: list[StrategyResult] = []
        for strategy_id, strategy in STRATEGY_INSTANCES.items():
            try:
                result = strategy.evaluate(candles_dict, volumes_arr, regime_name)
                results.append(result)
            except Exception:
                # 单个 strategy 失败不阻塞其他
                # （V1 简化：跳过失败的 strategy；Phase 2 可加 logging + alert）
                continue

        return results