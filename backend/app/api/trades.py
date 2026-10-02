"""trades 端点 — 真实数据源 (UserFollow → freqtrade → 空)，不再生成 mock。

B-Follow 落地后，prod 的真实交易记录来自 UserFollow 表（每条 recommendation 一次
跟进 / 出场）。freqtrade SQLite 仍是合法兜底（如果用户接入 freqtrade 真实回测）。
没有任何 mock 数据：返回空 = 返回空，绝不假装。
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

router = APIRouter()


class Trade(BaseModel):
    """单笔交易（前端展示模型）。"""

    id: int
    pair: str
    is_open: bool
    open_date: datetime
    close_date: datetime | None = None
    open_rate: float | None = None
    close_rate: float | None = None
    amount: float | None = None
    stake_amount: float
    close_profit: float | None = None
    close_profit_abs: float | None = None
    exit_reason: str | None = None
    strategy: str | None = None
    enter_tag: str | None = None
    leverage: float = 1.0
    is_short: bool = False


class TradesResponse(BaseModel):
    """交易列表响应"""

    trades: list[Trade]
    total_count: int
    source: str = Field(..., description="数据源：follows | freqtrade | empty")


# ----------------------------------------------------------------------
# freqtrade SQLite — 历史兜底
# ----------------------------------------------------------------------
def _read_freqtrade_trades(db_path: Path, limit: int, pair: str | None) -> list[dict[str, Any]]:
    """从 freqtrade SQLite 读取交易记录（历史兼容）"""
    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        query = """
            SELECT id, pair, is_open, open_date, close_date,
                   open_rate, close_rate, amount, stake_amount,
                   close_profit, close_profit_abs, exit_reason,
                   strategy, enter_tag,
                   COALESCE(leverage, 1.0) as leverage,
                   COALESCE(is_short, 0) as is_short
            FROM trades
            WHERE 1=1
        """
        params: list[Any] = []
        if pair:
            query += " AND pair = ?"
            params.append(pair)
        query += " ORDER BY open_date DESC LIMIT ?"
        params.append(limit)
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


# ----------------------------------------------------------------------
# UserFollow — 主数据源（B-Follow）
# ----------------------------------------------------------------------
def _pair_with_slash(pair: str) -> str:
    """UserFollow.pair 存的是 OKX 格式 'ETH-USDT'，前端展示用 'ETH/USDT'"""
    return pair.replace("-", "/", 1) if "-" in pair else pair


def _follow_to_trade_dict(f: Any) -> dict[str, Any]:
    """UserFollow → Trade dict 转换。pnl 实时从 exit_price - entry_price 推算。"""
    is_open = (f.status == "open")
    pnl_pct = f.pnl_pct
    pnl_abs = f.pnl_abs
    if is_open:
        # 持仓中无 pnl 持久化，前端用 close_profit=null 表示未平仓
        pnl_pct = None
        pnl_abs = None
    # pnl_abs 没存但 pnl_pct 存了 → 实时计算
    elif pnl_abs is None and pnl_pct is not None:
        pnl_abs = round(f.stake_amount * pnl_pct, 2)

    # amount = stake / entry_price（数量基于本金计算）
    amount = None
    if f.entry_price and f.stake_amount:
        amount = round(f.stake_amount / f.entry_price, 6)

    return {
        "id": f.id,
        "pair": _pair_with_slash(f.pair),
        "is_open": is_open,
        "open_date": f.entry_time,
        "close_date": f.exit_time,
        "open_rate": f.entry_price,
        "close_rate": f.exit_price,
        "amount": amount,
        "stake_amount": f.stake_amount,
        "close_profit": pnl_pct,
        "close_profit_abs": pnl_abs,
        "exit_reason": f.exit_reason,
        "strategy": None,  # UserFollow 不直接绑定 strategy
        "enter_tag": f.source,  # 'ai_recommendation' | 'manual'
        "leverage": float(f.leverage or 1),
        "is_short": f.direction == "short",
    }


def _read_follow_trades(
    db: Session,
    limit: int,
    pair: str | None,
) -> list[dict[str, Any]]:
    """从 UserFollow 读取真实交易记录。"""
    from app.db.models import UserFollow

    query = db.query(UserFollow)
    if pair:
        # 前端传 'ETH/USDT'，DB 存 'ETH-USDT'
        db_pair = pair.replace("/", "-", 1) if "/" in pair else pair
        query = query.filter(UserFollow.pair == db_pair)

    # 优先按 entry_time 倒序，缺则 created_at
    follows = query.order_by(UserFollow.entry_time.desc()).limit(limit).all()
    return [_follow_to_trade_dict(f) for f in follows]


# ----------------------------------------------------------------------
# 端点
# ----------------------------------------------------------------------
@router.get("", response_model=TradesResponse)
async def get_trades(
    limit: int = Query(100, ge=1, le=10000, description="返回交易数量"),
    pair: str | None = Query(None, description="按交易对过滤"),
    strategy: str | None = Query(None, description="按策略过滤"),
) -> TradesResponse:
    """获取交易记录 — 优先 UserFollow（B-Follow），fallback 到 freqtrade 兜底；都没有 → 空。"""
    from app.config import settings
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        follow_trades = _read_follow_trades(db, limit, pair)
    finally:
        db.close()

    if follow_trades:
        # UserFollow 没有 strategy 字段，过滤直接拒绝匹配（避免假阳性）
        if strategy:
            follow_trades = [t for t in follow_trades if t.get("strategy") == strategy]
        trades = [Trade(**t) for t in follow_trades]
        return TradesResponse(trades=trades, total_count=len(trades), source="follows")

    # 兜底：freqtrade SQLite（用户接 freqtrade 实盘才有数据）
    freqtrade_trades = _read_freqtrade_trades(settings.freqtrade_db_path, limit, pair)
    if freqtrade_trades:
        if strategy:
            freqtrade_trades = [t for t in freqtrade_trades if t.get("strategy") == strategy]
        trades = [Trade(**t) for t in freqtrade_trades]
        return TradesResponse(trades=trades, total_count=len(trades), source="freqtrade")

    # 都没有 → 空，绝不返 mock
    return TradesResponse(trades=[], total_count=0, source="empty")


@router.get("/stats/summary")
async def get_trades_summary() -> dict[str, Any]:
    """获取交易统计概览 — 同上三层数据源。"""
    from app.config import settings
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        follow_trades = _read_follow_trades(db, 10000, None)
    finally:
        db.close()

    if follow_trades:
        source = "follows"
        trades = follow_trades
    else:
        freqtrade_trades = _read_freqtrade_trades(settings.freqtrade_db_path, 10000, None)
        if freqtrade_trades:
            source = "freqtrade"
            trades = freqtrade_trades
        else:
            source = "empty"
            trades = []

    total = len(trades)
    profits = [t["close_profit_abs"] for t in trades if t.get("close_profit_abs") is not None]
    winning = [p for p in profits if p > 0]
    losing = [p for p in profits if p < 0]

    total_profit = sum(profits) if profits else 0.0
    win_rate = len(winning) / total * 100 if total > 0 else 0.0
    profit_factor = (
        sum(winning) / abs(sum(losing))
        if winning and losing and sum(losing) != 0
        else 0.0
    )

    return {
        "total_trades": total,
        "winning_trades": len(winning),
        "losing_trades": len(losing),
        "win_rate": round(win_rate, 2),
        "total_profit_abs": round(total_profit, 2),
        "profit_factor": round(profit_factor, 2),
        "source": source,
    }


@router.get("/{trade_id}")
async def get_trade_by_id(trade_id: int) -> Trade:
    """根据 ID 获取单笔交易 — UserFollow 优先，freqtrade 兜底。"""
    from app.config import settings
    from app.db.session import SessionLocal
    from app.db.models import UserFollow

    db = SessionLocal()
    try:
        f = db.query(UserFollow).filter_by(id=trade_id).one_or_none()
        if f:
            return Trade(**_follow_to_trade_dict(f))
    finally:
        db.close()

    # 兜底：freqtrade SQLite（按 ID 找）
    freqtrade_trades = _read_freqtrade_trades(settings.freqtrade_db_path, 10000, None)
    for t in freqtrade_trades:
        if t["id"] == trade_id:
            return Trade(**t)

    raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")