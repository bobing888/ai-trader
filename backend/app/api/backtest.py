"""POST /api/backtest + GET runs + GET run/{id}.

Walk-forward 回测 — 写入 BacktestRun + BacktestTrade 表。
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data import okx_client
from app.db.models import BacktestRun, BacktestTrade
from app.db.session import get_db
from scripts.backtest_engine import BacktestConfig, run_backtest

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


class BacktestRequest(BaseModel):
    symbol: str
    timeframe: str
    strategies: list[str] = Field(min_length=1)
    days: int = Field(default=30, ge=1, le=365)
    fee_taker_bps: float = Field(default=8.0, ge=0)
    slippage_bps: float = Field(default=5.0, ge=0)
    min_confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    target_pct: float = Field(default=0.005, gt=0.0, lt=0.5)
    stop_pct: float = Field(default=0.003, gt=0.0, lt=0.5)
    max_hold_minutes: int = Field(default=60, ge=1, le=1440)


class TradeOut(BaseModel):
    id: int
    strategy_name: str
    entry_time: str
    entry_price: float
    exit_time: str
    exit_price: float
    raw_confidence: float
    calibrated_confidence: Optional[float] = None
    net_pnl_pct: float
    outcome: str
    holding_minutes: int


class BacktestResponse(BaseModel):
    run_id: int
    summary: dict
    equity_curve: list[dict]
    trades: list[TradeOut]


@router.post("", response_model=BacktestResponse)
async def post_backtest(req: BacktestRequest, session: Session = Depends(get_db)):
    # 并发检查
    running = session.execute(
        select(BacktestRun).where(
            BacktestRun.symbol == req.symbol,
            BacktestRun.status == "running",
        )
    ).scalars().first()
    if running:
        raise HTTPException(
            status_code=409,
            detail=f"backtest for {req.symbol} already running (id={running.id})",
        )

    config = BacktestConfig(
        symbol=req.symbol,
        timeframe=req.timeframe,
        strategies=req.strategies,
        days=req.days,
        fee_taker_bps=req.fee_taker_bps,
        slippage_bps=req.slippage_bps,
        min_confidence=req.min_confidence,
        target_pct=req.target_pct,
        stop_pct=req.stop_pct,
        max_hold_minutes=req.max_hold_minutes,
    )

    run = BacktestRun(
        symbol=req.symbol,
        timeframe=req.timeframe,
        strategies=req.strategies,
        days=req.days,
        fee_taker_bps=req.fee_taker_bps,
        slippage_bps=req.slippage_bps,
        min_confidence=req.min_confidence,
        target_pct=req.target_pct,
        stop_pct=req.stop_pct,
        max_hold_minutes=req.max_hold_minutes,
        started_at=datetime.now(timezone.utc),
        status="running",
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    try:
        result = await run_backtest(config, okx_client)
    except ValueError as e:
        run.status = "error"
        run.error_message = str(e)
        run.finished_at = datetime.now(timezone.utc)
        session.commit()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        run.status = "error"
        run.error_message = f"{type(e).__name__}: {e}"
        run.finished_at = datetime.now(timezone.utc)
        session.commit()
        raise HTTPException(status_code=500, detail=f"backtest error: {e}")

    # 持久化 trades
    for t in result.trades:
        session.add(BacktestTrade(
            run_id=run.id,
            symbol=req.symbol,
            timeframe=req.timeframe,
            strategy_name=t.strategy_name,
            entry_time=t.entry_time,
            entry_price=t.entry_price,
            exit_time=t.exit_time,
            exit_price=t.exit_price,
            raw_confidence=t.raw_confidence,
            calibrated_confidence=t.calibrated_confidence,
            target_pct=t.target_pct,
            stop_pct=t.stop_pct,
            gross_pnl_pct=t.gross_pnl_pct,
            fee_pct=t.fee_pct,
            slippage_pct=t.slippage_pct,
            net_pnl_pct=t.net_pnl_pct,
            outcome=t.outcome,
            holding_minutes=t.holding_minutes,
        ))

    run.total_trades = result.total_trades
    run.hit_rate = result.hit_rate
    run.net_pnl_pct = result.net_pnl_pct
    run.sharpe_ratio = result.sharpe_ratio
    run.max_drawdown_pct = result.max_drawdown_pct
    run.equity_curve = [
        {"ts": ts.isoformat() if hasattr(ts, "isoformat") else str(ts), "equity": float(eq)}
        for ts, eq in result.equity_curve
    ]
    run.status = "done"
    run.finished_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(run)

    return BacktestResponse(
        run_id=run.id,
        summary={
            "total_trades": result.total_trades,
            "hit_rate": result.hit_rate,
            "net_pnl_pct": result.net_pnl_pct,
            "sharpe_ratio": result.sharpe_ratio,
            "max_drawdown_pct": result.max_drawdown_pct,
            "started_at": run.started_at.isoformat(),
            "finished_at": run.finished_at.isoformat(),
            "status": "done",
        },
        equity_curve=run.equity_curve,
        trades=[
            TradeOut(
                id=0,    # in-memory only, no DB trade.id yet
                strategy_name=t.strategy_name,
                entry_time=t.entry_time.isoformat(),
                entry_price=t.entry_price,
                exit_time=t.exit_time.isoformat(),
                exit_price=t.exit_price,
                raw_confidence=t.raw_confidence,
                calibrated_confidence=t.calibrated_confidence,
                net_pnl_pct=t.net_pnl_pct,
                outcome=t.outcome,
                holding_minutes=t.holding_minutes,
            ).dict()
            for t in result.trades
        ],
    )


@router.get("/runs", response_model=list[dict])
def list_runs(
    symbol: Optional[str] = None,
    limit: int = 50,
    session: Session = Depends(get_db),
):
    q = select(BacktestRun).order_by(BacktestRun.started_at.desc()).limit(min(limit, 200))
    if symbol:
        q = q.where(BacktestRun.symbol == symbol)
    runs = session.execute(q).scalars().all()
    return [_run_summary(r) for r in runs]


@router.get("/runs/{run_id}", response_model=dict)
def get_run(run_id: int, session: Session = Depends(get_db)):
    run = session.get(BacktestRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    summary = _run_summary(run)
    # 加入 trades
    trades_rows = session.execute(
        select(BacktestTrade).where(BacktestTrade.run_id == run_id)
    ).scalars().all()
    summary["trades"] = [
        {
            "id": t.id,
            "strategy_name": t.strategy_name,
            "entry_time": t.entry_time.isoformat(),
            "entry_price": t.entry_price,
            "exit_time": t.exit_time.isoformat(),
            "exit_price": t.exit_price,
            "raw_confidence": t.raw_confidence,
            "calibrated_confidence": t.calibrated_confidence,
            "net_pnl_pct": t.net_pnl_pct,
            "outcome": t.outcome,
            "holding_minutes": t.holding_minutes,
        }
        for t in trades_rows
    ]
    return summary


def _run_summary(run: BacktestRun) -> dict:
    return {
        "id": run.id,
        "symbol": run.symbol,
        "timeframe": run.timeframe,
        "strategies": run.strategies,
        "days": run.days,
        "fee_taker_bps": run.fee_taker_bps,
        "slippage_bps": run.slippage_bps,
        "min_confidence": run.min_confidence,
        "target_pct": run.target_pct,
        "stop_pct": run.stop_pct,
        "max_hold_minutes": run.max_hold_minutes,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "total_trades": run.total_trades,
        "hit_rate": run.hit_rate,
        "net_pnl_pct": run.net_pnl_pct,
        "sharpe_ratio": run.sharpe_ratio,
        "max_drawdown_pct": run.max_drawdown_pct,
        "equity_curve": run.equity_curve,
        "status": run.status,
        "error_message": run.error_message,
    }