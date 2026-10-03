"""Trend Analysis Agent — 趋势研判智能体（第二意见层）

本模块是 ai-trader 的"自然语言研判"层，**不改** signals/*，**不下单**，
只产出：
  1. AnalysisReport：自然语言研判（200-500 字中文 + regime + 关键观察 + 风险）
  2. AgentRecommendation：第二意见推荐单（与 aggregator 推荐单并列展示）

参考 spec：`docs/superpowers/specs/2026-10-03-trend-analysis-agent.md`
"""

from __future__ import annotations

from .schemas import AgentRecommendation, AnalysisReport, AnalysisStatus

__all__ = [
    "AgentRecommendation",
    "AnalysisReport",
    "AnalysisStatus",
]