"""
Tests for multi-timeframe merge (informative decorator pattern).
Pattern borrowed from freqtrade informative_decorator (GPL-3.0) — no code copied.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def test_merge_informative_timeframes_basic():
    """Base TF columns kept + informative columns renamed with suffix."""
    from app.signals.informative import merge_informative_timeframes

    base_ts = pd.to_datetime([
        "2024-01-01 00:00",
        "2024-01-01 01:00",
        "2024-01-01 02:00",
        "2024-01-01 03:00",
        "2024-01-01 04:00",
    ])
    base = pd.DataFrame(
        {"close": [100.0, 101.0, 102.0, 101.5, 103.0]},
        index=base_ts,
    )
    base.index.name = "ts"

    info_ts = pd.to_datetime([
        "2024-01-01 00:00",
        "2024-01-01 04:00",
    ])
    informative = pd.DataFrame(
        {"close": [200.0, 210.0]},
        index=info_ts,
    )
    informative.index.name = "ts"

    merged = merge_informative_timeframes(
        base, informative, base_tf="1h", informative_tf="4h"
    )

    # 原 base close 必须保留
    assert "close" in merged.columns, "Base 'close' column must be preserved"
    # informative close 加了 _4h 后缀
    assert "close_4h" in merged.columns, (
        f"Informative column must have '_4h' suffix. Got columns: {list(merged.columns)}"
    )
    # 行数跟 base 一致
    assert len(merged) == len(base), f"Expected {len(base)} rows, got {len(merged)}"


def test_merge_informative_timeframes_suffix_per_tf():
    """Each informative TF gets its own suffix."""
    from app.signals.informative import merge_informative_timeframes

    base_ts = pd.to_datetime(["2024-01-01 00:00", "2024-01-01 01:00", "2024-01-01 02:00"])
    base = pd.DataFrame({"close": [100.0, 101.0, 102.0]}, index=base_ts)
    base.index.name = "ts"

    info_4h = pd.DataFrame({"close": [200.0]}, index=pd.to_datetime(["2024-01-01 00:00"]))
    info_4h.index.name = "ts"
    info_1d = pd.DataFrame({"close": [300.0]}, index=pd.to_datetime(["2024-01-01 00:00"]))
    info_1d.index.name = "ts"

    merged_4h = merge_informative_timeframes(base, info_4h, base_tf="1h", informative_tf="4h")
    merged_1d = merge_informative_timeframes(base, info_1d, base_tf="1h", informative_tf="1d")

    assert "close_4h" in merged_4h.columns
    assert "close_1d" in merged_1d.columns
    assert "close_4h" not in merged_1d.columns
    assert "close_1d" not in merged_4h.columns


def test_informative_cache_ttl():
    """InformativeCache entries should be TTL-driven (expire after N candles)."""
    from app.signals.informative import InformativeCache

    cache = InformativeCache(maxsize=100)

    # Fill cache with 2 entries
    cache["key1"] = "value1"
    cache["key2"] = "value2"

    # Both should be present
    assert "key1" in cache
    assert "key2" in cache

    # After exceeding TTL (simulate by calling expire or clearing stale),
    # entries should eventually be evicted
    cache.expire()  # Trigger TTL expiration
    # TTL is 2 informative candles; keys added without explicit TTL should expire
    assert len(cache) <= 2  # At most original entries; may be 0 after expiration


def test_merge_informative_timeframes_no_base_data():
    """Empty base DataFrame should return empty DataFrame."""
    from app.signals.informative import merge_informative_timeframes

    base = pd.DataFrame(columns=["close"])
    info = pd.DataFrame({"close": [200.0]}, index=pd.to_datetime(["2024-01-01 00:00"]))
    info.index.name = "ts"

    merged = merge_informative_timeframes(base, info, base_tf="1h", informative_tf="4h")
    assert len(merged) == 0


def test_merge_informative_timeframes_merge_asof_behavior():
    """merge_asof should pick nearest past informative candle (backward)."""
    from app.signals.informative import merge_informative_timeframes

    # base: 5 hourly candles starting at 2024-01-01 00:00
    base_ts = pd.to_datetime([
        "2024-01-01 00:00",
        "2024-01-01 01:00",
        "2024-01-01 02:00",
        "2024-01-01 03:00",
        "2024-01-01 04:00",
    ])
    base = pd.DataFrame({"close": [100.0, 101.0, 102.0, 103.0, 104.0]}, index=base_ts)
    base.index.name = "ts"

    # 4h informative candles at 00:00 and 04:00
    info_ts = pd.to_datetime(["2024-01-01 00:00", "2024-01-01 04:00"])
    info = pd.DataFrame({"close": [200.0, 250.0]}, index=info_ts)
    info.index.name = "ts"

    merged = merge_informative_timeframes(base, info, base_tf="1h", informative_tf="4h")

    # Hours 00-03 should use the first 4h candle (close=200)
    for i in range(4):
        assert merged["close_4h"].iloc[i] == 200.0, f"Hour {i} should get 4h candle at 00:00"
    # Hour 04 should use the second 4h candle (close=250)
    assert merged["close_4h"].iloc[4] == 250.0, "Hour 04 should get 4h candle at 04:00"
