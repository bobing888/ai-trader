"""User preferences 端点 — K 线指标/形态等用户选择（Redis 持久化）

按 anonymous user_id（前端生成 UUID，存在 localStorage）存储。
跨设备同步：用户只需在同一浏览器保留 UUID 即可。如未来接入正式用户系统，
把 anonymous_user_id 换成 user_id 即可，schema 不变。
"""

import json
import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.data import binance_client

logger = logging.getLogger(__name__)

router = APIRouter(redirect_slashes=False)


# ── Schemas ──────────────────────────────────────────────────────────────────


class IndicatorPref(BaseModel):
    """单个指标的开关 + 可选参数覆盖"""

    enabled: bool = True
    params: dict[str, Any] = Field(default_factory=dict)


class PatternPref(BaseModel):
    """K 线形态标记开关"""

    enabled: bool = True


class ChartPreferences(BaseModel):
    """K 线图用户偏好"""

    indicators: dict[str, IndicatorPref] = Field(default_factory=dict)
    patterns: dict[str, PatternPref] = Field(default_factory=dict)


class PreferencesResponse(BaseModel):
    user_id: str
    preferences: ChartPreferences


# ── Helpers ──────────────────────────────────────────────────────────────────


def _key(user_id: str) -> str:
    return f"user_prefs:{user_id}"


async def _get_redis() -> Any | None:
    """复用 binance_client 的 redis 连接，避免重复创建"""
    return binance_client._redis  # noqa: SLF001 — intentional reuse


def _default_preferences() -> ChartPreferences:
    """新用户的默认偏好：保留项目核心指标 + 5 个最常用形态"""
    return ChartPreferences(
        indicators={
            # 主图均线（用户重点要求多周期）
            "ma5": IndicatorPref(enabled=False, params={"length": 5}),
            "ma10": IndicatorPref(enabled=False, params={"length": 10}),
            "ma20": IndicatorPref(enabled=True, params={"length": 20}),
            "ma30": IndicatorPref(enabled=True, params={"length": 30}),
            "ma60": IndicatorPref(enabled=False, params={"length": 60}),
            "ema12": IndicatorPref(enabled=False, params={"length": 12}),
            "ema26": IndicatorPref(enabled=False, params={"length": 26}),
            "ema50": IndicatorPref(enabled=True, params={"length": 50}),
            # 完整布林带（3 条线）
            "boll": IndicatorPref(enabled=True, params={"length": 20, "mult": 2.0}),
            # VWAP
            "vwap": IndicatorPref(enabled=False, params={}),
            # 副图指标
            "rsi": IndicatorPref(enabled=True, params={"length": 14}),
            "rsi6": IndicatorPref(enabled=False, params={"length": 6}),
            "rsi24": IndicatorPref(enabled=False, params={"length": 24}),
            "macd": IndicatorPref(enabled=True, params={"fast": 12, "slow": 26, "signal": 9}),
            "kdj": IndicatorPref(enabled=True, params={"length": 9}),
            "obv": IndicatorPref(enabled=True, params={}),
            "stoch": IndicatorPref(enabled=False, params={"k": 14, "d": 3}),
            "cci": IndicatorPref(enabled=False, params={"length": 20}),
            "wr": IndicatorPref(enabled=False, params={"length": 14}),
            "mfi": IndicatorPref(enabled=False, params={"length": 14}),
            "adx": IndicatorPref(enabled=False, params={"length": 14}),
            "atr": IndicatorPref(enabled=False, params={"length": 14}),
            # 高级趋势
            "sar": IndicatorPref(enabled=False, params={"step": 0.02, "max": 0.2}),
            "supertrend": IndicatorPref(enabled=False, params={"length": 10, "mult": 3.0}),
            "keltner": IndicatorPref(enabled=False, params={"length": 20, "mult": 2.0}),
            "ichimoku": IndicatorPref(enabled=False, params={}),
        },
        patterns={
            # Top 10 形态（按使用频率）
            "hammer": PatternPref(enabled=True),
            "hanging_man": PatternPref(enabled=True),
            "engulfing": PatternPref(enabled=True),
            "doji": PatternPref(enabled=True),
            "shooting_star": PatternPref(enabled=True),
            "morning_star": PatternPref(enabled=True),
            "evening_star": PatternPref(enabled=True),
            "three_white_soldiers": PatternPref(enabled=True),
            "three_black_crows": PatternPref(enabled=True),
            "harami": PatternPref(enabled=False),
        },
    )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=PreferencesResponse)
async def get_preferences(
    x_user_id: str = Header(..., alias="X-User-Id", description="anonymous UUID from localStorage"),
) -> PreferencesResponse:
    """读取用户偏好。无记录时返回默认。"""
    redis = await _get_redis()
    if redis:
        try:
            raw = await redis.get(_key(x_user_id))
            if raw:
                data = json.loads(raw)
                return PreferencesResponse(user_id=x_user_id, preferences=ChartPreferences(**data))
        except Exception as e:
            logger.warning("preferences read failed: %s", e)

    return PreferencesResponse(user_id=x_user_id, preferences=_default_preferences())


@router.put("", response_model=PreferencesResponse)
async def put_preferences(
    body: ChartPreferences,
    x_user_id: str = Header(..., alias="X-User-Id"),
) -> PreferencesResponse:
    """整体覆盖保存用户偏好。"""
    redis = await _get_redis()
    payload = body.model_dump()
    if redis:
        try:
            await redis.set(_key(x_user_id), json.dumps(payload))
        except Exception as e:
            logger.warning("preferences write failed: %s", e)
            raise HTTPException(status_code=503, detail="cache unavailable")
    else:
        # Redis 不可用时直接返回（不报错），让前端保持 localStorage 兜底
        logger.warning("Redis unavailable — preferences not persisted for user %s", x_user_id)
    return PreferencesResponse(user_id=x_user_id, preferences=body)


@router.post("/reset", response_model=PreferencesResponse)
async def reset_preferences(
    x_user_id: str = Header(..., alias="X-User-Id"),
) -> PreferencesResponse:
    """重置为默认偏好"""
    redis = await _get_redis()
    if redis:
        try:
            await redis.delete(_key(x_user_id))
        except Exception as e:
            logger.warning("preferences delete failed: %s", e)
    return PreferencesResponse(user_id=x_user_id, preferences=_default_preferences())
