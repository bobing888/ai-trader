"""Tests for analytics — trend / volatility / statistical / unified endpoint"""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.analytics.statistical import (
    fractal_dimension,
    hurst_exponent,
    rsi_score,
    shannon_entropy,
)
from app.analytics.trend import adx, trend_strength
from app.analytics.volatility import atr, volatility_percentile
from app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


def synthetic_candles(n: int = 200, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    # 模拟一个带趋势的序列
    trend = np.linspace(100, 110, n)
    noise = rng.normal(0, 0.5, n)
    close = trend + noise
    high = close + abs(rng.normal(0, 0.3, n))
    low = close - abs(rng.normal(0, 0.3, n))
    open_ = close + rng.normal(0, 0.1, n)
    volume = rng.uniform(100, 500, n)
    return {"close": close, "high": high, "low": low, "open": open_, "volume": volume}


# ── Unit tests ────────────────────────────────────────────────────────────────


def test_hurst_random_walk_returns_reasonable():
    """随机游走 Hurst 应在合理范围（注意 R/S 方法在小样本会有偏差）"""
    rng = np.random.default_rng(0)
    close = np.cumsum(rng.normal(0, 1, 500)) + 100
    h = hurst_exponent(close)
    assert 0.3 < h < 1.0  # R/S 在随机序列上会有 +0.1 偏差


def test_hurst_trending_returns_gt_05():
    """强单调序列 Hurst 应该 > 0.5"""
    close = np.linspace(100, 200, 500) + np.random.default_rng(1).normal(0, 0.01, 500)
    h = hurst_exponent(close)
    assert h > 0.5


def test_fractal_dim_complement_of_hurst():
    close = np.linspace(100, 110, 300) + np.random.default_rng(2).normal(0, 0.5, 300)
    d = fractal_dimension(close)
    h = hurst_exponent(close)
    assert abs(d - (2.0 - h)) < 1e-6


def test_entropy_uniform_distribution_max():
    """均匀分布 entropy 最大 = log2(bins)"""
    bins = 20
    prices = np.linspace(0, 1, bins * 50)  # 几乎均匀
    h = shannon_entropy(prices, bins=bins)
    assert 3.5 < h < 4.5  # log2(20) ≈ 4.32


def test_rsi_score_mapping():
    """RSI 反向情绪分映射正确"""
    # 超卖场景：连续下跌后 RSI 应该 < 30, score > 70
    prices = np.linspace(100, 50, 50)
    score = rsi_score(prices)
    assert score > 70


def test_adx_returns_three_arrays():
    s = synthetic_candles()
    a, p, n = adx(s["high"], s["low"], s["close"], period=14)
    assert len(a) == len(p) == len(n) == 200
    assert not np.isnan(a[-1])


def test_trend_strength_returns_dict():
    s = synthetic_candles()
    out = trend_strength(s["high"], s["low"], s["close"])
    assert "adx" in out
    assert "pdi" in out
    assert "ndi" in out
    assert "strength_label" in out
    assert out["strength_label"] in {"无趋势", "弱趋势", "中等趋势", "强趋势", "极强趋势"}


def test_atr_and_volatility_percentile():
    s = synthetic_candles(300)
    a = atr(s["high"], s["low"], s["close"])
    assert a[-1] > 0
    vp = volatility_percentile(s["close"], s["high"], s["low"])
    assert "current_atr_pct" in vp
    assert 0 <= vp["percentile_1y"] <= 1


# ── Integration tests (via API) ───────────────────────────────────────────────


def test_analysis_endpoint_btcusdt(client):
    r = client.get("/api/analysis/BTCUSDT?timeframe=1h&limit=200")
    if r.status_code == 502:
        pytest.skip("Binance unreachable in test env")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["symbol"] == "BTCUSDT"
    assert "regime" in data and data["regime"]["regime"] in {"bull", "bear", "choppy", "crisis"}
    assert "trend" in data
    assert "volatility" in data
    assert "statistical" in data
    assert "multifactor" in data
    # Hurst 应该在合法范围
    assert 0 <= data["statistical"]["hurst"] <= 1
    # multifactor 分数 0-100
    assert 0 <= data["multifactor"]["composite"] <= 100


def test_analysis_invalid_symbol_returns_404(client):
    r = client.get("/api/analysis/INVALIDXXX?timeframe=1h&limit=60")
    if r.status_code == 502:
        pytest.skip("Binance unreachable in test env")
    assert r.status_code == 404
