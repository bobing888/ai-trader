"""验证 _scan_with_boundary_check 只在跨桶时触发 _scan_one"""
import asyncio
from unittest.mock import AsyncMock
import sys
sys.path.insert(0, "backend")
from app.services.recommendation_recorder import RecommendationRecorder

async def test_first_call_triggers():
    """第一次调用应该触发所有 tf scan"""
    rec = RecommendationRecorder.__new__(RecommendationRecorder)
    rec._last_bucket_ts = {}
    rec._scan_one = AsyncMock()
    rec.settings_recommendation_timeframes = None
    # patch settings.recommendation_timeframes
    import app.config as cfg
    cfg.settings.recommendation_timeframes = ["5m", "15m", "1h", "1d"]

    ts_ms = 1759487640000
    await rec._scan_with_boundary_check("BTC-USDT", ts_ms)
    assert rec._scan_one.await_count == 4, f"Expected 4, got {rec._scan_one.await_count}"
    print("PASS first call: 4 scan triggered")

async def test_same_bucket_no_scan():
    rec = RecommendationRecorder.__new__(RecommendationRecorder)
    rec._last_bucket_ts = {}
    rec._scan_one = AsyncMock()
    await rec._scan_with_boundary_check("BTC-USDT", 1759487640000)
    await rec._scan_with_boundary_check("BTC-USDT", 1759487660000)  # +20s, same 5m
    assert rec._scan_one.await_count == 4, f"Expected 4, got {rec._scan_one.await_count}"
    print("PASS same bucket: only 4 scan (first init)")

async def test_cross_5m_bucket():
    rec = RecommendationRecorder.__new__(RecommendationRecorder)
    rec._last_bucket_ts = {}
    rec._scan_one = AsyncMock()
    await rec._scan_with_boundary_check("BTC-USDT", 1759487640000)
    await rec._scan_with_boundary_check("BTC-USDT", 1759487700000)  # +1min, cross 5m
    assert rec._scan_one.await_count == 5, f"Expected 5, got {rec._scan_one.await_count}"
    print("PASS cross 5m bucket: +1 scan")

async def test_cross_15m_bucket():
    rec = RecommendationRecorder.__new__(RecommendationRecorder)
    rec._last_bucket_ts = {}
    rec._scan_one = AsyncMock()
    # 12:30 → 12:45 跨 5m 1 次（12:30→12:45 candle 进 12:45 bucket）
    # 跨 15m 1 次（12:30→12:45 candle 进 12:45 bucket）
    # +2 = 6 total
    await rec._scan_with_boundary_check("BTC-USDT", 1759487400000)  # 12:30
    await rec._scan_with_boundary_check("BTC-USDT", 1759488300000)  # 12:45
    assert rec._scan_one.await_count == 6, f"Expected 6, got {rec._scan_one.await_count}"
    print("PASS cross 15m bucket: +2 scans (1×5m + 1×15m)")

async def test_cross_1h_bucket():
    rec = RecommendationRecorder.__new__(RecommendationRecorder)
    rec._last_bucket_ts = {}
    rec._scan_one = AsyncMock()
    await rec._scan_with_boundary_check("BTC-USDT", 1759487640000)  # 12:34
    await rec._scan_with_boundary_check("BTC-USDT", 1759490400000)  # 13:00
    # cross 5m + 15m + 1h
    assert rec._scan_one.await_count == 7, f"Expected 7, got {rec._scan_one.await_count}"
    print("PASS cross 1h bucket: +3 scans (5m+15m+1h)")

async def test_cross_1d_bucket():
    rec = RecommendationRecorder.__new__(RecommendationRecorder)
    rec._last_bucket_ts = {}
    rec._scan_one = AsyncMock()
    await rec._scan_with_boundary_check("BTC-USDT", 1759487640000)  # day X 12:34
    await rec._scan_with_boundary_check("BTC-USDT", 1759574040000)  # day X+1 12:34
    # cross 5m + 15m + 1h + 1d = 4
    assert rec._scan_one.await_count == 8, f"Expected 8, got {rec._scan_one.await_count}"
    print("PASS cross 1d bucket: +4 scans (all)")

async def main():
    await test_first_call_triggers()
    await test_same_bucket_no_scan()
    await test_cross_5m_bucket()
    await test_cross_15m_bucket()
    await test_cross_1h_bucket()
    await test_cross_1d_bucket()
    print("\nALL 6 tests passed")

asyncio.run(main())