#!/usr/bin/env python3
"""
Phase 2: Train ML Forecast Models
==================================
Walk-forward train/val/test on synthetic-realistic OHLCV.
Re-uses the synthetic data generator from backtest_baseline.py (same seed for
reproducibility).

Outputs: trained models at backend/data/models/{symbol}_{tf}.pkl
Report: reports/bt-train-{date}.md with per-split metrics.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
import pandas as pd

from backtest_baseline import (
    generate_synthetic_ohlcv,
    ohlcv_to_candles_dict,
    BASE_PRICES,
    N_CANDLES,
    SEED,
)
from app.signals.forecast import (
    FEATURE_NAMES,
    build_features_for_window,
    train_forecast_model,
    brier_score,
    auc_score,
    hit_rate,
    ForecastModel,
)

SYMBOLS = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]
TIMEFRAMES = ["1h", "4h", "1d"]
HORIZON = 5   # predict direction 5 bars ahead

MODEL_DIR = Path("backend/data/models")
MODEL_DIR.mkdir(parents=True, exist_ok=True)


def compute_label(future_ret: float) -> int:
    """1 = price went up (long win), 0 = price went down (short win)."""
    return 1 if future_ret > 0 else 0


def extract_dataset(
    symbol: str,
    timeframe: str,
) -> tuple[list[np.ndarray], list[int]]:
    """Extract (features, labels) from synthetic OHLCV."""
    df = generate_synthetic_ohlcv(symbol, timeframe, N_CANDLES)
    candles_list = ohlcv_to_candles_dict(df, symbol, timeframe)

    from app.signals import RegimeDetector, SignalAggregator, STRATEGY_INSTANCES

    regime_detector = RegimeDetector(timeframe=timeframe)
    aggregator = SignalAggregator()
    warmup = 200

    features_list: list[np.ndarray] = []
    labels: list[int] = []
    closes = df["close"].values

    for i in range(warmup, len(candles_list) - HORIZON):
        window = candles_list[max(0, i - 500):i + 1]
        if len(window) < 50:
            continue

        closes_win = np.array([c["close"] for c in window], dtype=np.float64)
        volumes_win = np.array([c["volume"] for c in window], dtype=np.float64)
        highs_win = np.array([c["high"] for c in window], dtype=np.float64)
        lows_win = np.array([c["low"] for c in window], dtype=np.float64)
        log_returns = np.diff(np.log(closes_win + 1e-10), prepend=closes_win[0])

        regime_info = regime_detector.update(log_returns, volumes_win, high=highs_win, low=lows_win, close=closes_win)

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

        # Label: did price go up in next HORIZON bars?
        future_ret_label = np.log(closes[i + HORIZON] / closes[i]) if i + HORIZON < len(closes) else 0.0
        label = compute_label(future_ret_label)

        try:
            fs = build_features_for_window(window, strategy_results, regime_info.regime_probs, HORIZON)
            features_list.append(fs.to_array())
            labels.append(label)
        except Exception as e:
            if i < warmup + 5:
                print(f"    sample {i} feature build failed: {e}", flush=True)
            continue

    return features_list, labels


def walk_forward_split(
    features_list: list[np.ndarray],
    labels: list[int],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """60% train / 15% val / 25% test — NO look-ahead."""
    n = len(features_list)
    train_end = int(n * 0.60)
    val_end = int(n * 0.75)

    X = np.array(features_list)
    y = np.array(labels)

    X_train, y_train = X[:train_end], y[:train_end]
    X_val, y_val = X[train_end:val_end], y[train_end:val_end]
    X_test, y_test = X[val_end:], y[val_end:]

    return X_train, y_train, X_val, y_val, X_test, y_test


def run_training() -> dict:
    """Train all models and return results dict."""
    all_results: list[dict] = []

    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            print(f"  Training {symbol} {tf}...", flush=True)
            try:
                features_list, labels = extract_dataset(symbol, tf)
                if len(features_list) < 200:
                    print(f"    Skipped — only {len(features_list)} samples", flush=True)
                    continue

                X_train, y_train, X_val, y_val, X_test, y_test = walk_forward_split(features_list, labels)

                model, monotonic = train_forecast_model(
                    X_train, y_train, X_val, y_val,
                    symbol=symbol, timeframe=tf, horizon=HORIZON,
                )

                # Metrics
                raw_test = model.predict_raw(X_test)
                cal_test = model.predict_calibrated(X_test)

                bs_raw = brier_score(raw_test, y_test.astype(float))
                bs_cal = brier_score(cal_test, y_test.astype(float))
                auc_raw = auc_score(raw_test, y_test.astype(float))
                auc_cal = auc_score(cal_test, y_test.astype(float))
                hr_raw = hit_rate(raw_test, y_test.astype(float))
                hr_cal = hit_rate(cal_test, y_test.astype(float))

                # Save
                model_path = MODEL_DIR / f"{symbol.replace('-','_')}_{tf}.pkl"
                model.save(model_path)

                all_results.append({
                    "symbol": symbol,
                    "timeframe": tf,
                    "n_train": len(X_train),
                    "n_val": len(X_val),
                    "n_test": len(X_test),
                    "auc_raw": round(auc_raw, 4),
                    "auc_cal": round(auc_cal, 4),
                    "bs_raw": round(bs_raw, 4),
                    "bs_cal": round(bs_cal, 4),
                    "hr_raw": round(hr_raw, 4),
                    "hr_cal": round(hr_cal, 4),
                    "cal_monotonic": monotonic,
                    "model_path": str(model_path),
                })

                print(f"    train={len(X_train)} val={len(X_val)} test={len(X_test)} "
                      f"hr={hr_cal:.3f} brier={bs_cal:.4f} auc={auc_cal:.3f}", flush=True)

            except Exception as e:
                print(f"    ERROR training {symbol} {tf}: {e}", flush=True)
                import traceback
                traceback.print_exc()

    return all_results


def write_report(results: list[dict]) -> Path:
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report_path = Path(f"reports/bt-train-{date_str}.md")
    report_path.parent.mkdir(exist_ok=True)

    with open(report_path, "w") as f:
        f.write(f"# ML Forecast Training Report\n")
        f.write(f"Generated: {datetime.now(timezone.utc).isoformat()} UTC\n")
        f.write(f"Seed: {SEED} | Horizon: {HORIZON} bars | Split: 60/15/25\n\n")

        f.write("## Per-Model Results\n\n")
        f.write("| Symbol | TF | Train | Val | Test | AUC raw | AUC cal | "
                 "Brier raw | Brier cal | HR raw | HR cal | Monotonic |\n")
        f.write("|--------|----|-------|-----|------|---------|---------|"
                 "-----------|-----------|--------|--------|-----------|\n")
        for r in results:
            f.write(f"| {r['symbol']} | {r['timeframe']} | {r['n_train']} | {r['n_val']} | "
                     f"{r['n_test']} | {r['auc_raw']:.3f} | {r['auc_cal']:.3f} | "
                     f"{r['bs_raw']:.4f} | {r['bs_cal']:.4f} | "
                     f"{r['hr_raw']:.1%} | {r['hr_cal']:.1%} | {'✅' if r['cal_monotonic'] else '❌'} |\n")

        if results:
            avg_auc = np.mean([r["auc_cal"] for r in results])
            avg_bs = np.mean([r["bs_cal"] for r in results])
            avg_hr = np.mean([r["hr_cal"] for r in results])
            f.write(f"\n**Overall — AUC: {avg_auc:.3f} | Brier: {avg_bs:.4f} | Hit Rate: {avg_hr:.1%}**\n")

    return report_path


if __name__ == "__main__":
    print("=== Phase 2: ML Forecast Training ===")
    print(f"Symbols: {SYMBOLS} | Timeframes: {TIMEFRAMES} | Horizon: {HORIZON}")
    results = run_training()
    if results:
        path = write_report(results)
        print(f"\nTraining report: {path}")
    else:
        print("\nNo models trained — check errors above.")
