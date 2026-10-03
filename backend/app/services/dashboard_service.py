"""Dashboard service — multi-symbol overview aggregation.

复用现有 /api/ticker/batch 和 /api/signals/recommend/{pair} 两条接口，
通过 asyncio.gather 并发拉取，组装为 dashboard payload。

设计原则：
1. 不修改 signal engine / strategy_pool / aggregator 任何逻辑
2. 单币失败 → degraded=true，整体不失败（前端按降级态展示）
3. 输入顺序保留（前端 grid 按用户选顺序展示）
4. symbol 形态兼容：BTC-USDT / BTCUSDT 两种均接受
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.api.signals import get_recommendation
from app.config import settings
from app.data import get_client
from app.schemas.dashboard import (
    OverviewItem,
    OverviewResponse,
    SignalSummary,
)


_MAX_SYMBOLS = 50


def _format_predicted_move(direction: str, net_pnl: float, quality: str) -> str:
    """模板字符串生成人类可读的下一预期走势。"""
    arrow = "↑" if direction == "long" else "↓"
    side = "看多" if direction == "long" else "看空"
    # 0.5% 阈值以下显示"震荡"
    pct = abs(net_pnl) * 100
    if pct < 0.05:
        magnitude = "震荡"
    else:
        magnitude = f"{pct:.1f}%"
    return f"{side} {arrow} {magnitude} ({quality})"


def _extract_signal_summary(recommendation: dict) -> SignalSummary | None:
    """从 /api/signals/recommend/{pair} 返回的 dict 提取 dashboard 用的 SignalSummary。"""
    if not recommendation.get("has_signal"):
        return None
    sig = recommendation.get("signal") or {}
    direction = sig.get("direction")
    if direction not in ("long", "short"):
        return None

    entry_zones = sig.get("entry_zones") or []
    entry_zone_first = entry_zones[0] if entry_zones else None

    confidence = float(sig.get("confidence", 0.0))
    calibrated = sig.get("calibrated_confidence")
    quality = sig.get("quality", "medium")
    net_pnl = float(sig.get("net_pnl_estimate", 0.0))

    return SignalSummary(
        direction=direction,
        confidence=round(confidence, 3),
        calibrated_confidence=(
            round(float(calibrated), 3) if calibrated is not None else None
        ),
        quality=quality,
        timeframe=sig.get("timeframe", "1h"),
        entry_zone_first=entry_zone_first,
        take_profit_1=sig.get("take_profit_1_price"),
        stop_loss=sig.get("stop_loss_price"),
        risk_reward_ratio=float(sig.get("risk_reward_ratio", 0.0)),
        next_predicted_move=_format_predicted_move(direction, net_pnl, quality),
    )


async def fetch_tickers(symbols: list[str]) -> dict:
    """拉 ticker 批量（mock 模式返回 0，真实模式调 client）。"""
    if settings.use_mock_data:
        return {
            "tickers": [
                {"symbol": s.replace("-", "").upper(), "price": 0.0, "change_24h": 0.0}
                for s in symbols
            ],
            "source": "mock",
        }
    client = get_client()
    # ticker 接受 BTCUSDT 形态
    raw_symbols = [s.replace("-", "").upper() for s in symbols]
    tickers = await client.get_tickers_batch(raw_symbols)
    return {"tickers": tickers, "source": (settings.data_source or "binance").lower()}


async def fetch_signal_for_pair(
    pair: str, timeframe: str, limit: int = 120
) -> dict:
    """对单币调用 /api/signals/recommend/{pair} 路径上的逻辑（直接调函数复用）。"""
    return await get_recommendation(pair=pair, timeframe=timeframe, limit=limit)


def _build_signal_error_message(error_text: str) -> str:
    """降级原因截断到 200 字符。"""
    return (error_text or "unknown error")[:200]


async def fetch_overview(
    symbols: list[str], timeframe: str = "1h"
) -> OverviewResponse:
    """聚合 N 个 symbol 的 ticker + signal，返回 dashboard overview."""
    if not symbols:
        raise ValueError("symbols must be non-empty")
    if len(symbols) > _MAX_SYMBOLS:
        raise ValueError(f"max {_MAX_SYMBOLS} symbols per request")

    # Step 1: 拉 ticker 批量（单次请求）
    ticker_payload = await fetch_tickers(symbols)
    tickers_by_raw: dict[str, dict] = {
        t["symbol"]: t for t in ticker_payload.get("tickers", [])
    }

    # Step 2: 并发拉每个币的 signal
    async def _safe_signal(pair: str) -> tuple[str, dict | None, str | None]:
        try:
            sig = await fetch_signal_for_pair(pair, timeframe)
            return (pair, sig, None)
        except Exception as e:
            return (pair, None, str(e))

    results = await asyncio.gather(*[_safe_signal(s) for s in symbols])

    # Step 3: 组装 payload，**保留输入顺序**
    items: list[OverviewItem] = []
    for original_symbol, (pair, sig, err) in zip(symbols, results):
        # ticker 查表（key 是无 - 形态）
        ticker_key = pair.replace("-", "").upper()
        ticker = tickers_by_raw.get(ticker_key, {})
        price = float(ticker.get("price", 0.0))
        change_24h = float(ticker.get("change_24h", 0.0))

        if err is not None:
            items.append(
                OverviewItem(
                    symbol=pair,
                    price=price,
                    change_24h_pct=change_24h,
                    signal=None,
                    degraded=True,
                    error=_build_signal_error_message(err),
                )
            )
            continue

        try:
            signal_summary = _extract_signal_summary(sig or {})
        except Exception:
            signal_summary = None

        items.append(
            OverviewItem(
                symbol=pair,
                price=price,
                change_24h_pct=change_24h,
                signal=signal_summary,
                degraded=False,
                error=None,
            )
        )

    return OverviewResponse(
        items=items,
        timeframe=timeframe,
        source=ticker_payload.get("source", "mock"),
        generated_at=datetime.now(timezone.utc),
    )