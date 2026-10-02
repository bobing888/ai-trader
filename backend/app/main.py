"""AI 交易助手后端 — 应用入口"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.analysis import router as analysis_router
from app.api.health import router as health_router
from app.api.klines import router as klines_router
from app.api.notifications import router as notifications_router
from app.api.notifications import set_notification_service
from app.api.preferences import router as preferences_router
from app.api.signals import router as signals_router
from app.api.strategies import router as strategies_router
from app.api.ticker import router as ticker_router
from app.api.trades import router as trades_router
from app.api.ws import router as ws_router
from app.config import settings
from app.data import binance_client, get_client, okx_client  # noqa: F401
from app.data.okx_ws import okx_ws_client
from app.db.session import SessionLocal, init_db
from app.services import github_sync as gh
from app.services.follow_scheduler import FollowScheduler, set_follow_scheduler
from app.services.notification_service import NotificationService
from app.services.regime_shift_engine import RegimeShiftEngine
from app.services.signal_change_bus import SignalChangeBus, set_signal_bus

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化两个 client（按 settings.data_source 实际只用其中一个, 但都 init 保证健康探测）
    await binance_client.init()
    await okx_client.init()
    await okx_ws_client.start()
    init_db()

    # Regime-shift engine + notification service (fire-and-forget)
    notification_service = NotificationService()
    regime_engine = RegimeShiftEngine()
    notification_service.attach(regime_engine)
    regime_engine.attach(okx_ws_client, okx_ws_client)
    asyncio.create_task(regime_engine.start())
    # 注册到 API router（绕开 import 循环）
    set_notification_service(notification_service)
    app.state.notification_service = notification_service

    # === B-Follow Step 2: signal bus + follow scheduler + recorder (spec §2) ===
    signal_bus = SignalChangeBus()
    set_signal_bus(signal_bus)

    # Recorder (T8 implements RecommendationRecorder; lazy import to avoid circular)
    from app.services.recommendation_recorder import (
        RecommendationRecorder,
        set_recorder,
    )

    recorder = RecommendationRecorder(
        ws_client=okx_ws_client,
        bus=signal_bus,
        session_factory=SessionLocal,
    )
    set_recorder(recorder)
    await recorder.start()

    # Follow scheduler
    follow_scheduler = FollowScheduler(
        bus=signal_bus,
        session_factory=SessionLocal,
    )
    set_follow_scheduler(follow_scheduler)
    await follow_scheduler.start()

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
            with __import__("contextlib").suppress(asyncio.CancelledError, Exception):
                await sync_task
        # === B-Follow Step 2 清理 ===
        await follow_scheduler.stop()
        await recorder.stop()
        await regime_engine.stop()
        await binance_client.close()
        await okx_client.close()
        await okx_ws_client.stop()


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
    app.include_router(ws_router, prefix="/api", tags=["ws"])
    app.include_router(notifications_router, prefix="/api", tags=["notifications"])
    # === B-Follow Step 2 ===
    from app.api.follows import router as follows_router

    app.include_router(follows_router)

    return app


app = create_app()
