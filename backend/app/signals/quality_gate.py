"""Signal Quality Gate (D2).

Categorizes a signal as high/medium/low/reject based on:
  - calibrated_confidence (PAVA Isotonic per-tf)
  - net_pnl_estimate (cost-aware expected PnL)
  - regime (BULL/BEAR/CHOPPY/CRISIS)

Reference:
  - QuantConnect Lean: signal scoring with regime filter
  - jesse-ai/jesse: signal confidence * edge — cost
  - Hephyrius/binance_futures_bot: regime multiplier
"""

from __future__ import annotations


# --------------------------------------------------------------------------
# Thresholds (tunable; conservative defaults aligned with v2 calibrator)
# --------------------------------------------------------------------------

DEFAULT_THRESHOLDS: dict[str, dict[str, float]] = {
    "BULL": {"min_conf": 0.55, "min_net_pnl": 0.001},
    "BEAR": {"min_conf": 0.55, "min_net_pnl": 0.001},
    "CHOPPY": {"min_conf": 0.60, "min_net_pnl": 0.002},
    "CRISIS": {"min_conf": 0.70, "min_net_pnl": 0.005},
}


def compute_quality_thresholds(regime: str) -> dict[str, float]:
    """返回给定 regime 的最小 conf + net_pnl 阈值。"""
    return DEFAULT_THRESHOLDS.get(regime.upper(), DEFAULT_THRESHOLDS["CHOPPY"])


def evaluate_signal_quality(
    calibrated_confidence: float | None,
    net_pnl_estimate: float,
    regime: str,
) -> dict:
    """Evaluate signal credibility.

    Returns:
        {
            "quality": "high" | "medium" | "low" | "reject",
            "reasons": [str, ...],
            "reject": bool,
        }
    """
    reasons: list[str] = []
    thresholds = compute_quality_thresholds(regime)

    # 1. cold start → medium (PASAVA not yet calibrated)
    if calibrated_confidence is None:
        reasons.append("Calibrator 冷启动 → 信号胜率未校准")
        return {"quality": "medium", "reasons": reasons, "reject": False}

    # 2. regime hard rules
    if regime.upper() == "CRISIS":
        reasons.append("CRISIS regime → 强制降低信号质量")

    # 3. check calibrated_conf
    min_conf = thresholds["min_conf"]
    conf_ok = calibrated_confidence >= min_conf
    if not conf_ok:
        reasons.append(
            f"calibrated_confidence={calibrated_confidence:.2f} < threshold {min_conf:.2f}"
        )

    # 4. check net_pnl (must be positive to cover costs)
    min_net_pnl = thresholds["min_net_pnl"]
    net_pnl_ok = net_pnl_estimate >= min_net_pnl
    if not net_pnl_ok:
        reasons.append(
            f"net_pnl_estimate={net_pnl_estimate:.4f} < threshold {min_net_pnl:.4f}"
        )

    # 5. categorize
    # CRISIS 永远不达到 high；CRISIS 下 0.85 以下视为 reject
    if regime.upper() == "CRISIS":
        if calibrated_confidence < 0.85:
            reasons.append("CRISIS 下置信度不足 0.85 → reject")
            return {"quality": "reject", "reasons": reasons, "reject": True}
        # 0.85~1.0 之间 → low (谨慎)
        reasons.append("CRISIS regime → 信号最高只能达到 low")
        return {"quality": "low", "reasons": reasons, "reject": False}

    reject = (not conf_ok) or (not net_pnl_ok)
    if reject:
        return {"quality": "reject", "reasons": reasons, "reject": True}

    # Determine high vs medium
    # Use explicit literal thresholds to avoid float precision drift
    if regime.upper() == "CRISIS":
        high_conf_threshold = 0.85
        high_net_pnl_threshold = 0.015
    elif regime.upper() == "CHOPPY":
        high_conf_threshold = 0.75
        high_net_pnl_threshold = 0.010
    else:  # BULL/BEAR
        high_conf_threshold = 0.70
        high_net_pnl_threshold = 0.006

    if calibrated_confidence >= high_conf_threshold and net_pnl_estimate >= high_net_pnl_threshold:
        reasons.append(
            f"calibrated_confidence={calibrated_confidence:.2f} ≥ high threshold {high_conf_threshold:.2f}"
        )
        reasons.append(
            f"net_pnl_estimate={net_pnl_estimate:.4f} ≥ high threshold {high_net_pnl_threshold:.4f}"
        )
        return {"quality": "high", "reasons": reasons, "reject": False}

    return {"quality": "medium", "reasons": reasons, "reject": False}