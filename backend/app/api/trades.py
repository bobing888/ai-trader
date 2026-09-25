"""trades 端点 — 读取 freqtrade trades 表（兼容 mock 数据）"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field


router = APIRouter()


class Trade(BaseModel):
    """单笔交易"""

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
    source: str = Field(..., description="数据源：freqtrade / mock")


def _read_freqtrade_trades(db_path: Path, limit: int, pair: str | None) -> list[dict[str, Any]]:
    """从 freqtrade SQLite 数据库读取交易记录"""
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
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _generate_mock_trades(limit: int, pair: str | None) -> list[dict[str, Any]]:
    """生成 mock 交易记录用于前端测试"""
    pairs = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
    if pair:
        pairs = [pair]

    strategies = ["DoubleEMACrossover", "SmartMoney", "CryptoFrogMultiTF"]
    exit_reasons = ["roi", "stop_loss", "exit_signal", "trailing_stop_loss"]

    now = datetime.now()
    trades: list[dict[str, Any]] = []
    for i in range(limit):
        pair_name = pairs[i % len(pairs)]
        open_dt = now.replace(hour=10, minute=0, second=0, microsecond=0)
        open_dt = open_dt.fromordinal(open_dt.toordinal() - i)

        base_price = 42000 if "BTC" in pair_name else 2200 if "ETH" in pair_name else 178
        profit_ratio = (i % 7 - 3) * 0.012
        open_rate = base_price * (1 + (i % 5 - 2) * 0.005)
        close_rate = open_rate * (1 + profit_ratio)

        trades.append(
            {
                "id": i + 1,
                "pair": pair_name,
                "is_open": 0,
                "open_date": open_dt.isoformat(),
                "close_date": open_dt.replace(hour=14).isoformat(),
                "open_rate": round(open_rate, 2),
                "close_rate": round(close_rate, 2),
                "amount": round(1000 / open_rate, 6),
                "stake_amount": 1000.0,
                "close_profit": round(profit_ratio, 4),
                "close_profit_abs": round(1000 * profit_ratio, 2),
                "exit_reason": exit_reasons[i % len(exit_reasons)],
                "strategy": strategies[i % len(strategies)],
                "enter_tag": "mock_signal",
                "leverage": 1.0,
                "is_short": 0,
            }
        )

    return trades


@router.get("", response_model=TradesResponse)
async def get_trades(
    limit: int = Query(100, ge=1, le=10000, description="返回交易数量"),
    pair: str | None = Query(None, description="按交易对过滤"),
    strategy: str | None = Query(None, description="按策略过滤"),
) -> TradesResponse:
    """获取交易记录 — 优先 freqtrade 数据库，fallback 到 mock 数据"""
    from app.config import settings

    freqtrade_trades = _read_freqtrade_trades(settings.freqtrade_db_path, limit, pair)
    if freqtrade_trades:
        if strategy:
            freqtrade_trades = [t for t in freqtrade_trades if t.get("strategy") == strategy]
        trades = [Trade(**t) for t in freqtrade_trades]
        return TradesResponse(trades=trades, total_count=len(trades), source="freqtrade")

    mock_trades = _generate_mock_trades(limit, pair)
    if strategy:
        mock_trades = [t for t in mock_trades if t.get("strategy") == strategy]
    trades = [Trade(**t) for t in mock_trades]
    return TradesResponse(trades=trades, total_count=len(trades), source="mock")


@router.get("/stats/summary")
async def get_trades_summary() -> dict[str, Any]:
    """获取交易统计概览"""
    from app.config import settings

    freqtrade_trades = _read_freqtrade_trades(settings.freqtrade_db_path, 10000, None)
    if not freqtrade_trades:
        mock_trades = _generate_mock_trades(200, None)
        freqtrade_trades = mock_trades

    total = len(freqtrade_trades)
    profits = [t["close_profit_abs"] for t in freqtrade_trades if t.get("close_profit_abs") is not None]
    winning = [p for p in profits if p > 0]
    losing = [p for p in profits if p < 0]

    total_profit = sum(profits) if profits else 0
    win_rate = len(winning) / total * 100 if total > 0 else 0
    profit_factor = (
        sum(winning) / abs(sum(losing))
        if winning and losing and sum(losing) != 0
        else 0
    )

    return {
        "total_trades": total,
        "winning_trades": len(winning),
        "losing_trades": len(losing),
        "win_rate": round(win_rate, 2),
        "total_profit_abs": round(total_profit, 2),
        "profit_factor": round(profit_factor, 2),
        "source": "freqtrade" if settings.freqtrade_db_path.exists() else "mock",
    }


@router.get("/{trade_id}")
async def get_trade_by_id(trade_id: int) -> Trade:
    """根据 ID 获取单笔交易"""
    from app.config import settings

    freqtrade_trades = _read_freqtrade_trades(settings.freqtrade_db_path, 10000, None)
    if freqtrade_trades:
        for t in freqtrade_trades:
            if t["id"] == trade_id:
                return Trade(**t)

    mock_trades = _generate_mock_trades(1000, None)
    for t in mock_trades:
        if t["id"] == trade_id:
            return Trade(**t)

    raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")
