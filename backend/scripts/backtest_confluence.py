#!/usr/bin/env python3
"""
backtest_confluence.py — 回测验证 multi_indicator_confluence 评分的方向命中率

核心问题：本评分是无方向"指标共识度"分数，分数高不代表看涨，
         而是代表"各项指标互相确认"。真正的预测力在于：
         当各项指标方向一致（bullish_count↑ + bearish_count=0 或反过来）
         且 ADX 高（趋势明确）时，后续方向更可预测。

用法:
    cd backend
    PYTHONPATH=. python3 scripts/backtest_confluence.py --symbol BTC-USDT --timeframe 1h
    PYTHONPATH=. python3 scripts/backtest_confluence.py --symbol BTC-USDT --timeframe 4h
    PYTHONPATH=. python3 scripts/backtest_confluence.py --symbol BTC-USDT --timeframe 1d
    PYTHONPATH=. python3 scripts/backtest_confluence.py --symbol ETH-USDT --timeframe 1h
    PYTHONPATH=. python3 scripts/backtest_confluence.py --symbol SOL-USDT --timeframe 1h
    PYTHONPATH=. python3 scripts/backtest_confluence.py --multi   # 多币种×多周期

多币种多周期:
    PYTHONPATH=. python3 scripts/backtest_confluence.py --symbols BTC-USDT,ETH-USDT,SOL-USDT \
        --timeframes 1h,4h,1d --multi

真实数据:
    PYTHONPATH=. python3 scripts/backtest_confluence.py --symbol BTC-USDT --timeframe 1h --source okx
    PYTHONPATH=. python3 scripts/backtest_confluence.py --symbol BTCUSDT --timeframe 1h --source binance

多币种扫描:
    PYTHONPATH=. python3 scripts/backtest_confluence.py --scan-all
    PYTHONPATH=. python3 scripts/backtest_confluence.py --scan-all --report /tmp/scan-2026-09-27.md
"""

import argparse
import math
import sys
import os
from datetime import datetime, timezone
from typing import Literal, TypedDict
import warnings

# 确保 backend/ 在 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

from app.analytics.trend import multi_indicator_confluence
from app.api.klines import Candle


# ── Mock 数据生成（timeframe 感知版）─────────────────────────────────────────
# 不依赖原有 _generate_mock_candles，因为原版忽略了 timeframe 导致所有周期数据相同

_TIMEFRAME_SECONDS: dict[str, int] = {
    "1m": 60, "5m": 300, "15m": 900,
    "1h": 3600, "4h": 14400, "1d": 86400,
}

# Binance timeframe (1h, 4h) → OKX timeframe (1H, 4H) — must be upper-case for OKX
_OKX_INTERVAL_MAP: dict[str, str] = {
    "1m": "1m", "5m": "5m", "15m": "15m",
    "1h": "1H", "4h": "4H", "1d": "1D",
}


def _generate_mock_candles_v2(
    symbol: str,
    timeframe: str,
    count: int,
) -> list[Candle]:
    """生成 mock K 线 — 每根 K 线内嵌随机日内波动，不同 timeframe 有不同特征。"""
    if timeframe not in _TIMEFRAME_SECONDS:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    tf_seconds = _TIMEFRAME_SECONDS[timeframe]

    now_ts = int(datetime.now(timezone.utc).timestamp())
    aligned_now = now_ts - (now_ts % tf_seconds)

    # 用 symbol + timeframe 混合 seed，确保不同周期产生不同价格序列
    seed = sum(ord(c) for c in f"{symbol}:{timeframe}")
    rng = lambda n: (seed * 1103515245 + n * 12345 + 12345) % (2**31)

    # 每个币种的基础价格
    price_map = {
        "BTC": 65000, "ETH": 3400, "SOL": 140,
        "BNB": 580,   "XRP": 0.62, "ADA": 0.45,
    }
    base_sym = symbol.split("-")[0]
    base_price = price_map.get(base_sym, 100.0)

    # timeframe 影响波动幅度（长时间周期振幅更大，但 bar 数量少）
    tf_vol_scale = {
        "1m": 0.0003, "5m": 0.0006, "15m": 0.001,
        "1h": 0.002,  "4h": 0.004,  "1d": 0.008,
    }
    vol = tf_vol_scale.get(timeframe, 0.002)

    # Regime per symbol-timeframe（固定 seed 保证可复现）
    regime_seed = seed % 5
    regime_drift = [0.0003, -0.0003, 0.0, 0.0005, -0.0001][regime_seed]

    candles: list[Candle] = []
    price = base_price

    for i in range(count):
        t = aligned_now - (count - 1 - i) * tf_seconds

        # 多种波动叠加
        wave1   = math.sin((i + seed) * 0.05) * base_price * vol
        wave2   = math.cos((i + seed) * 0.27) * base_price * vol * 0.5
        noise   = math.cos((i * 7 + seed * 3) * 0.73) * base_price * vol * 0.3
        drift   = regime_drift * base_price

        open_px  = price
        change   = wave1 + wave2 + noise + drift
        close_px = price + change

        # high/low 要包容 open/close
        body  = abs(close_px - open_px)
        wick  = base_price * vol * 0.8
        high_px = max(open_px, close_px) + wick
        low_px  = min(open_px, close_px) - wick

        # Volume 随价格波动
        vol_val = abs(change) / base_price / vol * 1000 + rng(i) % 500

        candles.append(Candle(
            time   = t,
            open   = round(open_px,  2),
            high   = round(high_px,  2),
            low    = round(low_px,   2),
            close  = round(close_px, 2),
            volume = round(vol_val,  2),
        ))
        price = close_px

    return candles


# ── 方向信号推导 ──────────────────────────────────────────────────────────────
# confluence_score 本身无方向，它衡量"指标共识度"。
# 真正的交易信号需要从子指标推导方向：
#   - bullish_count > 0 && bearish_count == 0 → "long"
#   - bearish_count > 0 && bullish_count == 0 → "short"
#   - 两者都 > 0 → "mixed"（信号混乱，不做预测）

def derive_signal(result: dict) -> Literal["long", "short", "mixed", "none"]:
    """从 multi_indicator_confluence 返回的子指标推导方向信号。"""
    # price_vs_ma30: above / cross_above → 看多；below / cross_below → 看空
    ma_bull = result["price_vs_ma30"] in ("above", "cross_above")
    ma_bear = result["price_vs_ma30"] in ("below",  "cross_below")

    # MACD: bullish_cross / above_zero → 看多；bearish_cross → 看空
    macd_bull = result["macd"]["status"] in ("bullish_cross", "above_zero")
    macd_bear = result["macd"]["status"] == "bearish_cross"

    # RSI: >50 → 看多（多头区）；<50 → 看空
    rsi_val = result["rsi14"]["value"]
    rsi_bull = rsi_val >= 50
    rsi_bear = rsi_val < 50

    # ADX 趋势确认：只看 ADX > 25 时的信号
    adx_ok = result["adx14"]["adx"] > 25
    adx_dir = result["adx14"]["pdi"] > result["adx14"]["ndi"]

    bullish = sum([ma_bull, macd_bull, rsi_bull, adx_ok and adx_dir])
    bearish = sum([ma_bear, macd_bear, rsi_bear, adx_ok and not adx_dir])

    if bullish > 0 and bearish == 0:
        return "long"
    elif bearish > 0 and bullish == 0:
        return "short"
    elif bullish > 0 and bearish > 0:
        return "mixed"
    else:
        return "none"


# ── 数据获取 ──────────────────────────────────────────────────────────────────

# Binance BTCUSDT → OKX BTC-USDT (for symbol conversion)
def _to_okx_symbol(symbol: str) -> str:
    """Convert Binance-style symbol (BTCUSDT) to OKX-style (BTC-USDT)."""
    s = symbol.upper()
    if "-" in s:
        return s
    for quote in ("USDT", "USDC", "USD", "BTC", "ETH"):
        if s.endswith(quote):
            return f"{s[: -len(quote)]}-{quote}"
    return s


class FetchResult(TypedDict):
    opens: "np.ndarray"
    highs: "np.ndarray"
    lows: "np.ndarray"
    closes: "np.ndarray"
    volumes: "np.ndarray"
    times: list[int]


def fetch_candles(symbol: str, timeframe: str, limit: int, source: str = "mock") -> FetchResult:
    """
    拉 K 线数据，支持 mock / OKX / Binance 三种数据源。

    source:
        mock    — 本地生成（无网络依赖，默认）
        okx     — OKX 公共 REST API（需要网络，无需 API key）
        binance — Binance 公共 REST API（需要网络，无需 API key）

    Returns (highs, lows, closes, volumes, times).
    Raises RuntimeError if all sources fail.
    """
    candles: list[dict]

    if source == "mock":
        candles = [_make_candle(c) for c in _generate_mock_candles_v2(symbol, timeframe, limit)]

    elif source == "okx":
        try:
            import asyncio as _asyncio
            from app.data.okx import OkxClient

            okx_sym = _to_okx_symbol(symbol)
            # Binance-style interval (1h, 4h, 1d) → OKX needs (1H, 4H, 1D)
            okx_interval = _OKX_INTERVAL_MAP.get(timeframe, timeframe.upper())
            client = OkxClient()
            _asyncio.run(client.init())
            raw_rows = _asyncio.run(client.get_klines(okx_sym, okx_interval, limit))
            candles = [_make_candle(r) for r in raw_rows]
            _asyncio.run(client.close())
        except Exception as e:
            warnings.warn(f"[WARN] OKX fetch failed for {symbol} {timeframe}: {e} — falling back to mock")
            candles = [_make_candle(c) for c in _generate_mock_candles_v2(symbol, timeframe, limit)]

    elif source == "binance":
        try:
            import asyncio as _asyncio
            from app.data.binance import BinanceClient

            binance_sym = symbol.upper().replace("-", "")
            client = BinanceClient()
            _asyncio.run(client.init())
            raw_rows = _asyncio.run(client.get_klines(binance_sym, timeframe, limit))
            candles = [_make_candle(r) for r in raw_rows]
            _asyncio.run(client.close())
        except Exception as e:
            warnings.warn(f"[WARN] Binance fetch failed for {symbol} {timeframe}: {e} — falling back to mock")
            candles = [_make_candle(c) for c in _generate_mock_candles_v2(symbol, timeframe, limit)]

    else:
        raise ValueError(f"Unknown source: {source}")

    if not candles:
        raise RuntimeError(f"No candles returned for {symbol} {timeframe}")

    opens  = np.array([c["open"]   for c in candles], dtype=np.float64)
    highs  = np.array([c["high"]   for c in candles], dtype=np.float64)
    lows   = np.array([c["low"]    for c in candles], dtype=np.float64)
    closes = np.array([c["close"]  for c in candles], dtype=np.float64)
    volumes= np.array([c["volume"] for c in candles], dtype=np.float64)
    times  = [c["time"] for c in candles]

    return FetchResult(opens=opens, highs=highs, lows=lows, closes=closes, volumes=volumes, times=times)


def _make_candle(r) -> dict:
    """Normalise candle data from any source into a flat dict.

    Real API: dict with keys  (time, open, high, low, close, volume)
    Mock:     Candle Pydantic object with attribute access
    """
    if isinstance(r, dict):
        return {"time": int(r["time"]), "open": float(r["open"]),
                "high": float(r["high"]), "low": float(r["low"]),
                "close": float(r["close"]), "volume": float(r["volume"])}
    # Pydantic / dataclass object
    return {"time": int(r.time), "open": float(r.open),
            "high": float(r.high), "low": float(r.low),
            "close": float(r.close), "volume": float(r.volume)}


# ── 回测引擎 ─────────────────────────────────────────────────────────────────

def backtest(
    symbol: str,
    timeframe: str,
    limit: int = 2000,
    forward_bars: int = 5,
    thresholds: list[int] = None,
    source: str = "mock",
) -> dict:
    """
    在历史 K 线上回测 confluence_score 的方向命中率。

    核心验证逻辑：
    1. 在每个 i（warmup=100 到 len-1-forward_bars）调用 multi_indicator_confluence
    2. 用 derive_signal() 从子指标推导信号（long/short/mixed/none）
    3. 记录 score + signal + 未来 forward_bars 根 K 线的实际方向
    4. 对信号为 long 的样本，统计后续实际上涨概率
       对信号为 short 的样本，统计后续实际下跌概率

    "命中率"定义：
      long 信号样本中，后续 N 根收盘价上涨的比例
      short 信号样本中，后续 N 根收盘价下跌的比例
    """
    if thresholds is None:
        thresholds = [60, 70, 75, 80]

    result = fetch_candles(symbol, timeframe, limit, source=source)
    opens, highs, lows, closes, volumes, times = (
        result["opens"], result["highs"], result["lows"],
        result["closes"], result["volumes"], result["times"],
    )
    n = len(closes)

    warmup = 100
    min_i  = warmup
    max_i  = n - 1 - forward_bars

    if max_i < min_i:
        print(f"[WARN] Not enough candles: n={n}, warmup={warmup}, forward_bars={forward_bars}", file=sys.stderr)
        return {}

    records: list[dict] = []

    for i in range(min_i, max_i + 1):
        result = multi_indicator_confluence(
            highs[i - warmup:i + 1],
            lows[i - warmup:i + 1],
            closes[i - warmup:i + 1],
            volumes[i - warmup:i + 1],
        )

        score  = result["confluence_score"]
        signal = derive_signal(result)

        # 未来 forward_bars 根的收盘价变化
        future_end  = closes[i + forward_bars]
        price_delta = float(future_end) - float(closes[i])
        pct_change  = price_delta / float(closes[i]) * 100 if closes[i] != 0 else 0.0
        actual_dir   = 1 if price_delta > 0 else (-1 if price_delta < 0 else 0)

        # Signal 是否命中
        if signal == "long":
            signal_hit = 1 if actual_dir > 0 else 0
        elif signal == "short":
            signal_hit = 1 if actual_dir < 0 else 0
        else:
            signal_hit = -1  # 无效信号（mixed/none），不计入信号统计

        # Regime 估算
        adx_val = result["adx14"]["adx"]
        if adx_val < 15:
            regime = "choppy"
        elif adx_val < 25:
            regime = "weak"
        elif result["adx14"]["pdi"] > result["adx14"]["ndi"]:
            regime = "bull"
        else:
            regime = "bear"

        records.append({
            "i":           i,
            "time":         times[i],
            "score":        score,
            "signal":       signal,
            "pct_change":   pct_change,
            "actual_dir":   actual_dir,
            "signal_hit":   signal_hit,
            "regime":       regime,
        })

    df = pd.DataFrame(records)
    if df.empty:
        return {}

    # ── Signal-based 命中率（按方向分类）────────────────────────────────────
    signal_rows = []
    for sig, label in [("long", "long ↑"), ("short", "short ↓"), ("mixed", "mixed"), ("none", "none")]:
        bucket = df[df["signal"] == sig]
        total  = len(bucket)
        if total == 0:
            signal_rows.append({
                "signal":   label, "count": 0, "hit_rate": "—",
                "avg_pct":  "—", "conf_avg": "—",
            })
            continue
        # 只对 long/short 算命中率
        if sig in ("long", "short"):
            hits  = (bucket["signal_hit"] == 1).sum()
            rate  = hits / total * 100
        else:
            rate  = None
        avg_pct   = bucket["pct_change"].mean()
        conf_avg  = bucket["score"].mean()
        signal_rows.append({
            "signal":   label,
            "count":    total,
            "hit_rate": f"{rate:.1f}%" if rate is not None else "—",
            "avg_pct":  f"{avg_pct:+.2f}%",
            "conf_avg": f"{conf_avg:.1f}",
        })

    # ── Score 阈值 × Signal 命中矩阵 ────────────────────────────────────────
    threshold_rows = []
    for thresh in thresholds:
        # 阈值桶（只看有明确信号的）
        bucket = df[(df["score"] >= thresh) & (df["signal"].isin(["long", "short"]))]
        total  = len(bucket)
        if total == 0:
            threshold_rows.append({
                "threshold":   f"≥{thresh}",
                "count":       0,
                "long_pct":    "—",
                "short_pct":   "—",
                "conf_avg":    "—",
                "signal_hit":  "—",
                "vs_baseline": "—",
                "note":        "无样本",
            })
            continue

        long_b   = (bucket["signal"] == "long").sum()
        short_b  = (bucket["signal"] == "short").sum()
        hits     = (bucket["signal_hit"] == 1).sum()
        hit_rate = hits / total * 100
        conf_avg = bucket["score"].mean()

        # 随机基线：long 信号时上涨概率 = 50%，short 信号时下跌概率 = 50%
        # 综合基线 ≈ 50%
        vs_base = hit_rate - 50.0
        flag    = "✅" if vs_base > 3 else ("❌" if vs_base < -10 else "≈")

        threshold_rows.append({
            "threshold":   f"≥{thresh}",
            "count":       total,
            "long_pct":    f"{long_b / total * 100:.0f}%",
            "short_pct":   f"{short_b / total * 100:.0f}%",
            "conf_avg":    f"{conf_avg:.1f}",
            "signal_hit":  f"{hit_rate:.1f}%",
            "vs_baseline": f"{vs_base:+.1f}% {flag}",
            "note":        "",
        })

    # ── Score 区间分桶 ───────────────────────────────────────────────────────
    score_buckets_spec = [
        (0,  30, "0–30"),
        (30, 50, "30–50"),
        (50, 70, "50–70"),
        (70, 85, "70–85"),
        (85, 100,"85–100"),
    ]
    score_rows = []
    for lo, hi, label in score_buckets_spec:
        bucket = df[(df["score"] >= lo) & (df["score"] < hi)]
        total  = len(bucket)
        if total == 0:
            score_rows.append({
                "range": label, "count": 0,
                "long_pct": "—", "short_pct": "—", "mixed_pct": "—",
                "signal_hit": "—", "avg_pct": "—",
            })
            continue
        long_pct   = (bucket["signal"] == "long").sum()   / total * 100
        short_pct  = (bucket["signal"] == "short").sum()  / total * 100
        mixed_pct  = (bucket["signal"] == "mixed").sum()  / total * 100
        none_pct   = (bucket["signal"] == "none").sum()   / total * 100

        # 有效信号（long+short）命中率
        valid = bucket[bucket["signal"].isin(["long", "short"])]
        if len(valid) > 0:
            sh = (valid["signal_hit"] == 1).sum() / len(valid) * 100
            signal_hit_str = f"{sh:.1f}%"
        else:
            signal_hit_str = "—"
        avg_pct = bucket["pct_change"].mean()

        score_rows.append({
            "range":       label,
            "count":       total,
            "long_pct":    f"{long_pct:.0f}%",
            "short_pct":   f"{short_pct:.0f}%",
            "mixed_pct":   f"{mixed_pct:.0f}%",
            "signal_hit":  signal_hit_str,
            "avg_pct":     f"{avg_pct:+.2f}%",
        })

    # ── Regime 分桶 ───────────────────────────────────────────────────────────
    regime_rows = []
    for regime in ["bull", "bear", "weak", "choppy"]:
        bucket = df[df["regime"] == regime]
        total  = len(bucket)
        if total == 0:
            regime_rows.append({"regime": regime, "count": 0,
                                "long_pct": "—", "short_pct": "—", "hit_rate": "—"})
            continue
        long_pct   = (bucket["signal"] == "long").sum()  / total * 100
        short_pct  = (bucket["signal"] == "short").sum() / total * 100
        valid      = bucket[bucket["signal"].isin(["long", "short"])]
        if len(valid) > 0:
            hr = (valid["signal_hit"] == 1).sum() / len(valid) * 100
            hit_str = f"{hr:.1f}%"
        else:
            hit_str = "—"
        regime_rows.append({
            "regime":    regime,
            "count":     total,
            "long_pct":  f"{long_pct:.0f}%",
            "short_pct": f"{short_pct:.0f}%",
            "hit_rate":  hit_str,
        })

    return {
        "symbol":        symbol,
        "timeframe":     timeframe,
        "limit":         limit,
        "forward_bars":  forward_bars,
        "total_records": len(df),
        "signal_stats":  signal_rows,
        "thresholds":    threshold_rows,
        "score_buckets": score_rows,
        "regimes":       regime_rows,
    }


# ── 输出格式化 ───────────────────────────────────────────────────────────────

def print_result(r: dict):
    if not r:
        print("No data to display.")
        return

    print(
        f"\n{'='*64}\n"
        f"## Backtest: {r['symbol']} {r['timeframe']}, "
        f"{r['limit']} candles, forward_bars={r['forward_bars']}\n"
        f"{'='*64}"
    )
    print(f"\n总样本量: {r['total_records']}  |  随机基线: 50.0%  |  后续 K 线: {r['forward_bars']}")

    # Signal 分布
    print(f"\n### Signal 方向分布\n")
    print(f"{'Signal':<10} {'样本数':<8} {'命中率':<10} {'平均涨跌幅':<12} {'Confluence均分':<14}")
    print("-" * 60)
    for row in r["signal_stats"]:
        print(
            f"{row['signal']:<10} "
            f"{row['count']:<8} "
            f"{row['hit_rate']:<10} "
            f"{row['avg_pct']:<12} "
            f"{row['conf_avg']:<14}"
        )

    # 阈值 × Signal 命中
    print(f"\n### Score 阈值 × Signal 命中率\n")
    print(f"{'阈值':<8} {'样本数':<8} {'Long%':<8} {'Short%':<8} {'Conf均分':<10} {'信号命中率':<12} {'vs 基线':<16}")
    print("-" * 80)
    for row in r["thresholds"]:
        print(
            f"{row['threshold']:<8} "
            f"{row['count']:<8} "
            f"{row['long_pct']:<8} "
            f"{row['short_pct']:<8} "
            f"{row['conf_avg']:<10} "
            f"{row['signal_hit']:<12} "
            f"{row['vs_baseline']:<16} "
            f"{row['note']}"
        )

    # Score 区间分桶
    print(f"\n### Score 区间分桶（信号分布 + 有效信号命中率）\n")
    print(f"{'区间':<12} {'样本数':<8} {'Long%':<8} {'Short%':<8} {'Mixed%':<8} {'信号命中':<10} {'平均涨跌':<12}")
    print("-" * 70)
    for row in r["score_buckets"]:
        print(
            f"{row['range']:<12} "
            f"{row['count']:<8} "
            f"{row['long_pct']:<8} "
            f"{row['short_pct']:<8} "
            f"{row['mixed_pct']:<8} "
            f"{row['signal_hit']:<10} "
            f"{row['avg_pct']:<12}"
        )

    # Regime 分桶
    print(f"\n### Regime 分桶\n")
    print(f"{'Regime':<12} {'样本数':<8} {'Long%':<8} {'Short%':<8} {'有效信号命中':<14}")
    print("-" * 52)
    for row in r["regimes"]:
        print(
            f"{row['regime']:<12} "
            f"{row['count']:<8} "
            f"{row['long_pct']:<8} "
            f"{row['short_pct']:<8} "
            f"{row['hit_rate']:<14}"
        )
    print()


# ── 多币种扫描 ────────────────────────────────────────────────────────────────

def scan_all(
    symbols: list[str] | None = None,
    timeframes: list[str] | None = None,
    sources: list[str] | None = None,
    limit: int = 2000,
    forward_bars: int = 5,
    thresholds: list[int] | None = None,
) -> list[dict]:
    """
    在 (symbol × timeframe × source) 网格上运行回测，返回汇总结果列表。
    """
    if symbols is None:
        symbols = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "DOGE-USDT", "XRP-USDT"]
    if timeframes is None:
        timeframes = ["1h", "4h", "1d"]
    if sources is None:
        sources = ["mock", "okx"]
    if thresholds is None:
        thresholds = [60, 70, 75, 80]

    results: list[dict] = []
    for sym in symbols:
        for tf in timeframes:
            for src in sources:
                print(f"[scan] {sym} {tf} ({src})...", flush=True)
                try:
                    r = backtest(
                        symbol=sym, timeframe=tf, limit=limit,
                        forward_bars=forward_bars, thresholds=thresholds,
                        source=src,
                    )
                    if r:
                        r["_source"] = src
                        results.append(r)
                        _print_single_result(r)
                except Exception as e:
                    print(f"[scan] {sym} {tf} ({src}) ERROR: {e}", file=sys.stderr)
    return results


def _print_single_result(r: dict):
    """Print minimal one-liner after each scan cell."""
    src = r.get("_source", "unknown")
    sig_rows = r.get("signal_stats", [])
    long_hit = short_hit = None
    for row in sig_rows:
        if row["signal"] == "long ↑":
            try:
                long_hit = float(row["hit_rate"].rstrip("%"))
            except (ValueError, AttributeError):
                pass
        elif row["signal"] == "short ↓":
            try:
                short_hit = float(row["hit_rate"].rstrip("%"))
            except (ValueError, AttributeError):
                pass
    mean_hit = (long_hit + short_hit) / 2 if long_hit is not None and short_hit is not None else None
    vs_50 = mean_hit - 50 if mean_hit is not None else None
    marker = f"**+{vs_50:.1f}%** ✅" if vs_50 is not None and vs_50 > 3 else (f"{vs_50:+.1f}% ❌" if vs_50 is not None and vs_50 < -10 else f"{vs_50:+.1f}% ≈" if vs_50 is not None else "—")
    print(
        f"  → n={r['total_records']} | "
        f"long_hit={long_hit:.1f}% short_hit={short_hit:.1f}% "
        f"mean={mean_hit:.1f}% vs_50%={marker}"
    )


def print_multi_scan_table(results: list[dict]):
    """Pretty-print the full multi-asset scan as a markdown-style table."""
    if not results:
        print("No results to display.")
        return

    print(f"\n{'='*100}")
    print("## Multi-Asset Scan: {} cells".format(len(results)))
    print(f"{'='*100}\n")

    print(
        f"{'Symbol':<12} {'TF':<5} {'Src':<8} {'n':<6} "
        f"{'Long%':<8} {'Short%':<8} {'Mean%':<8} {'vs 50%':<12} {'Status'}"
    )
    print("-" * 100)

    for r in results:
        src = r.get("_source", "mock")
        sig_rows = r.get("signal_stats", [])
        long_hit = short_hit = None
        for row in sig_rows:
            if row["signal"] == "long ↑":
                try:
                    long_hit = float(row["hit_rate"].rstrip("%"))
                except (ValueError, AttributeError):
                    pass
            elif row["signal"] == "short ↓":
                try:
                    short_hit = float(row["hit_rate"].rstrip("%"))
                except (ValueError, AttributeError):
                    pass
        mean_hit = (long_hit + short_hit) / 2 if long_hit is not None and short_hit is not None else None
        vs_50 = mean_hit - 50 if mean_hit is not None else None

        long_str = f"{long_hit:.1f}%" if long_hit is not None else "—"
        short_str = f"{short_hit:.1f}%" if short_hit is not None else "—"
        mean_str = f"{mean_hit:.1f}%" if mean_hit is not None else "—"

        if vs_50 is not None:
            if vs_50 > 3:
                status = "✅"
            elif vs_50 < -10:
                status = "❌"
            else:
                status = "≈"
            vs_str = f"{vs_50:+.1f}% {status}"
        else:
            vs_str = "—"

        print(
            f"{r['symbol']:<12} {r['timeframe']:<5} {src:<8} {r['total_records']:<6} "
            f"{long_str:<8} {short_str:<8} {mean_str:<8} {vs_str:<12}"
        )

    print()


# ── Markdown 报告 ─────────────────────────────────────────────────────────────

def write_markdown_report(path: str, results: list[dict], single_result: dict | None = None):
    """
    将回测结果写入 markdown 报告文件。

    Args:
        path:  报告输出路径（如 reports/bt-2026-09-27.md）
        results: scan_all 返回的列表（multi-asset 模式）
        single_result: 单币种 backtest 结果（单币种模式）
    """
    import os
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    with open(path, "w") as f:
        f.write(f"# Backtest Report\n\n")
        f.write(f"Generated at {now_str}\n\n")

        # ── Multi-asset section ─────────────────────────────────────────────
        if results:
            f.write("## Multi-Asset Scan Summary\n\n")
            f.write(
                f"| Symbol | TF | Source | n | Long% | Short% | Mean% | vs 50% |\n"
                f"|--------|----|--------|---|-------|--------|-------|--------|\n"
            )
            for r in results:
                src = r.get("_source", "mock")
                sig_rows = r.get("signal_stats", [])
                long_hit = short_hit = None
                for row in sig_rows:
                    if row["signal"] == "long ↑":
                        try:
                            long_hit = float(row["hit_rate"].rstrip("%"))
                        except (ValueError, AttributeError):
                            pass
                    elif row["signal"] == "short ↓":
                        try:
                            short_hit = float(row["hit_rate"].rstrip("%"))
                        except (ValueError, AttributeError):
                            pass
                mean_hit = (long_hit + short_hit) / 2 if long_hit is not None and short_hit is not None else None
                vs_50 = mean_hit - 50 if mean_hit is not None else None

                long_str = f"{long_hit:.1f}%" if long_hit is not None else "—"
                short_str = f"{short_hit:.1f}%" if short_hit is not None else "—"
                mean_str = f"{mean_hit:.1f}%" if mean_hit is not None else "—"
                vs_str = f"{vs_50:+.1f}% ✅" if vs_50 is not None and vs_50 > 3 else (
                    f"{vs_50:+.1f}% ❌" if vs_50 is not None and vs_50 < -10 else (
                        f"{vs_50:+.1f}% ≈" if vs_50 is not None else "—"
                    )
                )
                f.write(
                    f"| {r['symbol']} | {r['timeframe']} | {src} "
                    f"| {r['total_records']} | {long_str} | {short_str} | {mean_str} | {vs_str} |\n"
                )

            # ── ASCII histogram of mean hit rates ──────────────────────────
            f.write("\n### Mean Hit Rate Distribution\n\n")
            f.write("```\n")
            for r in results:
                src = r.get("_source", "mock")
                sig_rows = r.get("signal_stats", [])
                long_hit = short_hit = None
                for row in sig_rows:
                    if row["signal"] == "long ↑":
                        try:
                            long_hit = float(row["hit_rate"].rstrip("%"))
                        except (ValueError, AttributeError):
                            pass
                    elif row["signal"] == "short ↓":
                        try:
                            short_hit = float(row["hit_rate"].rstrip("%"))
                        except (ValueError, AttributeError):
                            pass
                mean_hit = (long_hit + short_hit) / 2 if long_hit is not None and short_hit is not None else 50.0
                bar_len = max(0, min(50, int(mean_hit - 30)))
                bar = "█" * bar_len
                vs_50 = mean_hit - 50
                marker = "+" if vs_50 >= 0 else ""
                f.write(
                    f"  {r['symbol']:<10} {r['timeframe']:<4} {src:<8} "
                    f"{mean_hit:5.1f}% |{bar} {marker}{vs_50:+.1f}%\n"
                )
            f.write("```\n")

        # ── Single-asset section ────────────────────────────────────────────
        elif single_result:
            r = single_result
            f.write(f"## Single Asset: {r['symbol']} {r['timeframe']}\n\n")
            f.write(f"- Total records: {r['total_records']}\n")
            f.write(f"- Forward bars: {r.get('forward_bars', '?')}\n")
            f.write(f"- Limit: {r.get('limit', '?')}\n\n")

            f.write("### Signal Distribution\n\n")
            f.write(
                f"| Signal | Count | Hit Rate | Avg % | Confluence Avg |\n"
                f"|--------|-------|----------|-------|----------------|\n"
            )
            for row in r.get("signal_stats", []):
                f.write(
                    f"| {row['signal']} | {row['count']} | "
                    f"{row['hit_rate']} | {row['avg_pct']} | {row['conf_avg']} |\n"
                )

            f.write("\n### Score Threshold × Hit Rate\n\n")
            f.write(
                f"| Threshold | Count | Long% | Short% | Conf Avg | Hit% | vs 50% |\n"
                f"|-----------|-------|-------|--------|----------|------|--------|\n"
            )
            for row in r.get("thresholds", []):
                f.write(
                    f"| {row['threshold']} | {row['count']} | "
                    f"{row['long_pct']} | {row['short_pct']} | "
                    f"{row['conf_avg']} | {row['signal_hit']} | {row['vs_baseline']} |\n"
                )

            f.write("\n### Score Bucket Distribution\n\n")
            f.write(
                f"| Range | Count | Long% | Short% | Mixed% | Hit% | Avg% |\n"
                f"|-------|-------|-------|--------|--------|------|------|\n"
            )
            for row in r.get("score_buckets", []):
                f.write(
                    f"| {row['range']} | {row['count']} | "
                    f"{row['long_pct']} | {row['short_pct']} | "
                    f"{row['mixed_pct']} | {row['signal_hit']} | {row['avg_pct']} |\n"
                )

        f.write(f"\n---\n*Generated by backtest_confluence.py*\n")

    print(f"[report] Written to {path}")


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="回测 multi_indicator_confluence 评分命中率",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # mock 数据单币种（向后兼容）
  PYTHONPATH=. python scripts/backtest_confluence.py --symbol BTC-USDT --timeframe 1h

  # OKX 真实数据
  PYTHONPATH=. python scripts/backtest_confluence.py --symbol BTC-USDT --timeframe 1h --source okx

  # Binance 真实数据
  PYTHONPATH=. python scripts/backtest_confluence.py --symbol BTCUSDT --timeframe 1h --source binance

  # 多币种扫描（5×3×2=30 个组合）
  PYTHONPATH=. python scripts/backtest_confluence.py --scan-all

  # 扫描并写 markdown 报告
  PYTHONPATH=. python scripts/backtest_confluence.py --scan-all --report /tmp/scan-2026-09-27.md
""",
    )
    parser.add_argument("--symbol",       default="BTC-USDT")
    parser.add_argument("--timeframe",   default="1h")
    parser.add_argument("--limit",       type=int, default=2000)
    parser.add_argument("--forward-bars", type=int, default=5)
    parser.add_argument("--thresholds",   type=str, default="60,70,75,80")
    parser.add_argument(
        "--source",
        choices=["mock", "okx", "binance"],
        default="mock",
        help="Data source: mock (no network) | okx (real OKX public) | binance (real Binance public)",
    )
    # 多币种扫描参数
    parser.add_argument("--scan-all",     action="store_true",
                        help="Scan all symbol × timeframe × source combinations")
    parser.add_argument("--symbols",      type=str,
                        default="BTC-USDT,ETH-USDT,SOL-USDT,DOGE-USDT,XRP-USDT")
    parser.add_argument("--timeframes",  type=str, default="1h,4h,1d")
    parser.add_argument("--sources",      type=str, default="mock,okx")
    # 报告参数
    parser.add_argument("--report",       type=str, default=None,
                        help="Write markdown report to this path (e.g. reports/bt-2026-09-27.md)")
    # 向后兼容
    parser.add_argument("--no-mock",     action="store_true",
                        help="(Deprecated) Use --source okx instead")
    parser.add_argument("--multi",        action="store_true",
                        help="(Deprecated) Use --scan-all instead")

    args = parser.parse_args()

    thresholds = [int(t.strip()) for t in args.thresholds.split(",")]

    # 旧兼容：如果传了 --no-mock 或 --multi，自动切换行为
    effective_source = args.source
    if args.no_mock and args.source == "mock":
        # 优先用 okx（--no-mock 的历史语义）
        effective_source = "okx"

    if args.scan_all or args.multi:
        symbols_list   = [s.strip() for s in args.symbols.split(",")]
        tf_list        = [t.strip() for t in args.timeframes.split(",")]
        src_list       = [s.strip() for s in args.sources.split(",")]
        results = scan_all(
            symbols=symbols_list,
            timeframes=tf_list,
            sources=src_list,
            limit=args.limit,
            forward_bars=args.forward_bars,
            thresholds=thresholds,
        )
        print_multi_scan_table(results)
        if args.report:
            write_markdown_report(args.report, results=results)
    else:
        r = backtest(
            symbol=args.symbol,
            timeframe=args.timeframe,
            limit=args.limit,
            forward_bars=args.forward_bars,
            thresholds=thresholds,
            source=effective_source,
        )
        print_result(r)
        if args.report:
            write_markdown_report(args.report, results=[], single_result=r)


if __name__ == "__main__":
    main()
