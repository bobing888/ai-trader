"""Test cost_model — OKX fee + slippage + profitability threshold.

验证：
1. 默认费率（OKX taker 0.08%）
2. 往返 + 滑点
3. 环境变量可覆盖
4. profitability threshold 在低 confidence 下返回 False
"""
import pytest

from app.signals.cost_model import (
    estimate_cost,
    estimate_round_trip_cost,
    is_profitable_threshold,
    CostEstimate,
)


def test_okx_taker_fee_default():
    assert estimate_cost(side="entry") == pytest.approx(0.0008)
    assert estimate_cost(side="exit") == pytest.approx(0.0008)


def test_round_trip_includes_slippage():
    cost = estimate_round_trip_cost()
    # 0.0008 + 0.0008 + 0.0005 = 0.0021 (21 bps)
    assert cost.entry_fee_pct == pytest.approx(0.0008)
    assert cost.exit_fee_pct == pytest.approx(0.0008)
    assert cost.slippage_pct == pytest.approx(0.0005)
    assert cost.total_round_trip_pct == pytest.approx(0.0021)
    assert cost.total_round_trip_bps == pytest.approx(21.0)


def test_threshold_low_confidence_unprofitable():
    # target=0.5%, conf=0.5 → 0.25% < 0.21% round trip
    # (round_trip is 0.21%, expected edge is 0.25%, edge > cost)
    # so it IS profitable. Use conf=0.4 instead.
    assert is_profitable_threshold(target_pct=0.005, confidence=0.4) is False


def test_threshold_high_confidence_profitable():
    # target=0.5%, conf=0.7 → 0.35% > 0.21% round trip
    assert is_profitable_threshold(target_pct=0.005, confidence=0.7) is True


def test_cost_overridable_via_env(monkeypatch):
    monkeypatch.setenv("OKX_TAKER_FEE_BPS", "10.0")
    # Reimport cost_model to pick up new env var
    import importlib
    import app.signals.cost_model as cm
    importlib.reload(cm)
    assert cm.estimate_cost(side="entry") == pytest.approx(0.001)
    # Cleanup — reset module state for other tests
    monkeypatch.delenv("OKX_TAKER_FEE_BPS", raising=False)
    importlib.reload(cm)


def test_cost_estimate_dataclass():
    ce = CostEstimate(0.001, 0.001, 0.0005, 0.0025)
    assert ce.total_round_trip_bps == 25.0
    assert isinstance(ce, CostEstimate)