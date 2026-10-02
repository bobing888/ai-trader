"""Test calibration — per-timeframe Isotonic regression.

验证：
1. 喂 1000 个 synthetic sample → Brier < 0.15
2. per-tf separation: 1h 和 1m 各自独立
3. cold start: 无 model 时返 None
4. 模型持久化到 .pkl 后再加载能复用
"""
import numpy as np
import pytest

from app.signals.calibration import (
    train_calibrator,
    calibrate,
    get_calibrator,
    CalibrationModel,
)


@pytest.fixture
def store_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("app.signals.calibration.CALIBRATION_STORE", str(tmp_path))
    return tmp_path


def test_train_calibrator_on_synthetic_data(store_dir):
    """1000 个 sample：raw_conf 与 win 强正相关 → 校准后 Brier < 0.15"""
    rng = np.random.default_rng(42)
    raw = rng.uniform(0, 1, 1000)
    pnl = (raw - 0.5) * 0.02 + rng.normal(0, 0.005, 1000)
    samples = list(zip(raw.tolist(), pnl.tolist()))

    model = train_calibrator(timeframe="1h", samples=samples)

    assert model.timeframe == "1h"
    assert model.is_ready is True
    assert model.train_size == 1000
    assert model.train_brier_score < 0.15
    assert model.trained_at is not None


def test_calibrate_returns_calibrated_value(store_dir):
    rng = np.random.default_rng(42)
    raw = rng.uniform(0, 1, 200)
    pnl = (raw - 0.5) * 0.02 + rng.normal(0, 0.005, 200)
    samples = list(zip(raw.tolist(), pnl.tolist()))

    train_calibrator(timeframe="5m", samples=samples)

    result = calibrate(raw_confidence=0.7, timeframe="5m")
    assert result is not None
    assert 0.0 <= result <= 1.0
    # 高 raw conf 应该 → 高 calibrated (PnL>mid)
    result_high = calibrate(raw_confidence=0.9, timeframe="5m")
    result_low = calibrate(raw_confidence=0.3, timeframe="5m")
    assert result_high > result_low


def test_calibrate_returns_none_when_cold_start(store_dir):
    """calibrator 未训练 → 返 None（前端显示「calibrating...」）"""
    result = calibrate(raw_confidence=0.7, timeframe="15m")
    assert result is None


def test_per_timeframe_separation(store_dir):
    """1h 模型和 1m 模型必须各自独立（不同 .pkl 文件）。"""
    # 1h: conf=0.7 → win
    samples_1h = [
        (0.5, 0.001), (0.6, 0.002), (0.7, 0.005),
        (0.8, 0.008), (0.9, 0.012),
    ] * 30  # 150 总样本
    # 1m: conf=0.7 → loss
    samples_1m = [
        (0.5, -0.001), (0.6, -0.001), (0.7, -0.001),
        (0.8, 0.001), (0.9, 0.005),
    ] * 30  # 150 总样本

    train_calibrator("1h", samples_1h)
    train_calibrator("1m", samples_1m)

    model_1h = get_calibrator("1h")
    model_1m = get_calibrator("1m")
    assert model_1h is not None
    assert model_1m is not None
    assert model_1h.timeframe == "1h"
    assert model_1m.timeframe == "1m"

    p_1h = calibrate(0.7, "1h")
    p_1m = calibrate(0.7, "1m")
    assert p_1h is not None and p_1m is not None
    # 1h 中 0.7 conf 是 win，1m 中 0.7 conf 是 loss → 1h > 1m
    assert p_1h > p_1m


def test_calibrator_persisted_and_reloadable(store_dir):
    """训练后 .pkl 存在；卸载内存 cache 后从磁盘重载依然工作。"""
    samples = [(0.5, 0.001), (0.7, 0.005), (0.9, 0.012)] * 40  # 120 样本
    train_calibrator("4h", samples)

    pkl_path = store_dir / "4h.pkl"
    assert pkl_path.exists()

    # 清空内存 cache,模拟新进程启动
    from app.signals import calibration as cm
    cm._calibrators.clear()

    p1 = calibrate(0.7, "4h")
    assert p1 is not None

    # 删掉磁盘
    pkl_path.unlink()
    cm._calibrators.clear()
    p2 = calibrate(0.7, "4h")
    assert p2 is None  # 冷启动


def test_train_calibrator_too_few_samples_raises(store_dir):
    """< 10 样本应当报错，避免低样本污染模型。"""
    with pytest.raises(ValueError, match="need ≥10 samples"):
        train_calibrator("1d", [(0.5, 0.001)] * 5)


def test_calibration_monotonic_non_decreasing(store_dir):
    """校准输出必须 monotonic-non-decreasing（Isotonic 性质）。"""
    # 构造明显胜 30 负 30 正的样本（中间过渡）
    samples = []
    for i in range(100):
        raw = i / 99.0  # 0..1
        pnl = (raw - 0.6) * 0.02  # > 0.6 时 win
        samples.append((raw, pnl))
    train_calibrator("15m", samples)
    # Isotonic regression 性质：calibrated 必须 monotonic-non-decreasing
    raws = [0.1, 0.3, 0.5, 0.7, 0.9]
    preds = [calibrate(c, "15m") for c in raws]
    assert all(p is not None for p in preds)
    for i in range(len(preds) - 1):
        assert preds[i] <= preds[i + 1], f"not monotonic at {i}: {preds}"