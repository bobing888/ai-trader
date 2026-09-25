"""Health 端点 — 健康检查"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings


router = APIRouter()


class HealthResponse(BaseModel):
    """健康检查响应"""

    status: str
    app_name: str
    version: str
    debug: bool
    freqtrade_db_configured: bool


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """健康检查端点"""
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        freqtrade_db_configured=settings.freqtrade_db_path.exists(),
    )


@router.get("/ping")
async def ping() -> dict[str, str]:
    """最简单的存活检查"""
    return {"pong": "true"}
