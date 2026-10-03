"""Pydantic schemas for recommendations API (spec §5.3)"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_serializer


class RecommendationHistoryOut(BaseModel):
    """一帧推荐决议快照."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    pair: str
    timeframe: str
    has_signal: bool
    direction: str | None
    confidence: float | None
    regime: str | None
    regime_confidence: float | None
    suggested_leverage: int | None
    fast_path: bool
    outcome: str
    scanned_at: datetime
    source: str
    # Phase 1 signal credibility
    calibrated_confidence: float | None = None
    net_pnl_estimate: float | None = None
    # D1 — actionable execution levels
    entry_levels: list[dict] = []
    stop_loss_price: float | None = None
    take_profit_1_price: float | None = None
    take_profit_2_price: float | None = None
    atr: float | None = None
    risk_reward_ratio: float | None = None
    current_price: float | None = None
    # D2 — quality gate
    quality: str | None = None
    quality_reasons: list[str] = []

    # 2026-10-03: 进/离场时间窗口（分钟，基于 timeframe 推 N 根 K 线）
    entry_window_minutes: int | None = None
    exit_window_minutes: int | None = None

    # Horizon tier + leverage (spec §3.A)
    horizon_tier: str = "P1_short"  # P0_long / P0_cross_month / P1_mid / P1_short / P2_ultra / P3_uhf
    leverage: int = 1
    expires_at: datetime | None = None

    @field_serializer("entry_levels", "quality_reasons")
    def _serialize_list(self, value):
        return value or []

    @classmethod
    def from_orm_with_json(cls, obj) -> "RecommendationHistoryOut":
        """从 ORM 行 + JSON 文本字段构造."""
        import json

        data = {c.key: getattr(obj, c.key) for c in obj.__table__.columns}
        # 解析 JSON 字段
        if data.get("entry_levels_json"):
            try:
                data["entry_levels"] = json.loads(data["entry_levels_json"])
            except Exception:
                data["entry_levels"] = []
        else:
            data["entry_levels"] = []
        if data.get("quality_reasons_json"):
            try:
                data["quality_reasons"] = json.loads(data["quality_reasons_json"])
            except Exception:
                data["quality_reasons"] = []
        else:
            data["quality_reasons"] = []
        return cls(**data)


class RecommendationHistoryList(BaseModel):
    items: list[RecommendationHistoryOut]
    total: int