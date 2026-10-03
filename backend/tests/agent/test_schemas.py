"""Tests for backend.app.agent.schemas — 研判报告 + 第二意见推荐单.

覆盖（spec §9 验证清单）：
  - BTC + ETH only（btc-eth-scope Rule 1 强制）
  - Timeframe 必须是 5m / 15m / 1h / 1d
  - Default analysis_status = SUCCESS
  - AgentRecommendation source 固定为 'agent'
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.schemas import (
    AgentRecommendation,
    ALLOWED_PAIRS,
    ALLOWED_REGIMES,
    ALLOWED_TIMEFRAMES,
    AnalysisReport,
    AnalysisStatus,
    Direction,
)


# === Fixtures ===

def _valid_report_kwargs(**overrides) -> dict:
    """生成 AnalysisReport 合规默认 kwargs"""
    base = {
        "pair": "BTC-USDT",
        "timeframe": "1h",
        "regime": "bull",
        "regime_confidence": 0.7,
        "reasoning": "BTC 1h 处于多头格局，ADX>25 + MACD 金叉 + 成交量放大。",
    }
    base.update(overrides)
    return base


def _valid_recommendation_kwargs(**overrides) -> dict:
    base = {
        "pair": "ETH-USDT",
        "timeframe": "15m",
        "direction": "short",
        "confidence": 0.6,
        "rationale": "ETH 15m 出现顶背离 + 量能萎缩，建议短空。",
    }
    base.update(overrides)
    return base


# === Constants ===

class TestConstants:
    def test_allowed_pairs(self):
        assert ALLOWED_PAIRS == ("BTC-USDT", "ETH-USDT")

    def test_allowed_timeframes(self):
        assert ALLOWED_TIMEFRAMES == ("5m", "15m", "1h", "1d")

    def test_allowed_regimes(self):
        assert ALLOWED_REGIMES == ("bull", "bear", "choppy", "crisis")


# === AnalysisReport ===

class TestAnalysisReportImportable:
    """Task 1 Step 1 — 初始 fail 测试，现已 pass（占位 + import 验证）"""

    def test_analysis_report_importable(self):
        from app.agent import AnalysisReport as Imported
        assert Imported is AnalysisReport

    def test_agent_recommendation_importable(self):
        from app.agent import AgentRecommendation as Imported
        assert Imported is AgentRecommendation


class TestAnalysisReportDefaults:
    def test_default_status_is_success(self):
        report = AnalysisReport(**_valid_report_kwargs())
        assert report.analysis_status == AnalysisStatus.SUCCESS

    def test_default_created_at_is_utc(self):
        from datetime import timezone
        report = AnalysisReport(**_valid_report_kwargs())
        assert report.created_at.tzinfo is not None
        assert report.created_at.tzinfo == timezone.utc

    def test_raw_llm_response_default_none(self):
        report = AnalysisReport(**_valid_report_kwargs())
        assert report.raw_llm_response is None

    def test_key_observations_default_empty(self):
        report = AnalysisReport(**_valid_report_kwargs())
        assert report.key_observations == []
        assert report.risks == []


class TestAnalysisReportPairScope:
    """Task 2 — BTC/ETH only（btc-eth-scope Rule 1）"""

    @pytest.mark.parametrize("pair", ["BTC-USDT", "ETH-USDT"])
    def test_btc_and_eth_accepted(self, pair):
        report = AnalysisReport(**_valid_report_kwargs(pair=pair))
        assert report.pair == pair

    @pytest.mark.parametrize("pair", ["SOL-USDT", "DOGE-USDT", "BNB-USDT", "XRP-USDT", "PEPE-USDT"])
    def test_other_pairs_rejected(self, pair):
        with pytest.raises(ValidationError) as exc_info:
            AnalysisReport(**_valid_report_kwargs(pair=pair))
        # pydantic v2 会因为 Literal 不匹配直接拒
        assert "pair" in str(exc_info.value).lower() or pair in str(exc_info.value)


class TestAnalysisReportTimeframe:
    """Task 2 — timeframe 强约束"""

    @pytest.mark.parametrize("tf", ["5m", "15m", "1h", "1d"])
    def test_allowed_timeframes_accepted(self, tf):
        report = AnalysisReport(**_valid_report_kwargs(timeframe=tf))
        assert report.timeframe == tf

    @pytest.mark.parametrize("tf", ["1m", "4h", "30m", "2h", "1w"])
    def test_other_timeframes_rejected(self, tf):
        with pytest.raises(ValidationError):
            AnalysisReport(**_valid_report_kwargs(timeframe=tf))


class TestAnalysisReportRegime:
    """Task 2 — regime 强约束"""

    @pytest.mark.parametrize("regime", ["bull", "bear", "choppy", "crisis"])
    def test_all_regimes_accepted(self, regime):
        report = AnalysisReport(**_valid_report_kwargs(regime=regime))
        assert report.regime == regime

    def test_invalid_regime_rejected(self):
        with pytest.raises(ValidationError):
            AnalysisReport(**_valid_report_kwargs(regime="sideways"))


class TestAnalysisReportConfidence:
    def test_confidence_zero_accepted(self):
        report = AnalysisReport(**_valid_report_kwargs(regime_confidence=0.0))
        assert report.regime_confidence == 0.0

    def test_confidence_one_accepted(self):
        report = AnalysisReport(**_valid_report_kwargs(regime_confidence=1.0))
        assert report.regime_confidence == 1.0

    def test_confidence_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            AnalysisReport(**_valid_report_kwargs(regime_confidence=1.5))
        with pytest.raises(ValidationError):
            AnalysisReport(**_valid_report_kwargs(regime_confidence=-0.1))


class TestAnalysisReportFallbackStatus:
    """Task 2 — 降级状态支持"""

    def test_fallback_status_accepted(self):
        report = AnalysisReport(
            **_valid_report_kwargs(),
            analysis_status=AnalysisStatus.FALLBACK,
        )
        assert report.analysis_status == AnalysisStatus.FALLBACK

    def test_parse_error_status_accepted(self):
        report = AnalysisReport(
            **_valid_report_kwargs(
                analysis_status=AnalysisStatus.PARSE_ERROR,
                raw_llm_response='{"invalid": "response"}',
            ),
        )
        assert report.analysis_status == AnalysisStatus.PARSE_ERROR
        assert report.raw_llm_response is not None


# === AgentRecommendation ===

class TestAgentRecommendationDefaults:
    def test_source_defaults_to_agent(self):
        rec = AgentRecommendation(**_valid_recommendation_kwargs())
        assert rec.source == "agent"

    def test_direction_enum_value(self):
        rec = AgentRecommendation(**_valid_recommendation_kwargs())
        assert rec.direction == Direction.SHORT


class TestAgentRecommendationScope:
    @pytest.mark.parametrize("pair", ["BTC-USDT", "ETH-USDT"])
    def test_btc_eth_accepted(self, pair):
        rec = AgentRecommendation(**_valid_recommendation_kwargs(pair=pair))
        assert rec.pair == pair

    @pytest.mark.parametrize("pair", ["SOL-USDT", "LINK-USDT"])
    def test_other_pairs_rejected(self, pair):
        with pytest.raises(ValidationError):
            AgentRecommendation(**_valid_recommendation_kwargs(pair=pair))

    @pytest.mark.parametrize("tf", ["5m", "15m", "1h", "1d"])
    def test_allowed_timeframes_accepted(self, tf):
        rec = AgentRecommendation(**_valid_recommendation_kwargs(timeframe=tf))
        assert rec.timeframe == tf

    def test_invalid_timeframe_rejected(self):
        with pytest.raises(ValidationError):
            AgentRecommendation(**_valid_recommendation_kwargs(timeframe="4h"))


class TestAgentRecommendationDirection:
    @pytest.mark.parametrize("direction", ["long", "short", "neutral"])
    def test_all_directions_accepted(self, direction):
        rec = AgentRecommendation(**_valid_recommendation_kwargs(direction=direction))
        assert rec.direction.value == direction

    def test_invalid_direction_rejected(self):
        with pytest.raises(ValidationError):
            AgentRecommendation(**_valid_recommendation_kwargs(direction="up"))