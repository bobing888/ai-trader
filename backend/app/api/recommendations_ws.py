"""/api/recommendations/ws — WebSocket 推送 SignalChangeBus 事件（spec §5.2）

客户端连接后,任何 SignalChangeEvent 都会通过这个 endpoint 推送。

D4: 完整 payload — entry_levels / SL / TP / quality / current_price 全部下推。
    客户端无需再调 GET /api/{id} 即可渲染。
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.signal_change_bus import get_signal_bus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


def _serialize_recommendation(rec) -> dict:
    """把 RecommendationHistory 行取完整 dict（含 version）供 web 前端用."""
    if rec is None:
        return {}
    payload = {
        "id": rec.id,
        "pair": rec.pair,
        "timeframe": rec.timeframe,
        "has_signal": rec.has_signal,
        "direction": rec.direction,
        "confidence": rec.confidence,
        "regime": rec.regime,
        "regime_confidence": rec.regime_confidence,
        "contributing_strategies": (
            json.loads(rec.contributing_strategies) if rec.contributing_strategies else []
        ),
        "reasons": json.loads(rec.reasons) if rec.reasons else [],
        "suggested_leverage": rec.suggested_leverage,
        "min_agreement_used": rec.min_agreement_used,
        "fast_path": rec.fast_path,
        "outcome": rec.outcome,
        "scanned_at": rec.scanned_at.isoformat() if rec.scanned_at else None,
        "source": rec.source,
        # Phase 1
        "calibrated_confidence": rec.calibrated_confidence,
        "net_pnl_estimate": rec.net_pnl_estimate,
        # D1 — executable levels
        "entry_levels": json.loads(rec.entry_levels_json) if rec.entry_levels_json else [],
        "stop_loss_price": rec.stop_loss_price,
        "take_profit_1_price": rec.take_profit_1_price,
        "take_profit_2_price": rec.take_profit_2_price,
        "atr": rec.atr,
        "risk_reward_ratio": rec.risk_reward_ratio,
        "current_price": rec.current_price,
        # D2 — quality gate
        "quality": rec.quality,
        "quality_reasons": (
            json.loads(rec.quality_reasons_json) if rec.quality_reasons_json else []
        ),
    }
    return payload


@router.websocket("/ws")
async def recommendations_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    bus = get_signal_bus()
    queue = bus.subscribe()
    try:
        # 连接后立刻发 initial snapshot（拿当前 active 信号 — 前端首屏就能看到）
        try:
            await _send_initial_snapshot(bus, websocket)
        except Exception as exc:
            logger.debug("[recs_ws] initial snapshot skipped: %s", exc)

        while True:
            event = await queue.get()
            try:
                # D4: full payload — 前后端无需二次 GET
                await websocket.send_json({
                    "type": "signal_change",
                    "change_type": event.change_type,
                    "pair": event.pair,
                    "timeframe": event.timeframe,
                    "current": _serialize_recommendation(event.current),
                    "previous": _serialize_recommendation(event.previous),
                })
            except Exception as exc:
                logger.warning("[recs_ws] send failed: %s", exc)
                break
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(queue)


async def _send_initial_snapshot(websocket: WebSocket) -> None:
    """连接时主动推一帧「最近一次 active 信号」给前端避免冷启动空窗."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from app.db.database import SessionLocal
    from app.db.models import RecommendationHistory

    db = SessionLocal()
    try:
        # 最近 5 分钟内 has_signal=True 的，按时间倒序取最新一对 (pair, timeframe)
        cutoff = datetime.now(UTC) - timedelta(minutes=5)
        rows = db.execute(
            select(RecommendationHistory)
            .where(
                RecommendationHistory.has_signal.is_(True),
                RecommendationHistory.scanned_at >= cutoff,
            )
            .order_by(RecommendationHistory.scanned_at.desc())
            .limit(8)
        ).scalars().all()
        for rec in rows:
            await websocket.send_json({
                "type": "signal_change",
                "change_type": "initial_snapshot",
                "pair": rec.pair,
                "timeframe": rec.timeframe,
                "current": _serialize_recommendation(rec),
                "previous": None,
            })
    finally:
        db.close()