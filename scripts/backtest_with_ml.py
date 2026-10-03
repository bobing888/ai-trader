#!/usr/bin/env python3
"""
Phase 4: Rule vs ML Comparison Backtest
=====================================
Runs BOTH rule-only baseline AND rule+ML version on the same synthetic data
(same seed) and produces a side-by-side comparison report.

Outputs: reports/bt-rule-vs-ml-{date}.md
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np

from backtest_baseline import (
    generate_synthetic_ohlcv,
    ohlcv_to_candles_dict,
    compute_future_return,
    hit_rate as _hr,
    brier_score as _bs,
    SYMBOLS,
    TIMEFRAMES,
    N_CANDLES,
    SEED,
)
from app.signals.forecast import (
    ForecastModel,
    build_features_for_window,
    FEATURE_NAMES,
    hit_rate,
    brier_score,
    auc_score,
)

HORIZON = 5
MODEL_DIR = Path("backend/data/models")


def _auc(probs: np.ndarray, actual: np.ndarray) -> float:
    """Alias for clarity."""
    return auc_score(probs, actual)


def run_with_ml(
    candles_list: list[dict],
    symbol: str,
    timeframe: str,
    future_ret: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, int]:
    """Run rule+ML aggregation, return (probs_rule, probs_ml, dirs_rule, dirs_ml, n)."""
    from app.signals import RegimeDetector, SignalAggregator, STRATEGY_INSTANCES

    regime_detector = RegimeDetector(timeframe=timeframe)
    aggregator = SignalAggregator()
    warmup = 200

    # Load model if available
    model_path = MODEL_DIR / f"{symbol.replace('-','_')}_{timeframe}.pkl"
    model: ForecastModel | None = None
    if model_path.exists():
        try:
            model = ForecastModel.load(model_path)
            print(f"    Loaded model: {model_path}")
        except Exception as e:
            print(f"    Model load failed {model_path}: {e}")
            model = None

    n = len(candles_list)
    probs_rule = np.full(n, np.nan, dtype=np.float64)
    probs_ml = np.full(n, np.nan, dtype=np.float64)
    dirs_rule = np.full(n, np.nan, dtype=np.float64)
    dirs_ml = np.full(n, np.nan, dtype=np.float64)

    for i in range(warmup, n - HORIZON):
        window = candles_list[max(0, i - 500):i + 1]
        if len(window) < 50:
            continue

        closes_win = np.array([c["close"] for c in window], dtype=np.float64)
        volumes_win = np.array([c["volume"] for c in window], dtype=np.float64)
        highs_win = np.array([c["high"] for c in window], dtype=np.float64)
        lows_win = np.array([c["low"] for c in window], dtype=np.float64)
        log_returns = np.diff(np.log(closes_win + 1e-10), prepend=closes_win[0])

        regime_info = regime_detector.update(
            log_returns, volumes_win, high=highs_win, low=lows_win, close=closes_win
        )

        strategy_results = []
        for sid, strat in STRATEGY_INSTANCES.items():
            cd = {
                "symbol": symbol,
                "timeframe": timeframe,
                "open": [c["open"] for c in window],
                "high": [c["high"] for c in window],
                "low": [c["low"] for c in window],
                "close": [c["close"] for c in window],
            }
            vols = np.array([c["volume"] for c in window], dtype=np.float64)
            result = strat.evaluate(cd, vols, regime_info.regime.value)
            strategy_results.append(result)

        # Rule-only aggregate
        agg_rule = aggregator.aggregate(
            strategy_results=strategy_results,
            regime=regime_info.regime,
            regime_confidence=regime_info.confidence,
            timeframe=timeframe,
            adx=regime_info.adx,
            hurst=regime_info.hurst,
            # No forecast_override → pure rule
        )

        if agg_rule is not None:
            dirs_rule[i] = 1.0 if agg_rule.direction == "long" else -1.0
            probs_rule[i] = agg_rule.confidence

        # ML blend
        ml_prob: float | None = None
        if model is not None:
            try:
                fs = build_features_for_window(window, strategy_results, regime_info.regime_probs, HORIZON)
                feat_arr = fs.to_array().reshape(1, -1)
                ml_prob = float(model.predict_calibrated(feat_arr)[0])
                ml_prob = float(np.clip(ml_prob, 0.0, 1.0))
            except Exception:
                ml_prob = None

        if ml_prob is not None and agg_rule is not None:
            # Blend: 60% rule, 40% ML
            blended = 0.6 * agg_rule.confidence + 0.4 * ml_prob
            dirs_ml[i] = 1.0 if blended >= 0.5 else -1.0
            probs_ml[i] = blended
        elif agg_rule is not None:
            # No ML model → fall back to rule only
            dirs_ml[i] = dirs_rule[i]
            probs_ml[i] = probs_rule[i]

    mask = ~np.isnan(dirs_rule) & ~np.isnan(future_ret[:n])
    return probs_rule, probs_ml, dirs_rule, dirs_ml, int(mask.sum())


def run_comparison() -> list[dict]:
    results: list[dict] = []

    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            print(f"  {symbol} {tf}...", flush=True)
            df = generate_synthetic_ohlcv(symbol, tf, N_CANDLES)
            candles_list = ohlcv_to_candles_dict(df, symbol, tf)
            future_ret = compute_future_return(df, horizon=HORIZON)

            probs_rule, probs_ml, dirs_rule, dirs_ml, n = run_with_ml(
                candles_list, symbol, tf, future_ret
            )

            # Compute metrics on non-null indices
            valid = ~np.isnan(dirs_rule) & ~np.isnan(future_ret[:len(dirs_rule)])
            fr = future_ret[:len(dirs_rule)]

            if valid.sum() == 0:
                print(f"    No valid signals — skipped")
                continue

            hr_rule = _hr(dirs_rule[valid], fr[valid])
            hr_ml = _hr(dirs_ml[valid], fr[valid])
            bs_rule = _bs(probs_rule[valid], (fr[valid] > 0).astype(float))
            bs_ml = _bs(probs_ml[valid], (fr[valid] > 0).astype(float))
            auc_rule = _auc(probs_rule[valid], (fr[valid] > 0).astype(float))
            auc_ml = _auc(probs_ml[valid], (fr[valid] > 0).astype(float))

            delta_hr = hr_ml - hr_rule
            delta_bs = bs_rule - bs_ml   # positive = ML improved
            delta_auc = auc_ml - auc_rule

            results.append({
                "symbol": symbol,
                "timeframe": tf,
                "n_samples": n,
                "hit_rate_rule": round(hr_rule, 4),
                "hit_rate_ml": round(hr_ml, 4),
                "delta_hit_rate": round(delta_hr, 4),
                "brier_rule": round(bs_rule, 4),
                "brier_ml": round(bs_ml, 4),
                "delta_brier": round(delta_bs, 4),
                "auc_rule": round(auc_rule, 4),
                "auc_ml": round(auc_ml, 4),
                "delta_auc": round(delta_auc, 4),
                "ml_helped": delta_hr > 0 or delta_bs > 0,
            })

            verdict = "✅ ML HELPED" if (delta_hr > 0 or delta_bs > 0) else "⚠️ ML NOT HELPFUL"
            print(f"    rule: hr={hr_rule:.3f} bs={bs_rule:.4f} auc={auc_rule:.3f}  "
                  f"ml: hr={hr_ml:.3f} bs={bs_ml:.4f} auc={auc_ml:.3f}  "
                  f"Δhr={delta_hr:+.3f} Δbs={delta_bs:+.4f}  {verdict}", flush=True)

    return results


def write_report(results: list[dict]) -> Path:
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report_path = Path(f"reports/bt-rule-vs-ml-{date_str}.md")
    report_path.parent.mkdir(exist_ok=True)

    with open(report_path, "w") as f:
        f.write(f"# Rule vs ML Backtest Report\n")
        f.write(f"Generated: {datetime.now(timezone.utc).isoformat()} UTC\n")
        f.write(f"Seed: {SEED} | Horizon: {HORIZON} | Candles: {N_CANDLES}\n")
        f.write(f"Blend weights: rule=0.6, ML=0.4\n\n")

        f.write("## Side-by-Side Results\n\n")
        f.write("| Symbol | TF | N | HR Rule | HR ML | ΔHR | Brier Rule | Brier ML | ΔBrier | AUC Rule | AUC ML | ΔAUC | ML Helped |\n")  # noqa: E501
        f.write("|--------|----|---|---------|-------|-----|------------|----------|--------|---------|-------|------|----------|\n")  # noqa: E501
        for r in results:
            helped = "✅" if r["ml_helped"] else "⚠️"
            f.write(f"| {r['symbol']} | {r['timeframe']} | {r['n_samples']} "
                     f"| {r['hit_rate_rule']:.1%} | {r['hit_rate_ml']:.1%} | {r['delta_hit_rate']:+.1%} "
                     f"| {r['brier_rule']:.4f} | {r['brier_ml']:.4f} | {r['delta_brier']:+.4f} "
                     f"| {r['auc_rule']:.3f} | {r['auc_ml']:.3f} | {r['delta_auc']:+.3f} | {helped} |\n")

        if results:
            avg_hr_rule = np.mean([r["hit_rate_rule"] for r in results])
            avg_hr_ml = np.mean([r["hit_rate_ml"] for r in results])
            avg_bs_rule = np.mean([r["brier_rule"] for r in results])
            avg_bs_ml = np.mean([r["brier_ml"] for r in results])
            avg_auc_rule = np.mean([r["auc_rule"] for r in results])
            avg_auc_ml = np.mean([r["auc_ml"] for r in results])
            avg_delta_hr = np.mean([r["delta_hit_rate"] for r in results])
            avg_delta_bs = np.mean([r["delta_brier"] for r in results])
            avg_delta_auc = np.mean([r["delta_auc"] for r in results])
            n_helped = sum(1 for r in results if r["ml_helped"])
            n_total = len(results)

            f.write("\n## Aggregate Summary\n\n")
            f.write(f"| Metric | Rule | ML | Delta |\n")
            f.write(f"|--------|------|----|-------|\n")
            f.write(f"| Hit Rate | {avg_hr_rule:.1%} | {avg_hr_ml:.1%} | {avg_delta_hr:+.1%} |\n")
            f.write(f"| Brier Score | {avg_bs_rule:.4f} | {avg_bs_ml:.4f} | {avg_delta_bs:+.4f} |\n")
            f.write(f"| AUC | {avg_auc_rule:.3f} | {avg_auc_ml:.3f} | {avg_delta_auc:+.3f} |\n")
            f.write(f"| ML Helped | — | {n_helped}/{n_total} symbols | |\n")

            overall_helped = avg_delta_hr > 0 and avg_delta_bs > 0
            verdict = "✅ **ML IMPROVED SIGNAL QUALITY**" if overall_helped else "⚠️ **ML DID NOT IMPROVE — see analysis**"
            f.write(f"\n## Verdict\n\n{verdict}\n\n")
            f.write(f"- avg Δhit_rate = {avg_delta_hr:+.1%}\n")
            f.write(f"- avg Δbrier = {avg_delta_bs:+.4f} (positive = ML reduced Brier = better calibration)\n")
            f.write(f"- avg Δauc = {avg_delta_auc:+.3f}\n")
            if not overall_helped:
                f.write("\n**Analysis**: ML did not outperform rule-only on synthetic-realistic data.\n")
                f.write("Possible reasons: (a) GBM synthetic data lacks real market microstructure,\n")
                f.write("(b) strategy signals already capture most predictable patterns,\n")
                f.write("(c) LightGBM features insufficient for short-horizon prediction.\n")

    return report_path


if __name__ == "__main__":
    print("=== Phase 4: Rule vs ML Comparison ===")
    results = run_comparison()
    if results:
        path = write_report(results)
        print(f"\nReport written to {path}")
        helped = sum(1 for r in results if r["ml_helped"])
        print(f"ML helped: {helped}/{len(results)} symbol/timeframe combinations")
    else:
        print("\nNo results — check errors above.")
