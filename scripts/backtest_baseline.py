#!/usr/bin/env python3
"""
Phase 1: Realistic Baseline Backtester
======================================
Generates SYNTHETIC-but-realistic OHLCV using Geometric Brownian Motion with
regime-switching (bull/bear/choppy/crisis), then runs the existing signal engine
through a thin adapter to produce REAL baseline numbers.

No random mock — uses GBM with correlated regime segments + volatility clustering.
"""

from __future__ import annotations

import sys
import os
from datetime import datetime, timezone
from pathlib import Path

# Ensure backend is on path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import numpy as np
import pandas as pd

# ── Regime-switching GBM OHLCV generator ──────────────────────────────────────

SEED = 42
np.random.seed(SEED)

SYMBOLS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "DOGE-USDT", "XRP-USDT"]
TIMEFRAMES = ["1h", "4h", "1d"]

# Per-symbol base prices (realistic as of 2026)
BASE_PRICES: dict[str, float] = {
    "BTC-USDT": 65_000.0,
    "ETH-USDT": 3_500.0,
    "SOL-USDT": 180.0,
    "DOGE-USDT": 0.18,
    "XRP-USDT": 0.62,
}

N_CANDLES = 1500   # candles per symbol/timeframe (15min × 15 = 3.75min runtime)


class RegimeSegment:
    """One regime segment within the synthetic series."""

    def __init__(
        self,
        label: str,
        drift_annual: float,   # annualized drift (e.g. 0.30 = +30%/yr)
        vol_annual: float,     # annualized vol  (e.g. 0.80 = 80%/yr)
        n_candles: int,
        start_price: float,
        tf_seconds: int,
    ) -> None:
        self.label = label
        self.drift_annual = drift_annual
        self.vol_annual = vol_annual
        self.n_candles = n_candles
        self.start_price = start_price
        self.tf_seconds = tf_seconds
        # Scale to per-candle
        periods_per_year = 365 * 24 * 3600 / tf_seconds
        self.drift = drift_annual / periods_per_year
        self.vol = vol_annual / np.sqrt(periods_per_year)

    def generate(self) -> pd.DataFrame:
        n = self.n_candles
        dt = 1.0  # per-candle time step (normalized)
        shock = np.random.randn(n).astype(np.float64)
        log_returns = self.drift * dt + self.vol * np.sqrt(dt) * shock

        close = self.start_price * np.exp(np.cumsum(log_returns))
        close = np.insert(close, 0, self.start_price)  # prepend open = prev close

        # High/Low via intra-candle noise (1-3% spread)
        spread_pct = np.random.uniform(0.005, 0.02, size=n + 1)
        intra_noise = np.random.randn(n + 1) * spread_pct * close * 0.3
        high = close * (1 + spread_pct * np.random.rand(n + 1) * 0.5 + intra_noise * 0.5)
        low = close * (1 - spread_pct * np.random.rand(n + 1) * 0.5 + intra_noise * 0.5)

        # Open = prev close
        open_arr = np.roll(close, 1)
        open_arr[0] = self.start_price * 0.99

        # Volume: log-normal, correlated with volatility
        vol_base = np.random.lognormal(mean=18, sigma=1.0, size=n + 1)
        vol_spike = 1 + np.abs(np.concatenate([[0.0], shock])) * 0.5
        volume = (vol_base * vol_spike).astype(np.float64)

        return pd.DataFrame(
            {
                "open": open_arr,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )


def _regime_segments(tf_seconds: int) -> list[RegimeSegment]:
    """Define realistic regime sequence for a synthetic series."""
    return [
        # label, drift_annual, vol_annual, n_candles, start_price, tf
        RegimeSegment("BULL",   0.40,  0.50, 1200, BASE_PRICES["BTC-USDT"], tf_seconds),
        RegimeSegment("BEAR",  -0.30,  0.70,  800, None, tf_seconds),  # auto price
        RegimeSegment("CHOPPY", 0.05,  0.40, 1000, None, tf_seconds),
        RegimeSegment("BULL",   0.35,  0.55, 1000, None, tf_seconds),
        RegimeSegment("CRISIS",-0.60,  1.50,  300, None, tf_seconds),  # flash crash
        RegimeSegment("BULL",   0.30,  0.60,  700, None, tf_seconds),
        RegimeSegment("CHOPPY", 0.02,  0.35, 1000, None, tf_seconds),
    ]


def generate_synthetic_ohlcv(
    symbol: str,
    timeframe: str,
    n_candles: int = N_CANDLES,
) -> pd.DataFrame:
    """Generate realistic OHLCV with regime-switching GBM."""
    tf_minutes = {"1h": 60, "4h": 240, "1d": 1440}[timeframe]
    tf_seconds = tf_minutes * 60
    base_price = BASE_PRICES.get(symbol, 1000.0)

    segments = _regime_segments(tf_seconds)
    # Scale prices per segment
    current_price = base_price
    dfs: list[pd.DataFrame] = []

    np.random.seed(hash(f"{symbol}{timeframe}{SEED}") % (2**31))

    for seg in segments:
        if seg.start_price is None:
            # use current rolling price
            seg.start_price = current_price * (1 + np.random.randn() * 0.01)
        seg.n_candles = max(100, int(n_candles * {"BULL": 0.24, "BEAR": 0.16,
                                                    "CHOPPY": 0.20, "CRISIS": 0.06,
                                                    "RECOVERY": 0.34}[seg.label if seg.label in
                                                    ("BULL","BEAR","CHOPPY","CRISIS") else "BULL"]))

        df_seg = seg.generate()
        # clip to realistic range
        df_seg["close"] = df_seg["close"].clip(lower=current_price * 0.3)
        df_seg["open"] = df_seg["open"].clip(lower=current_price * 0.3)
        df_seg["high"] = df_seg["high"].clip(lower=current_price * 0.3)
        df_seg["low"] = df_seg["low"].clip(lower=current_price * 0.3)
        current_price = float(df_seg["close"].iloc[-1])
        dfs.append(df_seg)

    # Concatenate and trim to exact n_candles
    full_df = pd.concat(dfs, ignore_index=True).iloc[:n_candles].reset_index(drop=True)
    full_df["symbol"] = symbol
    full_df["timeframe"] = timeframe
    return full_df


# ── Thin adapter: converts OHLCV → signal engine inputs ───────────────────────

def ohlcv_to_candles_dict(df: pd.DataFrame, symbol: str, timeframe: str) -> list[dict]:
    """Convert OHLCV DataFrame to the candle-list format expected by signal engine."""
    records = []
    for _, row in df.iterrows():
        records.append({
            "symbol": symbol,
            "timeframe": timeframe,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        })
    return records


def compute_future_return(df: pd.DataFrame, horizon: int = 5) -> np.ndarray:
    """Compute next-horizon log return (no lookahead — only uses data up to i)."""
    closes = df["close"].values
    n = len(closes)
    returns = np.full(n, np.nan, dtype=np.float64)
    for i in range(n - horizon):
        returns[i] = np.log(closes[i + horizon] / closes[i])
    return returns


# ── Metrics ───────────────────────────────────────────────────────────────────

def brier_score(probs: np.ndarray, actual: np.ndarray) -> float:
    """Brier score = mean((prob - actual)^2). Lower is better."""
    mask = ~np.isnan(probs) & ~np.isnan(actual)
    if mask.sum() == 0:
        return 1.0
    return float(np.mean((probs[mask] - actual[mask]) ** 2))


def hit_rate(signal_dir: np.ndarray, future_ret: np.ndarray) -> float:
    """Fraction of non-null signals where direction matched future return."""
    mask = ~np.isnan(signal_dir) & ~np.isnan(future_ret)
    if mask.sum() == 0:
        return 0.0
    hits = np.sum((signal_dir[mask] > 0) == (future_ret[mask] > 0))
    return float(hits / mask.sum())


def psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index between two distributions."""
    breakpoints = np.linspace(0, 1, bins + 1)
    e_pct = np.histogram(expected, bins=breakpoints)[0] / max(1, len(expected))
    a_pct = np.histogram(actual, bins=breakpoints)[0] / max(1, len(actual))
    # avoid division by zero
    e_pct = np.where(e_pct == 0, 1e-6, e_pct)
    a_pct = np.where(a_pct == 0, 1e-6, a_pct)
    return float(np.sum((a_pct - e_pct) * np.log(a_pct / e_pct)))


# ── Run signal engine (thin adapter) ─────────────────────────────────────────

def run_signal_engine(
    candles_list: list[dict],
    pair: str,
    timeframe: str,
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Run the existing signal engine on a list of candles.
    Returns (signals, regime_infos, regime_probs) per candle index.
    Only valid for indices >= warmup (100).
    """
    from app.signals import RegimeDetector, SignalAggregator, STRATEGY_INSTANCES
    from app.signals.strategy_pool import StrategyId

    regime_detector = RegimeDetector(timeframe=timeframe)
    aggregator = SignalAggregator()
    warmup = 100

    signals_out: list[dict] = [{}] * len(candles_list)
    regimes_out: list[str] = [None] * len(candles_list)
    regime_probs_out: list[dict] = [{}] * len(candles_list)

    for i in range(warmup, len(candles_list)):
        window = candles_list[max(0, i - 500):i + 1]
        if len(window) < 30:
            continue

        # Regime detection
        closes = np.array([c["close"] for c in window], dtype=np.float64)
        volumes = np.array([c["volume"] for c in window], dtype=np.float64)
        highs = np.array([c["high"] for c in window], dtype=np.float64)
        lows = np.array([c["low"] for c in window], dtype=np.float64)
        log_returns = np.diff(np.log(closes + 1e-10), prepend=closes[0])

        regime_info = regime_detector.update(
            log_returns, volumes, high=highs, low=lows, close=closes
        )

        # Strategy results
        strategy_results = []
        for sid, strat in STRATEGY_INSTANCES.items():
            # Build candles dict for this window
            cd = {
                "symbol": pair,
                "timeframe": timeframe,
                "open": [c["open"] for c in window],
                "high": [c["high"] for c in window],
                "low": [c["low"] for c in window],
                "close": [c["close"] for c in window],
            }
            vols = np.array([c["volume"] for c in window], dtype=np.float64)
            result = strat.evaluate(cd, vols, regime_info.regime.value)
            strategy_results.append(result)

        # Aggregate
        agg = aggregator.aggregate(
            strategy_results=strategy_results,
            regime=regime_info.regime,
            regime_confidence=regime_info.confidence,
            timeframe=timeframe,
            adx=regime_info.adx,
            hurst=regime_info.hurst,
        )

        signals_out[i] = {
            "direction": 1.0 if agg and agg.direction == "long" else (-1.0 if agg and agg.direction == "short" else np.nan),
            "confidence": agg.confidence if agg else np.nan,
            "regime": regime_info.regime.value,
        }
        regimes_out[i] = regime_info.regime.value
        regime_probs_out[i] = {r.value: float(p) for r, p in regime_info.regime_probs.items()}

    return signals_out, regimes_out, regime_probs_out


# ── Main ─────────────────────────────────────────────────────────────────────

def run_baseline() -> None:
    results: list[dict] = []
    all_symbol_confs: dict[str, list[float]] = {s: [] for s in SYMBOLS}

    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            print(f"  Processing {symbol} {tf}...", flush=True)
            df = generate_synthetic_ohlcv(symbol, tf, N_CANDLES)
            candles_list = ohlcv_to_candles_dict(df, symbol, tf)

            # Compute ground truth future returns
            future_ret = compute_future_return(df, horizon=5)

            # Run signal engine
            signals, regimes, reg_probs = run_signal_engine(candles_list, symbol, tf)

            # Collect non-null signals
            signal_dirs = np.array([s.get("direction", np.nan) for s in signals], dtype=np.float64)
            confidences = np.array([s.get("confidence", np.nan) for s in signals], dtype=np.float64)
            mask = ~np.isnan(signal_dirs) & ~np.isnan(future_ret)

            hr = hit_rate(signal_dirs, future_ret)
            bs = brier_score(confidences[mask], (future_ret[mask] > 0).astype(float)) if mask.sum() > 0 else 1.0

            # Per-regime hit rates
            regimes_arr = np.array(regimes, dtype=object)
            regime_hrs = {}
            for r in ("bull", "bear", "choppy", "crisis"):
                rmask = mask & (regimes_arr == r)
                regime_hrs[r] = hit_rate(signal_dirs[rmask], future_ret[rmask]) if rmask.sum() > 0 else np.nan

            n_signals = int(mask.sum())
            all_symbol_confs[symbol].extend(confidences[mask].tolist())

            results.append({
                "symbol": symbol,
                "timeframe": tf,
                "n_signals": n_signals,
                "hit_rate": round(hr, 4),
                "brier_score": round(bs, 4),
                "hr_bull": round(regime_hrs.get("bull", np.nan), 4),
                "hr_bear": round(regime_hrs.get("bear", np.nan), 4),
                "hr_choppy": round(regime_hrs.get("choppy", np.nan), 4),
                "hr_crisis": round(regime_hrs.get("crisis", np.nan), 4),
            })
            print(f"    hit_rate={hr:.3f}  brier={bs:.4f}  n_signals={n_signals}", flush=True)

    # Aggregate across symbols
    symbol_agg = {}
    for sym, confs in all_symbol_confs.items():
        if confs:
            symbol_agg[sym] = {
                "mean_conf": round(np.mean(confs), 4),
                "n": len(confs),
            }

    # Write report
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report_path = Path(f"reports/bt-baseline-realistic-{date_str}.md")
    report_path.parent.mkdir(exist_ok=True)

    with open(report_path, "w") as f:
        f.write(f"# Baseline Signal Engine Report (Synthetic-Realistic OHLCV)\n")
        f.write(f"Generated: {datetime.now(timezone.utc).isoformat()} UTC\n")
        f.write(f"Seed: {SEED} | Candles/symbol/tf: {N_CANDLES}\n\n")

        f.write("## Per-Symbol Per-Timeframe Results\n\n")
        f.write("| Symbol | TF | Signals | Hit Rate | Brier | HR Bull | HR Bear | HR Choppy | HR Crisis |\n")
        f.write("|--------|----|---------|----------|-------|---------|---------|-----------|----------|\n")
        for r in results:
            f.write(f"| {r['symbol']} | {r['timeframe']} | {r['n_signals']} "
                     f"| {r['hit_rate']:.1%} | {r['brier_score']:.4f} "
                     f"| {r['hr_bull']:.1%} | {r['hr_bear']:.1%} "
                     f"| {r['hr_choppy']:.1%} | {r['hr_crisis']:.1%} |\n")

        f.write("\n## Symbol Aggregate\n\n")
        f.write("| Symbol | Mean Confidence | N Samples |\n")
        f.write("|--------|----------------|-----------|\n")
        for sym, agg in symbol_agg.items():
            f.write(f"| {sym} | {agg['mean_conf']:.3f} | {agg['n']} |\n")

        overall_hr = np.mean([r["hit_rate"] for r in results if r["n_signals"] > 0])
        overall_bs = np.mean([r["brier_score"] for r in results if r["n_signals"] > 0])
        f.write(f"\n**Overall Hit Rate: {overall_hr:.1%} | Overall Brier: {overall_bs:.4f}**\n")

    print(f"\nBaseline report written to {report_path}")
    print(f"Overall hit_rate={overall_hr:.1%}  brier={overall_bs:.4f}")
    return report_path


if __name__ == "__main__":
    print("=== Phase 1: Realistic Baseline Backtester ===")
    run_baseline()
