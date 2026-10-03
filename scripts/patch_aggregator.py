#!/usr/bin/env python3
"""
Phase 3: Modify SignalAggregator to Accept ML Forecast Override
================================================================
Adds optional `forecast_override` parameter to aggregate().
When provided (a calibrated probability 0-1), blends with affinity-weighted
confidence: final_conf = rule_weight * rule_conf + ml_weight * forecast_override
where rule_weight=0.6, ml_weight=0.4 initially.

DOES NOT remove any existing logic — only ADDS the ML blend as additive path.
"""

import re

with open("backend/app/signals/aggregator.py", "r") as f:
    content = f.read()

# ── Step 1: Add forecast_override parameter to aggregate() ────────────────────

# Update the aggregate method signature
OLD_SIG = """    def aggregate(
        self,
        strategy_results: list[StrategyResult],
        regime: Regime,
        regime_confidence: float,
        timeframe: str = "1h",
        candles_dict: dict[str, list[dict]] | None = None,
        current_price: float | None = None,
        adx: float | None = None,
        hurst: float | None = None,
    ) -> Optional[AggregatedSignal]:"""

NEW_SIG = """    def aggregate(
        self,
        strategy_results: list[StrategyResult],
        regime: Regime,
        regime_confidence: float,
        timeframe: str = "1h",
        candles_dict: dict[str, list[dict]] | None = None,
        current_price: float | None = None,
        adx: float | None = None,
        hurst: float | None = None,
        forecast_override: float | None = None,
        ml_weight: float = 0.4,
    ) -> Optional[AggregatedSignal]:"""

content = content.replace(OLD_SIG, NEW_SIG)

# ── Step 2: Update docstring ──────────────────────────────────────────────────

OLD_DOC = """        \"\"\"
        聚合策略信号（v2）。

        candles_dict: {pair: candles}  — 用于 ATR / D1 execution levels
        current_price: 现价 dict（key=pair），None 时跳过 D1 计算
        adx / hurst: 透传给 _dynamic_min_agreement — 强趋势时放宽到 1
        \"\"\""""

NEW_DOC = """        \"\"\"
        聚合策略信号（v2）。

        candles_dict: {pair: candles}  — 用于 ATR / D1 execution levels
        current_price: 现价 dict（key=pair），None 时跳过 D1 计算
        adx / hurst: 透传给 _dynamic_min_agreement — 强趋势时放宽到 1
        forecast_override: optional ML-calibrated probability (0-1). When provided,
            blends with affinity-weighted rule confidence: final = (1-ml_weight)*rule
            + ml_weight*forecast_override. Default ml_weight=0.4 (rule=0.6).
        \"\"\""""

content = content.replace(OLD_DOC, NEW_DOC)

# ── Step 3: Add ML blend logic after final_confidence computation ──────────────
# Find the line that sets final_confidence and add ML blend after it

OLD_CONF_BLOCK = """        # Regime 置信度加权
        regime_weight = 0.5 + 0.5 * regime_confidence
        # v2: 略放宽，避免低置信度 regime 把所有信号压成 0
        final_confidence = min(1.0, avg_confidence * regime_weight + 0.10 * regime_confidence)"""

NEW_CONF_BLOCK = """        # Regime 置信度加权
        regime_weight = 0.5 + 0.5 * regime_confidence
        # v2: 略放宽，避免低置信度 regime 把所有信号压成 0
        final_confidence = min(1.0, avg_confidence * regime_weight + 0.10 * regime_confidence)

        # Phase 3: ML forecast blend (additive — never removes rule-based logic)
        # When forecast_override is provided, blend with rule confidence
        # ml_weight=0.4 means 40% ML, 60% rule; user can override
        if forecast_override is not None and 0.0 <= forecast_override <= 1.0:
            ml_w = float(ml_weight)
            rule_w = 1.0 - ml_w
            final_confidence = min(1.0, rule_w * final_confidence + ml_w * forecast_override)"""

content = content.replace(OLD_CONF_BLOCK, NEW_CONF_BLOCK)

# ── Step 4: Add forecast_override field to AggregatedSignal dataclass ──────────

OLD_DS_FIELDS = """    # D3: trailing + partial TP
    trailing_stop_enabled: bool = True
    partial_tp_enabled: bool = True"""

NEW_DS_FIELDS = """    # D3: trailing + partial TP
    trailing_stop_enabled: bool = True
    partial_tp_enabled: bool = True
    # Phase 3: ML forecast blend
    forecast_override: float | None = None   # raw ML probability (if used)
    ml_weight_used: float = 0.4             # weight given to ML in final_confidence"""

content = content.replace(OLD_DS_FIELDS, NEW_DS_FIELDS)

# ── Step 5: Add fields to AggregatedSignal construction ───────────────────────

OLD_RETURN = """            quality=quality_result["quality"],
            quality_reasons=quality_result["reasons"],
        )"""

NEW_RETURN = """            quality=quality_result["quality"],
            quality_reasons=quality_result["reasons"],
            forecast_override=forecast_override,
            ml_weight_used=ml_weight if forecast_override is not None else 0.4,
        )"""

content = content.replace(OLD_RETURN, NEW_RETURN)

# Write modified content
with open("backend/app/signals/aggregator.py", "w") as f:
    f.write(content)

print("aggregator.py patched successfully.")
print("  - aggregate() signature: added forecast_override + ml_weight parameters")
print("  - AggregatedSignal dataclass: added forecast_override + ml_weight_used fields")
print("  - ML blend logic: additive path, (1-ml_weight)*rule + ml_weight*forecast_override")
