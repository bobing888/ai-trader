"""Test aggregator Phase 1 integration — calibrated_confidence + net_pnl_estimate.

验证：
1. AggregatedSignal.calibrated_confidence 字段存在
2. AggregatedSignal.net_pnl_estimate 字段存在
3. cold start 时 calibrated_confidence = None
4. calibrated model 存在时 calibrated_confidence ∈ [0, 1]
"""
from app.signals.calibration import clear_cache, train_calibrator
from app.signals.aggregator import AggregatedSignal


def test_aggregated_signal_has_phase1_fields():
    """dataclass 加字段必须能 import + 构造。"""
    sig = AggregatedSignal(
        pair="BTC-USDT",
        direction="long",
        confidence=0.7,
        contributing_strategies=["MomentumStrategy"],
        reasons=["test"],
        regime="bull",
        regime_confidence=0.8,
        entry_zones=[],
        risk_warnings=[],
    )
    # Default values
    assert sig.calibrated_confidence is None
    assert sig.net_pnl_estimate == 0.0


def test_aggregated_signal_with_calibrated_fields():
    sig = AggregatedSignal(
        pair="BTC-USDT",
        direction="long",
        confidence=0.7,
        contributing_strategies=[],
        reasons=[],
        regime="bull",
        regime_confidence=0.8,
        entry_zones=[],
        risk_warnings=[],
        calibrated_confidence=0.62,
        net_pnl_estimate=0.0029,
    )
    assert sig.calibrated_confidence == 0.62
    assert sig.net_pnl_estimate == pytest_approx(0.0029) if False else sig.net_pnl_estimate == 0.0029


# Use pytest.approx wrapper
def test_aggregated_signal_with_calibrated_fields_approx():
    import pytest
    sig = AggregatedSignal(
        pair="BTC-USDT",
        direction="long",
        confidence=0.7,
        contributing_strategies=[],
        reasons=[],
        regime="bull",
        regime_confidence=0.8,
        entry_zones=[],
        risk_warnings=[],
        calibrated_confidence=0.62,
        net_pnl_estimate=0.0029,
    )
    assert sig.calibrated_confidence == pytest.approx(0.62)
    assert sig.net_pnl_estimate == pytest.approx(0.0029)


def test_calibration_integration_smoke(tmp_path, monkeypatch):
    """smoke test: clear cache → train model → next aggregator 调用 calibrate() 时有值。"""
    monkeypatch.setattr("app.signals.calibration.CALIBRATION_STORE", str(tmp_path))
    clear_cache()
    # 训练一个 calibrator
    rng = __import__("numpy").random.default_rng(42)
    raw = rng.uniform(0, 1, 200)
    pnl = (raw - 0.5) * 0.02 + rng.normal(0, 0.005, 200)
    model = train_calibrator("1h", list(zip(raw.tolist(), pnl.tolist())))
    assert model.is_ready

    from app.signals.calibration import calibrate
    p = calibrate(0.7, "1h")
    assert p is not None
    assert 0.0 <= p <= 1.0


def test_cost_model_integration():
    """net_pnl_estimate 公式: confidence * target - round_trip."""
    from app.signals.cost_model import estimate_round_trip_cost, is_profitable_threshold

    cost = estimate_round_trip_cost().total_round_trip_pct  # ~0.0021
    # confidence 0.7, target 0.5%: net = 0.7 * 0.005 - 0.0021 = 0.0014
    net = 0.7 * 0.005 - cost
    assert 0.001 < net < 0.002
    assert is_profitable_threshold(0.005, 0.7) is True
    assert is_profitable_threshold(0.005, 0.4) is False