"""Dashboard schemas — multi-symbol overview payload."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class SignalSummary(BaseModel):
    """单币种信号摘要（dashboard 卡片用）。"""

    direction: str = Field(..., description="long | short")
    confidence: float = Field(..., ge=0.0, le=1.0)
    calibrated_confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="经 isotonic 校准后的真实胜率"
    )
    quality: str = Field(..., description="high | medium | low | reject")
    timeframe: str
    entry_zone_first: str | None = Field(
        default=None, description="aggregator 输出的第一条 entry zone 提示"
    )
    take_profit_1: float | None = None
    stop_loss: float | None = None
    risk_reward_ratio: float = Field(default=0.0, ge=0.0)
    next_predicted_move: str = Field(
        ..., description="人类可读的下一预期走势，如 '看多 ↑ 0.5% (high)'"
    )


class OverviewItem(BaseModel):
    """Dashboard 列表里的单币种条目。"""

    symbol: str
    price: float = Field(default=0.0, ge=0.0)
    change_24h_pct: float = Field(default=0.0)
    signal: SignalSummary | None = Field(
        default=None, description="None = 无足够共识信号"
    )
    degraded: bool = Field(default=False, description="True = 该币拉取失败")
    error: str | None = Field(default=None, description="降级原因")


class OverviewResponse(BaseModel):
    """Dashboard 整体响应。"""

    items: list[OverviewItem]
    timeframe: str
    source: str = Field(..., description="binance | okx | mock")
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )