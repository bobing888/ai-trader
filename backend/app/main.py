"""AI 交易助手后端 — 应用入口"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.analysis import router as analysis_router
from app.api.health import router as health_router
from app.api.klines import router as klines_router
from app.api.preferences import router as preferences_router
from app.api.signals import router as signals_router
from app.api.strategies import router as strategies_router
from app.api.ticker import router as ticker_router
from app.api.trades import router as trades_router
from app.config import settings
from app.data import binance_client
from app.db.session import init_db
from app.services import github_sync as gh

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await binance_client.init()
    init_db()
    # 启动 GitHub sync 后台循环
    sync_task = None
    if settings.github_sync_enabled:
        sync_task = asyncio.create_task(gh.scheduled_sync_loop())
        logger.info("github sync scheduler started (interval=%sh)", settings.github_sync_interval_hours)
    try:
        yield
    finally:
        if sync_task is not None:
            sync_task.cancel()
            try:
                await sync_task
            except (asyncio.CancelledError, Exception):
                pass
        await binance_client.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI 交易助手 API",
        description="现货+合约混合模式的 AI 交易助手后端",
        version="0.2.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router, prefix="/api", tags=["health"])
    app.include_router(klines_router, prefix="/api/klines", tags=["klines"])
    app.include_router(ticker_router, prefix="/api", tags=["ticker"])
    app.include_router(trades_router, prefix="/api/trades", tags=["trades"])
    app.include_router(signals_router, prefix="/api", tags=["signals"])
    app.include_router(preferences_router, prefix="/api/preferences", tags=["preferences"])
    app.include_router(strategies_router, prefix="/api/strategies", tags=["strategies"])
    app.include_router(analysis_router, prefix="/api/analysis", tags=["analysis"])

    return app


app = create_app()
