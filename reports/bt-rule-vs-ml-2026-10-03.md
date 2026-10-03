# Rule vs ML Backtest Report (Fast Mode)
Generated: 2026-10-03T10:32:59.196720+00:00 UTC
Seed: 42 | Candles: 1000 | Horizon: 5

## Results

| Symbol | TF | N | HR Rule | HR ML | ΔHR | Brier Rule | Brier ML | ΔBrier | AUC Rule | AUC ML | ΔAUC | ML |
|--------|----|---|---------|-------|-----|------------|----------|--------|---------|-------|------|----|
| BTC-USDT | 1h | 650 | 51.8% | 49.9% | -1.9% | 0.2663 | 0.2593 | +0.0071 | 0.487 | 0.492 | +0.005 | ✅ |
| BTC-USDT | 4h | 524 | 51.5% | 51.0% | -0.5% | 0.2776 | 0.2661 | +0.0115 | 0.482 | 0.468 | -0.014 | ✅ |
| BTC-USDT | 1d | 676 | 51.8% | 52.1% | +0.3% | 0.2822 | 0.2870 | -0.0048 | 0.544 | 0.537 | -0.008 | ✅ |
| ETH-USDT | 1h | 486 | 50.6% | 52.3% | +1.7% | 0.2781 | 0.2587 | +0.0194 | 0.477 | 0.473 | -0.004 | ✅ |
| ETH-USDT | 4h | 536 | 49.1% | 49.8% | +0.7% | 0.2727 | 0.2670 | +0.0057 | 0.477 | 0.481 | +0.004 | ✅ |
| ETH-USDT | 1d | 482 | 48.5% | 46.6% | -1.9% | 0.2798 | 0.2709 | +0.0089 | 0.489 | 0.474 | -0.015 | ✅ |
| SOL-USDT | 1h | 623 | 48.2% | 43.5% | -4.7% | 0.2842 | 0.2667 | +0.0174 | 0.516 | 0.518 | +0.001 | ✅ |
| SOL-USDT | 4h | 613 | 48.8% | 49.9% | +1.1% | 0.2811 | 0.2577 | +0.0235 | 0.530 | 0.529 | -0.001 | ✅ |
| SOL-USDT | 1d | 576 | 50.5% | 49.6% | -0.9% | 0.2729 | 0.2559 | +0.0170 | 0.494 | 0.508 | +0.014 | ✅ |
| DOGE-USDT | 1h | 684 | 47.7% | 47.1% | -0.6% | 0.2751 | 0.2758 | -0.0008 | 0.491 | 0.489 | -0.002 | ⚠️ |
| DOGE-USDT | 4h | 616 | 48.9% | 48.2% | -0.7% | 0.2676 | 0.2700 | -0.0024 | 0.516 | 0.510 | -0.007 | ⚠️ |
| DOGE-USDT | 1d | 577 | 50.3% | 50.5% | +0.3% | 0.2879 | 0.2892 | -0.0013 | 0.520 | 0.525 | +0.005 | ✅ |
| XRP-USDT | 1h | 578 | 47.9% | 47.3% | -0.6% | 0.2827 | 0.2811 | +0.0016 | 0.543 | 0.550 | +0.008 | ✅ |
| XRP-USDT | 4h | 589 | 47.9% | 48.3% | +0.4% | 0.2765 | 0.2776 | -0.0011 | 0.523 | 0.527 | +0.004 | ✅ |
| XRP-USDT | 1d | 711 | 53.3% | 53.1% | -0.2% | 0.2803 | 0.2840 | -0.0038 | 0.501 | 0.510 | +0.009 | ⚠️ |

## Aggregate Summary

| Metric | Rule | ML | Delta |
|--------|------|----|-------|
| Hit Rate | 49.8% | 49.3% | -0.5% |
| Brier Score | 0.2777 | 0.2711 | +0.0065 |
| AUC | 0.506 | 0.506 | -0.000 |
| ML Helped | — | 12/15 | |

## Verdict

⚠️ **ML DID NOT IMPROVE — see analysis**

- avg Δhit_rate = -0.5%
- avg Δbrier = +0.0065 (positive = ML better calibration)
- avg Δauc = -0.000

**Analysis**: ML did not outperform rule-only on synthetic-realistic GBM data.
This is expected: GBM generates close-to-random walk with injected regime patterns.
Strategy signals on GBM produce ~50% hit rate (random) and ML cannot improve.
Real market data (with microstructure, order flow) would show different results.
