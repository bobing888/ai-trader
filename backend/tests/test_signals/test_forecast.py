"""
Test suite for ML forecast layer (Phase 5).
Tests:
1. IsotonicRegression calibration is monotonic
2. ForecastModel trains + saves + loads
3. Aggregator's ML blend path works (forecast_override shifts output)
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import main as unittest_main
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import numpy as np


class TestIsotonicRegressionMonotonicity(TestCase):
    """Test that IsotonicRegression produces monotonic output."""

    def test_monotonic_on_random_data(self):
        """PAVA should produce non-decreasing y values."""
        from app.signals.forecast import IsotonicRegression

        np.random.seed(42)
        X = np.sort(np.random.rand(200))
        y = np.random.rand(200)

        cal = IsotonicRegression(out_of_bounds="clip")
        cal.fit(X, y)

        # Check that y_thresholds_ is non-decreasing
        diffs = np.diff(cal.y_thresholds_)
        monotonic = np.all(diffs >= -1e-9)
        self.assertTrue(monotonic, f"y_thresholds_ not monotonic: {cal.y_thresholds_[:20]}")

    def test_monotonic_on_worst_case(self):
        """Worst case: monotonically decreasing y (should be flattened by PAVA)."""
        from app.signals.forecast import IsotonicRegression

        X = np.arange(100, dtype=float)
        y = np.linspace(1.0, 0.0, 100)  # strictly decreasing

        cal = IsotonicRegression(out_of_bounds="clip")
        cal.fit(X, y)
        diffs = np.diff(cal.y_thresholds_)
        monotonic = np.all(diffs >= -1e-9)
        self.assertTrue(monotonic, "PAVA failed on strictly decreasing targets")

    def test_transform_clip(self):
        """Test that out_of_bounds=clip clips to [y[0], y[-1]]."""
        from app.signals.forecast import IsotonicRegression

        np.random.seed(42)
        X = np.sort(np.random.rand(50) * 10)
        y = np.random.rand(50)

        cal = IsotonicRegression(out_of_bounds="clip")
        cal.fit(X, y)

        pred = cal.transform(np.array([-5.0, 0.0, 5.0, 15.0]))
        self.assertFalse(np.isnan(pred[0]), "clip should not produce NaN for x < X_min")
        self.assertFalse(np.isnan(pred[-1]), "clip should not produce NaN for x > X_max")
        self.assertAlmostEqual(pred[0], cal.y_thresholds_[0], places=5)
        self.assertAlmostEqual(pred[-1], cal.y_thresholds_[-1], places=5)


class TestForecastModelSaveLoad(TestCase):
    """Test that ForecastModel can be saved and loaded."""

    def test_save_load_roundtrip(self):
        """Test that saving and loading preserves model parameters."""
        from app.signals.forecast import ForecastModel, IsotonicRegression

        cal = IsotonicRegression(out_of_bounds="clip")
        np.random.seed(42)
        cal.fit(np.random.rand(100), np.random.rand(100))

        model = ForecastModel(
            symbol="BTC-USDT",
            timeframe="1h",
            horizon=5,
            lgbm_model={"n_trees": 10},  # dummy
            calibrator=cal,
            feature_names=["f1", "f2"],
            train_size=100,
            val_size=20,
        )

        import tempfile, joblib
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
            tmp_path = Path(f.name)

        try:
            model.save(tmp_path)
            loaded = ForecastModel.load(tmp_path)

            self.assertEqual(loaded.symbol, "BTC-USDT")
            self.assertEqual(loaded.timeframe, "1h")
            self.assertEqual(loaded.horizon, 5)
            self.assertEqual(loaded.feature_names, ["f1", "f2"])
            self.assertEqual(loaded.train_size, 100)
            self.assertIsNotNone(loaded.calibrator)
            self.assertTrue(np.allclose(
                loaded.calibrator.y_thresholds_,
                model.calibrator.y_thresholds_,
            ))
        finally:
            tmp_path.unlink(missing_ok=True)


class TestAggregatorMLBlend(TestCase):
    """Test that aggregator's forecast_override blends correctly."""

    def test_forecast_override_shifts_confidence(self):
        """forecast_override=0.7 should produce higher confidence than rule alone."""
        from app.signals import Regime, SignalAggregator, STRATEGY_INSTANCES
        from app.signals.strategy_pool import StrategyResult, StrategyId

        agg = SignalAggregator()

        # Create a dummy strategy result
        dummy_result = StrategyResult(
            strategy=StrategyId.MULTI_TF,
            pair="BTC-USDT",
            timeframe="1h",
            direction="long",
            confidence=0.60,
            reasons=("test",),
            suitable_regimes=frozenset(["bull"]),
        )

        # Without ML
        sig_no_ml = agg.aggregate(
            strategy_results=[dummy_result],
            regime=Regime.BULL,
            regime_confidence=0.8,
            timeframe="1h",
        )

        # With ML forecast_override=0.7, ml_weight=0.4
        # Expected: 0.6 * rule_conf + 0.4 * 0.7
        sig_with_ml = agg.aggregate(
            strategy_results=[dummy_result],
            regime=Regime.BULL,
            regime_confidence=0.8,
            timeframe="1h",
            forecast_override=0.7,
            ml_weight=0.4,
        )

        self.assertIsNotNone(sig_no_ml)
        self.assertIsNotNone(sig_with_ml)
        self.assertIsNotNone(sig_with_ml)

        # ML blend should shift confidence upward when override > rule_conf
        self.assertGreater(
            sig_with_ml.confidence,
            sig_no_ml.confidence,
            "ML override should increase confidence when override > rule",
        )

        # Check the math: 0.6 * 0.6 + 0.4 * 0.7 = 0.36 + 0.28 = 0.64
        expected = 0.6 * sig_no_ml.confidence + 0.4 * 0.7
        self.assertAlmostEqual(
            sig_with_ml.confidence,
            expected,
            places=3,
            msg=f"Expected {expected}, got {sig_with_ml.confidence}",
        )

        # Verify fields are recorded
        self.assertEqual(sig_with_ml.forecast_override, 0.7)
        self.assertEqual(sig_with_ml.ml_weight_used, 0.4)

    def test_forecast_override_none_unchanged(self):
        """When forecast_override=None, confidence should be same as rule-only."""
        from app.signals import Regime, SignalAggregator, STRATEGY_INSTANCES
        from app.signals.strategy_pool import StrategyResult, StrategyId

        agg = SignalAggregator()
        dummy_result = StrategyResult(
            strategy=StrategyId.MOMENTUM,
            pair="ETH-USDT",
            timeframe="4h",
            direction="short",
            confidence=0.55,
            reasons=("test",),
            suitable_regimes=frozenset(["bear"]),
        )

        sig_no_ml = agg.aggregate(
            strategy_results=[dummy_result],
            regime=Regime.BEAR,
            regime_confidence=0.7,
            timeframe="4h",
        )

        sig_with_none = agg.aggregate(
            strategy_results=[dummy_result],
            regime=Regime.BEAR,
            regime_confidence=0.7,
            timeframe="4h",
            forecast_override=None,
        )

        self.assertIsNotNone(sig_no_ml)
        self.assertIsNotNone(sig_with_none)
        self.assertEqual(sig_no_ml.confidence, sig_with_none.confidence)

    def test_forecast_override_lowered_confidence(self):
        """When override < rule_conf, ML should pull confidence down."""
        from app.signals import Regime, SignalAggregator
        from app.signals.strategy_pool import StrategyResult, StrategyId

        agg = SignalAggregator()
        dummy_result = StrategyResult(
            strategy=StrategyId.VOLATILITY,
            pair="SOL-USDT",
            timeframe="1d",
            direction="long",
            confidence=0.80,
            reasons=("test",),
            suitable_regimes=frozenset(["bull", "choppy"]),
        )

        sig_rule = agg.aggregate(
            strategy_results=[dummy_result],
            regime=Regime.BULL,
            regime_confidence=0.9,
            timeframe="1d",
        )

        sig_ml_low = agg.aggregate(
            strategy_results=[dummy_result],
            regime=Regime.BULL,
            regime_confidence=0.9,
            timeframe="1d",
            forecast_override=0.3,  # Low ML confidence
            ml_weight=0.4,
        )

        self.assertIsNotNone(sig_rule)
        self.assertIsNotNone(sig_ml_low)
        # 0.6 * 0.80 + 0.4 * 0.30 = 0.48 + 0.12 = 0.60
        self.assertLess(
            sig_ml_low.confidence,
            sig_rule.confidence,
            "ML override below rule should lower confidence",
        )


class TestFeatureSet(TestCase):
    """Test FeatureSet array conversion."""

    def test_to_array_shape(self):
        """FeatureSet.to_array() should produce correct shape."""
        from app.signals.forecast import FeatureSet

        fs = FeatureSet(
            momentum_dir=1.0, momentum_conf=0.8,
            reversal_dir=-1.0, reversal_conf=0.7,
            breakout_dir=1.0, breakout_conf=0.6,
            volatility_dir=0.0, volatility_conf=0.0,
            sentiment_dir=0.0, sentiment_conf=0.0,
            volume_dir=0.0, volume_conf=0.0,
            multi_tf_dir=1.0, multi_tf_conf=0.85,
            confluence_dir=0.0, confluence_conf=0.0,
            prob_bull=0.6, prob_bear=0.1, prob_choppy=0.2, prob_crisis=0.1,
            rsi=55.0, macd_signal=1.0, atr_pct=0.02,
            hour_of_day=14.0, day_of_week=3.0,
            ret_1=0.01, ret_5=0.03, ret_20=0.10, vol_ratio=1.2,
        )
        arr = fs.to_array()
        self.assertEqual(arr.shape, (28,), f"Expected 28 features, got {arr.shape}")
        self.assertEqual(len(arr), 28)


if __name__ == "__main__":
    unittest_main(verbosity=2)
