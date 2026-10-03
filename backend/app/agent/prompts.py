"""Prompt 模板 — 中文金融推理（Task 4）

设计：
  - System prompt 设定角色 + 输出 schema + 风格
  - User prompt 喂市场数据（regime + 策略信号 + cost + K线摘要）
  - 强制 JSON 输出（DeepSeek response_format=json_object 配合）

参考 spec: docs/superpowers/specs/2026-10-03-trend-analysis-agent.md §4.1
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

from app.agent.perceiver import PerceivedContext

if TYPE_CHECKING:
    pass


# === System Prompt ===

SYSTEM_PROMPT_TEMPLATE = """你是 ai-trader 项目的"趋势研判 Agent"。你的职责是：

1. **理解** 给定交易对（BTC-USDT 或 ETH-USDT）当前的市场状态
2. **推理** 当前的 regime（bull / bear / choppy / crisis）、置信度（0-1）
3. **解释** 你的判断逻辑（基于 ADX / Hurst / 策略信号 / 成本）
4. **识别** 3-5 条关键观察点
5. **警示** 当前的风险点

**约束**：
- 只分析 BTC-USDT 或 ETH-USDT
- 不下任何交易建议，只做"自然语言研判"
- 客观、基于数据；避免主观臆断
- reasoning 控制在 200-500 字中文

**输出格式**（严格 JSON，不要包含其他文字）：

```json
{{
  "regime": "bull | bear | choppy | crisis",
  "regime_confidence": 0.0,
  "reasoning": "200-500 字中文，解释你的判断",
  "key_observations": ["观察点 1", "观察点 2", "..."],
  "risks": ["风险点 1", "风险点 2", "..."]
}}
```

regime_confidence 范围 [0, 1]，越接近 1 越确信。"""


# === User Prompt ===

def build_user_prompt(ctx: PerceivedContext) -> str:
    """组装 user prompt — 把 PerceivedContext 序列化喂给 LLM"""
    regime = ctx.regime

    # K 线摘要（最近 10 根 + 关键统计）
    ohlcv_summary = _summarize_ohlcv(ctx.ohlcv)

    # 策略信号摘要
    strategy_summary = _summarize_strategies(ctx.strategy_signals)

    # Cost 估算
    cost = ctx.cost_estimate

    data = {
        "pair": ctx.pair,
        "timeframe": ctx.timeframe,
        "data_completeness": ctx.data_completeness,
        "regime_from_signals": {
            "regime": regime.regime.value if hasattr(regime.regime, "value") else str(regime.regime),
            "confidence": regime.confidence,
            "adx": regime.adx,
            "hurst": regime.hurst,
            "description": regime.description,
        },
        "ohlcv_summary": ohlcv_summary,
        "strategy_signals": strategy_summary,
        "cost_estimate": {
            "total_round_trip_pct": cost.total_round_trip_pct,
        },
        "fetched_at": ctx.fetched_at.isoformat(),
    }

    return (
        "请基于以下市场数据，输出研判 JSON：\n\n"
        + json.dumps(data, ensure_ascii=False, indent=2)
    )


def _summarize_ohlcv(ohlcv: list[dict]) -> dict:
    """K 线摘要：最近 5 根 + 关键统计"""
    if not ohlcv:
        return {"candles_count": 0}

    recent = ohlcv[-5:]  # 最近 5 根
    closes = [c.get("c", c.get("close", 0.0)) for c in ohlcv if c.get("c") or c.get("close")]

    summary = {
        "candles_count": len(ohlcv),
        "recent_5_candles": [
            {
                "c": c.get("c", c.get("close")),
                "o": c.get("o", c.get("open")),
                "h": c.get("h", c.get("high")),
                "l": c.get("l", c.get("low")),
                "vol": c.get("vol", c.get("volume")),
            }
            for c in recent
        ],
    }
    if closes:
        summary["close_stats"] = {
            "first": closes[0],
            "last": closes[-1],
            "high": max(closes),
            "low": min(closes),
            "change_pct": (closes[-1] - closes[0]) / closes[0] * 100 if closes[0] else 0,
        }
    return summary


def _summarize_strategies(strategies: list) -> list[dict]:
    """策略信号摘要"""
    return [
        {
            "strategy": s.strategy.value if hasattr(s.strategy, "value") else str(s.strategy),
            "direction": s.direction,
            "confidence": s.confidence,
            "reasons": list(s.reasons) if s.reasons else [],
        }
        for s in strategies
    ]