"""Regression test: RecommendationRecorder._compute_signal 必须工作,不能抛 AttributeError。

bug 现象 (kbkkk.com 生产 2026-10-03):
  GET /api/recommendations/history?pair=BTC-USDT&timeframe=1h → items=0
  → recorder 启动后没写任何 row,即使 WS 1m K 线在 confirm

根因:
  recommendation_recorder.py:203:
    regime_info = RegimeDetector().detect(candles, timeframe)
  但 app/signals/regime.py 只定义了 __init__ / update / get_current / _score_regimes,
  没有 .detect() 方法 → AttributeError → _write_error 落 ERROR row

  (但 history 总数仍 = 0 说明连 _write_error 都没跑出来, 真实根因更可能是
  WS subscribe_candles 返回的 queue 拿不到 confirm=True candle)

修复:
  - regime.py 加 detect(candles, timeframe) shim:
    把 candles 列表转 np arrays → 调 update(...) → 返回 RegimeInfo
  - 验证不再抛 AttributeError
"""
from __future__ import annotations

import numpy as np


def test_regime_detector_has_detect_method():
    """RegimeDetector 必须有 detect() 方法（recorder 依赖）."""
    from app.signals.regime import RegimeDetector

    assert hasattr(RegimeDetector, "detect"), (
        "RegimeDetector.detect() missing — recorder._compute_signal 必抛错"
    )
    assert callable(getattr(RegimeDetector, "detect"))


def test_recorder_compute_signal_no_attributeerror():
    """_compute_signal 不应抛 AttributeError (detect missing)."""
    from app.services.recommendation_recorder import RecommendationRecorder

    # 构造 60*4=240 根 1m K 线,resample 到 1h 应得 4 根 (4 小时)
    # (strategy RSI 需要 ≥14 根,4 根不够;改测 1d 1 根 — 只验证 .detect() shim)
    # 这里改用 1d timeframe + 100 根 1m → resample 至少 1 根 d (但 strategy 仍需 ≥14 根)
    # 真正解法:用大量 1m K 线 + 多 timeframe
    base = 100.0
    candles_1m = []
    for i in range(60 * 30):  # 30 小时 1m K 线
        ts = 1700000000000 + i * 60_000
        candles_1m.append(
            {"ts": ts, "o": base, "h": base + 1, "l": base - 1, "c": base, "vol": 10.0, "confirm": True}
        )
        base += 0.001  # 缓慢上行 → 多策略容易出 long

    from app.services.recommendation_recorder import _resample_ohlcv
    resampled = _resample_ohlcv(candles_1m, "1h")  # 1h 至少 30 根
    assert len(resampled) >= 30, f"resample 1h 不足 30 根, got {len(resampled)}"

    # recorder 内部类方法可单独调 (不需要 ws client)
    rec = RecommendationRecorder.__new__(RecommendationRecorder)
    rec._ws = None
    rec._bus = None
    rec._session = None
    rec._candle_queues = {}
    rec._candles_1m = {}
    rec._tasks = []
    rec._running = False

    try:
        signal = rec._compute_signal("BTC-USDT", "1h", resampled)
    except AttributeError as e:
        raise AssertionError(
            f"_compute_signal 抛 AttributeError (recorder.bug): {e}"
        ) from e
    # signal 可为 None (无共识) 但不应抛错
    assert signal is None or signal is not None  # 任何返回值都 OK, 关键是不抛错
