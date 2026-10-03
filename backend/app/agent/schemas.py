"""Agent schemas — 研判报告 + 第二意见推荐单 Pydantic models.

参考 spec：`docs/superpowers/specs/2026-10-03-trend-analysis-agent.md` §6.5

设计要点：
  1. pair 强约束 BTC-USDT / ETH-USDT（btc-eth-scope Rule 1）
  2. timeframe 强约束 5m / 15m / 1h / 1d（与 recommendation_timeframes 一致）
  3. AnalysisReport 是 fail-soft：analysis_status 标记 LLM 失败 / 解析失败 / 降级
  4. reasoning 200-500 字中文（V1 暂不强制长度，留给 prompt 模板约束）
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# === Enums ===

class AnalysisStatus(str, Enum):
    """研判报告状态（用于降级 / 错误标记）"""

    SUCCESS = "success"           # LLM 正常返回 + Pydantic 合规
    FALLBACK = "fallback"       # LLM 调用失败（5xx / timeout / rate-limit）
    PARSE_ERROR = "parse_error" # LLM 返回但不符合 Pydantic schema
    DATA_INCOMPLETE = "data_incomplete"  # signals/* 数据缺失


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


# === Constants (single source of truth) ===

ALLOWED_PAIRS: tuple[str, ...] = ("BTC-USDT", "ETH-USDT")
ALLOWED_TIMEFRAMES: tuple[str, ...] = ("5m", "15m", "1h", "1d")
ALLOWED_REGIMES: tuple[str, ...] = ("bull", "bear", "choppy", "crisis")


# === Schemas ===

class AnalysisReport(BaseModel):
    """研判报告 — Agent 的核心产出"""

    pair: Literal["BTC-USDT", "ETH-USDT"] = Field(
        ..., description="交易对，强制 BTC/ETH（btc-eth-scope Rule 1）"
    )
    timeframe: Literal["5m", "15m", "1h", "1d"] = Field(
        ..., description="时间周期，与 recommendation_timeframes 对齐"
    )
    regime: Literal["bull", "bear", "choppy", "crisis"] = Field(
        ..., description="Agent 判断的市场状态（可能与 signals/regime.py 不一致——这是 agent 的第二意见）"
    )
    regime_confidence: float = Field(
        ..., ge=0.0, le=1.0, description="regime 判断的置信度 0-1"
    )
    reasoning: str = Field(
        ..., min_length=10, description="自然语言研判，200-500 字中文（V1 不强制长度上限）"
    )
    key_observations: list[str] = Field(
        default_factory=list, description="关键观察点，3-5 条"
    )
    risks: list[str] = Field(
        default_factory=list, description="风险点"
    )
    analysis_status: AnalysisStatus = Field(
        default=AnalysisStatus.SUCCESS, description="降级标记"
    )
    raw_llm_response: str | None = Field(
        default=None, description="LLM 原始响应（PARSE_ERROR 时保留以便 debug）"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC 时间戳",
    )

    @field_validator("pair")
    @classmethod
    def _validate_pair(cls, v: str) -> str:
        if v not in ALLOWED_PAIRS:
            raise ValueError(
                f"{v} 不在分析范围。AI-Trader 当前只覆盖 {ALLOWED_PAIRS}。"
                "其他币种请用 freqtrade / 其他工具。"
            )
        return v


class AgentRecommendation(BaseModel):
    """Agent 第二意见推荐单 — 与 aggregator 推荐单并列展示，不抢权威"""

    pair: Literal["BTC-USDT", "ETH-USDT"] = Field(..., description="BTC/ETH only")
    timeframe: Literal["5m", "15m", "1h", "1d"] = Field(..., description="4 档周期")
    direction: Direction = Field(..., description="long / short / neutral")
    confidence: float = Field(..., ge=0.0, le=1.0, description="0-1 置信度")
    rationale: str = Field(..., min_length=10, description="100-200 字理由")
    source: Literal["agent"] = Field(
        default="agent", description="固定为 agent，区别于 aggregator"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @field_validator("pair")
    @classmethod
    def _validate_pair(cls, v: str) -> str:
        if v not in ALLOWED_PAIRS:
            raise ValueError(f"{v} 不在分析范围")
        return v