"""Signal Quality Gate (D2).

Categorizes a signal as high/medium/low/reject based on:
  - calibrated_confidence (PAVA Isotonic per-tf)
  - net_pnl_estimate (cost-aware expected PnL)
  - regime (BULL/BEAR/CHOPPY/CRISIS)

UHF (P3_uhf) tier goes through 6 additional hard gates (spec §3.D):
  1. funding_rate abs ≤ 0.01% / 8h (0.0001)
  2. volume_24h_usdt ≥ 1B USDT
  3. oi_24h_change ≥ -5% (-0.05)
  4. spread ≤ 0.05% (0.0005)
  5. 100x must be delta_neutral=True
  6. equity_drawdown ≤ 5% (0.05) — pause if exceeded

Reference:
  - QuantConnect Lean: signal scoring with regime filter
  - jesse-ai/jesse: signal confidence * edge — cost
  - Hephyrius/binance_futures_bot: regime multiplier
  - godzilla-foundation/godzilla-community: funding rate arbitrage delta-neutral 100x
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


# --------------------------------------------------------------------------
# Thresholds (tunable; conservative defaults aligned with v2 calibrator)
# --------------------------------------------------------------------------

DEFAULT_THRESHOLDS: dict[str, dict[str, float]] = {
    "BULL": {"min_conf": 0.55, "min_net_pnl": 0.001},
    "BEAR": {"min_conf": 0.55, "min_net_pnl": 0.001},
    "CHOPPY": {"min_conf": 0.60, "min_net_pnl": 0.002},
    "CRISIS": {"min_conf": 0.70, "min_net_pnl": 0.005},
}

# UHF (P3_uhf) 6 hard gates — spec §3.D
UHF_MAX_FUNDING_RATE_ABS: float = 0.0001       # 0.01% / 8h
UHF_MIN_VOLUME_24H_USDT: float = 1e9          # 1B USDT
UHF_MIN_OI_24H_CHANGE: float = -0.05          # -5% (reject if below)
UHF_MAX_SPREAD: float = 0.0005                 # 0.05%


@dataclass
class GateResult:
    passed: bool
    reasons: list[str]


def compute_quality_thresholds(regime: str) -> dict[str, float]:
    """返回给定 regime 的最小 conf + net_pnl 阈值。"""
    return DEFAULT_THRESHOLDS.get(regime.upper(), DEFAULT_THRESHOLDS["CHOPPY"])


def gate(
    signal: dict,
    market: dict | None,
) -> GateResult:
    """UHF (P3_uhf) 6 hard gates + passthrough for other tiers.

    Spec §3.D gates (only for horizon_tier == "P3_uhf"):
      1. funding_rate abs ≤ 0.0001 (0.01%/8h)
      2. volume_24h_usdt ≥ 1e9 USDT
      3. oi_24h_change ≥ -0.05
      4. spread ≤ 0.0005 (0.05%)
      5. 100x leverage → delta_neutral=True required
      6. equity_drawdown ≤ 0.05 (5%) — pause if exceeded

    For non-UHF tiers: delegates to evaluate_signal_quality if calibrated fields present.

    Args:
        signal: dict with keys like horizon_tier, leverage, delta_neutral,
                calibrated_confidence, net_pnl_estimate, regime
        market: dict with funding_rate, volume_24h_usdt, oi_24h_change,
                spread, equity_drawdown (None for non-UHF tiers)

    Returns:
        GateResult(passed: bool, reasons: list[str])
    """
    reasons: list[str] = []
    horizon_tier = str(signal.get("horizon_tier", "")).lower()

    # ── UHF (P3_uhf) strict 6-gate path ──────────────────────────────────────
    if horizon_tier == "p3_uhf":
        if market is None:
            reasons.append("P3_uhf requires market data but market=None")
            return GateResult(passed=False, reasons=reasons)

        # Gate 1: funding_rate abs ≤ 0.0001
        fr = market.get("funding_rate")
        if fr is None:
            reasons.append("funding_rate_missing (gate 1)")
        elif abs(fr) > UHF_MAX_FUNDING_RATE_ABS:
            reasons.append(f"funding_rate_abs={abs(fr):.5f} > {UHF_MAX_FUNDING_RATE_ABS} (gate 1)")

        # Gate 2: volume_24h_usdt ≥ 1B
        vol = market.get("volume_24h_usdt")
        if vol is None:
            reasons.append("volume_24h_usdt_missing (gate 2)")
        elif vol < UHF_MIN_VOLUME_24H_USDT:
            reasons.append(f"volume_24h_usdt={vol:.0f} < {UHF_MIN_VOLUME_24H_USDT:.0f} (gate 2)")

        # Gate 3: oi_24h_change ≥ -0.05
        oi_change = market.get("oi_24h_change")
        if oi_change is None:
            reasons.append("oi_24h_change_missing (gate 3)")
        elif oi_change < UHF_MIN_OI_24H_CHANGE:
            reasons.append(f"oi_24h_change={oi_change:.3f} < {UHF_MIN_OI_24H_CHANGE} (gate 3: 多空双爆)")

        # Gate 4: spread ≤ 0.0005
        spread = market.get("spread")
        if spread is None:
            reasons.append("spread_missing (gate 4)")
        elif spread > UHF_MAX_SPREAD:
            reasons.append(f"spread={spread:.5f} > {UHF_MAX_SPREAD} (gate 4)")

        # Gate 5: 100x → delta_neutral=True
        leverage = signal.get("leverage")
        delta_neutral = signal.get("delta_neutral", False)
        if leverage and leverage >= 100 and not delta_neutral:
            reasons.append("100x without delta_neutral=True (gate 5)")

        # Gate 6: equity_drawdown ≤ 0.05
        drawdown = market.get("equity_drawdown")
        if drawdown is not None and drawdown > 0.05:
            reasons.append(f"equity_drawdown={drawdown:.3f} > 0.05 — paper paused (gate 6)")

        passed = len(reasons) == 0
        return GateResult(passed=passed, reasons=reasons)

    # ── Non-UHF tiers: passthrough (delegate to existing evaluate_signal_quality) ─
    calibrated_confidence = signal.get("calibrated_confidence")
    net_pnl_estimate = signal.get("net_pnl_estimate", 0.0)
    regime = signal.get("regime", "CHOPPY")

    # Delegate to existing quality evaluator
    result = evaluate_signal_quality(calibrated_confidence, net_pnl_estimate, regime)
    return GateResult(
        passed=not result["reject"],
        reasons=result["reasons"],
    )


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