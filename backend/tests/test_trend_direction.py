"""test_trend_direction — derive_signal_direction() 的单元测试

直接 import analytics.trend（绕过 app.main / db 依赖）。
"""

import pytest
from app.analytics.trend import derive_signal_direction, multi_indicator_confluence
import numpy as np


class TestDeriveSignalDirection:
    """方向票数逻辑测试"""

    def test_long_when_3_plus_bullish_votes(self):
        """MA30 above + MACD bullish + RSI neutral + PDI > NDI → long"""
        direction = derive_signal_direction(
            ma30_state="above",
            macd_status="bullish_cross",
            rsi_zone="neutral",
            pdi=30.0,
            ndi=15.0,
        )
        assert direction == "long"

    def test_long_above_zero_macd(self):
        """MACD above_zero 仍是 long"""
        direction = derive_signal_direction(
            ma30_state="cross_above",
            macd_status="above_zero",
            rsi_zone="neutral",
            pdi=25.0,
            ndi=10.0,
        )
        assert direction == "long"

    def test_short_when_3_plus_bearish_votes(self):
        """MA30 below + MACD bearish + RSI neutral + PDI < NDI → short"""
        direction = derive_signal_direction(
            ma30_state="below",
            macd_status="bearish_cross",
            rsi_zone="neutral",
            pdi=10.0,
            ndi=30.0,
        )
        assert direction == "short"

    def test_short_below_zero_macd(self):
        """MACD below_zero 配合其他空头信号 → short"""
        direction = derive_signal_direction(
            ma30_state="below",
            macd_status="below_zero",
            rsi_zone="neutral",
            pdi=8.0,
            ndi=28.0,
        )
        assert direction == "short"

    def test_mixed_when_bullish_but_rsi_overbought(self):
        """票数够 long 但 RSI 超买 → mixed（防追高）"""
        direction = derive_signal_direction(
            ma30_state="above",
            macd_status="bullish_cross",
            rsi_zone="overbought",   # 超买 → 抑制做多
            pdi=30.0,
            ndi=15.0,
        )
        assert direction == "mixed"

    def test_mixed_when_5_neutral_votes(self):
        """所有信号 neutral → mixed"""
        direction = derive_signal_direction(
            ma30_state="above",
            macd_status="above_zero",
            rsi_zone="neutral",
            pdi=10.0,
            ndi=10.0,   # PDI == NDI，无方向
        )
        assert direction == "mixed"

    def test_mixed_when_insufficient_bullish_votes(self):
        """长着像 long 但只有 2 票 → mixed"""
        direction = derive_signal_direction(
            ma30_state="above",
            macd_status="above_zero",
            rsi_zone="neutral",
            pdi=10.0,   # PDI < NDI
            ndi=20.0,
        )
        assert direction == "mixed"

    def test_mixed_when_insufficient_bearish_votes(self):
        """长着像 short 但只有 2 票 → mixed"""
        direction = derive_signal_direction(
            ma30_state="below",
            macd_status="below_zero",
            rsi_zone="neutral",
            pdi=20.0,   # PDI > NDI
            ndi=10.0,
        )
        assert direction == "mixed"


class TestSignalDirectionInConfluenceResponse:
    """multi_indicator_confluence() 返回值包含 signal_direction"""

    def test_confluence_has_signal_direction_key(self):
        """确认 multi_indicator_confluence 返回 dict 中有 signal_direction"""
        # 生成最小合法 K 线数据
        n = 50
        close = np.linspace(100, 110, n)
        high = close + 1
        low = close - 1
        volume = np.full(n, 1_000_000.0)

        result = multi_indicator_confluence(high, low, close, volume)

        assert "signal_direction" in result, "返回 dict 必须包含 signal_direction"
        assert result["signal_direction"] in ("long", "short", "mixed")
