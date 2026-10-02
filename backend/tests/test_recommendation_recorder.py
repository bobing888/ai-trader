"""test_recommendation_recorder — TDD: _resample_ohlcv 1m → target timeframe"""

from datetime import UTC, datetime

from app.services.recommendation_recorder import _resample_ohlcv


def _make_candle(ts_minutes_ago=0, **kwargs):
    """制造 1m K 线 — ts 落在一个整 60 边界,方便 1h 测试。"""
    bucket_minutes = 60
    base_ts = int(datetime.now(UTC).timestamp() // (bucket_minutes * 60)) * (bucket_minutes * 60)
    base_ts_ms = base_ts * 1000
    ts = base_ts_ms - ts_minutes_ago * 60 * 1000
    base = {
        "ts": ts,
        "o": 50000.0,
        "h": 50100.0,
        "l": 49900.0,
        "c": 50050.0,
        "vol": 100.0,
        "confirm": True,
    }
    base.update(kwargs)
    return base


def test_resample_1m_to_5m_basic():
    """45 根 1m K 线 → 9 根 5m K 线（同一小时内）。"""
    candles = [_make_candle(ts_minutes_ago=45 - i) for i in range(45)]
    resampled = _resample_ohlcv(candles, "5m")
    assert 9 <= len(resampled) <= 10


def test_resample_1m_to_1h_basic():
    """45 根 1m K 线 → 1 根 1h K 线（同一小时内）。"""
    candles = [_make_candle(ts_minutes_ago=45 - i) for i in range(45)]
    resampled = _resample_ohlcv(candles, "1h")
    assert len(resampled) == 1


def test_resample_empty_returns_empty():
    assert _resample_ohlcv([], "5m") == []


def test_resample_bucket_ohlc_correct():
    """bucket 内 high = 最高 1m high, low = 最低 1m low, close = 最后一根 1m close。"""
    candles = []
    base_ts_ms = int(datetime.now(UTC).timestamp() // 300) * 300 * 1000  # 5min 对齐
    for i in range(5):
        ts = base_ts_ms - (5 - i) * 60 * 1000
        candles.append(
            {
                "ts": ts,
                "o": 50000 + i * 10,
                "h": 50100 + i * 5,
                "l": 49900 + i * 5,
                "c": 50050 + i,
                "vol": 10.0,
                "confirm": True,
            }
        )
    resampled = _resample_ohlcv(candles, "5m")
    assert len(resampled) == 1
    assert resampled[0]["h"] == 50100 + 4 * 5
    assert resampled[0]["l"] == 49900
    assert resampled[0]["c"] == 50050 + 4
    assert resampled[0]["vol"] == 50.0


def test_resample_1m_to_15m():
    """30 根 1m → 2 根 15m。"""
    candles = [_make_candle(ts_minutes_ago=30 - i) for i in range(30)]
    resampled = _resample_ohlcv(candles, "15m")
    assert 2 <= len(resampled) <= 3


def test_resample_handles_unsorted_input():
    """乱序输入应被正确 bucket(不影响结果)。"""
    candles = [_make_candle(ts_minutes_ago=i) for i in range(45)]  # 倒序
    resampled = _resample_ohlcv(candles, "5m")
    assert 9 <= len(resampled) <= 10


def test_resample_buckets_are_sorted_by_ts():
    """返回的 bucket 按 ts 升序。"""
    candles = [_make_candle(ts_minutes_ago=45 - i) for i in range(45)]
    resampled = _resample_ohlcv(candles, "5m")
    ts_list = [c["ts"] for c in resampled]
    assert ts_list == sorted(ts_list)


def test_resample_1m_to_1d_returns_at_least_one_bucket():
    """1m 数据量 < 1440 根时仍然输出可整除的 bucket。"""
    candles = [_make_candle(ts_minutes_ago=45 - i) for i in range(45)]
    resampled = _resample_ohlcv(candles, "1d")
    assert len(resampled) >= 1


def test_resample_preserves_open_of_first_candle():
    """bucket open = 该 bucket 第一根 1m K 线的 open。"""
    base_ts_ms = int(datetime.now(UTC).timestamp() // 300) * 300 * 1000
    candles = []
    for i in range(5):
        ts = base_ts_ms - (5 - i) * 60 * 1000
        candles.append({"ts": ts, "o": 50100 + i, "h": 50200, "l": 50000, "c": 50150, "vol": 10.0})
    resampled = _resample_ohlcv(candles, "5m")
    assert len(resampled) == 1
    # 第一根 o = 50100
    assert resampled[0]["o"] == 50100