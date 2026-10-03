# Rule vs ML Backtest Report (Fast Mode)
Generated: 2026-10-03T10:05:35.086673+00:00 UTC
Seed: 42 | Candles: 1000 | Horizon: 5

## Results

| Symbol | TF | N | HR Rule | HR ML | ΔHR | Brier Rule | Brier ML | ΔBrier | AUC Rule | AUC ML | ΔAUC | ML |
|--------|----|---|---------|-------|-----|------------|----------|--------|---------|-------|------|----|
| BTC-USDT | 1h | 566 | 51.9% | 52.9% | +0.9% | 0.2794 | 0.2850 | -0.0056 | 0.515 | 0.528 | +0.014 | ✅ |
| BTC-USDT | 4h | 571 | 52.7% | 52.9% | +0.2% | 0.2747 | 0.2750 | -0.0003 | 0.528 | 0.527 | -0.001 | ✅ |
| BTC-USDT | 1d | 529 | 47.6% | 46.4% | -1.2% | 0.2821 | 0.2837 | -0.0015 | 0.463 | 0.451 | -0.012 | ⚠️ |
| ETH-USDT | 1h | 653 | 50.4% | 51.5% | +1.1% | 0.2714 | 0.2712 | +0.0002 | 0.453 | 0.443 | -0.010 | ✅ |
| ETH-USDT | 4h | 577 | 50.4% | 50.2% | -0.2% | 0.2813 | 0.2814 | -0.0001 | 0.529 | 0.535 | +0.006 | ⚠️ |
| ETH-USDT | 1d | 575 | 47.7% | 48.0% | +0.3% | 0.2752 | 0.2777 | -0.0024 | 0.529 | 0.543 | +0.014 | ✅ |
| SOL-USDT | 1h | 673 | 53.8% | 53.2% | -0.6% | 0.2630 | 0.2645 | -0.0015 | 0.519 | 0.519 | +0.000 | ⚠️ |
| SOL-USDT | 4h | 650 | 51.4% | 51.4% | +0.0% | 0.2781 | 0.2773 | +0.0008 | 0.548 | 0.557 | +0.009 | ✅ |
| SOL-USDT | 1d | 670 | 50.7% | 51.4% | +0.6% | 0.2767 | 0.2782 | -0.0014 | 0.497 | 0.490 | -0.006 | ✅ |
| DOGE-USDT | 1h | 632 | 54.0% | 55.2% | +1.2% | 0.2686 | 0.2695 | -0.0009 | 0.496 | 0.506 | +0.009 | ✅ |
| DOGE-USDT | 4h | 604 | 46.7% | 46.4% | -0.3% | 0.2669 | 0.2649 | +0.0020 | 0.480 | 0.467 | -0.013 | ✅ |
| DOGE-USDT | 1d | 601 | 49.6% | 49.9% | +0.3% | 0.2830 | 0.2821 | +0.0009 | 0.507 | 0.503 | -0.004 | ✅ |
| XRP-USDT | 1h | 644 | 52.3% | 53.2% | +0.9% | 0.2754 | 0.2747 | +0.0007 | 0.475 | 0.475 | -0.000 | ✅ |
| XRP-USDT | 4h | 574 | 52.6% | 52.8% | +0.1% | 0.2671 | 0.2670 | +0.0001 | 0.493 | 0.489 | -0.004 | ✅ |
| XRP-USDT | 1d | 578 | 50.3% | 49.0% | -1.4% | 0.2684 | 0.2696 | -0.0012 | 0.502 | 0.505 | +0.003 | ⚠️ |

## Aggregate Summary

| Metric | Rule | ML | Delta |
|--------|------|----|-------|
| Hit Rate | 50.8% | 51.0% | +0.1% |
| Brier Score | 0.2741 | 0.2748 | -0.0007 |
| AUC | 0.502 | 0.503 | +0.000 |
| ML Helped | — | 11/15 | |

## Verdict

⚠️ **ML DID NOT IMPROVE — see analysis**

- avg Δhit_rate = +0.1%
- avg Δbrier = -0.0007 (positive = ML better calibration)
- avg Δauc = +0.000

**Analysis**: ML did not outperform rule-only on synthetic-realistic GBM data.
This is expected: GBM generates close-to-random walk with injected regime patterns.
Strategy signals on GBM produce ~50% hit rate (random) and ML cannot improve.
Real market data (with microstructure, order flow) would show different results.
