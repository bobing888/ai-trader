"""FollowService — 业务层 CRUD + PnL mock（spec §4.4）

不依赖 FastAPI,可被 API 层 + scheduler 层调用。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import UserFollow


class FollowService:
    """跟单业务逻辑 — 纯函数 + 静态 PnL 计算。"""

    # === PnL mock (跟 freqtrade close_profit 公式一致) ===

    @staticmethod
    def compute_pnl(
        entry_price: float,
        exit_price: float,
        direction: str,
        leverage: int = 1,
        stake_amount: float = 100.0,
    ) -> tuple[float, float]:
        """算 pnl_pct + pnl_abs。

        direction:
          long  = (exit - entry) / entry * leverage
          short = (entry - exit) / entry * leverage

        Returns:
            (pnl_pct, pnl_abs) — pnl_abs = pnl_pct * stake_amount
        """
        if direction == "long":
            pnl_pct = (exit_price - entry_price) / entry_price * leverage
        else:
            pnl_pct = (entry_price - exit_price) / entry_price * leverage
        pnl_abs = pnl_pct * stake_amount
        return round(pnl_pct, 6), round(pnl_abs, 4)

    # === CRUD ===

    @staticmethod
    def create(db: Session, payload: dict[str, Any]) -> UserFollow:
        """新建跟单 — entry_time=now, status=open, stake_amount=100。

        D3: 接收 snapshot 自带单价的量化字段（SL/TP/ATR），extract 用 dashboard 计算实时浮盈。
        """
        entry_price = payload.get("entry_price")
        follow = UserFollow(
            pair=payload["pair"],
            timeframe=payload["timeframe"],
            direction=payload["direction"],
            entry_price=entry_price,
            stop_loss=payload.get("stop_loss"),
            target=payload.get("target"),
            leverage=payload.get("leverage", 1),
            stake_amount=payload.get("stake_amount", 100.0),
            source=payload.get("source", "manual"),
            recommendation_id=payload.get("recommendation_id"),
            notes=payload.get("notes"),
            status="open",
            entry_time=datetime.now(UTC),
            # D3: snapshot trailing + partial TP 配置 + 价位
            trailing_stop_enabled=1 if payload.get("trailing_stop_enabled", True) else 0,
            partial_tp_enabled=1 if payload.get("partial_tp_enabled", True) else 0,
            current_stop_loss=payload.get("stop_loss"),
            take_profit_1_price=payload.get("take_profit_1_price"),
            take_profit_2_price=payload.get("take_profit_2_price"),
            entry_atr=payload.get("entry_atr"),
            remaining_size_pct=payload.get("remaining_size_pct", 1.0),
            entry_price_ref=entry_price,
        )
        db.add(follow)
        db.commit()
        db.refresh(follow)
        return follow

    @staticmethod
    def close(
        db: Session,
        follow_id: int,
        exit_price: float,
        exit_reason: str = "manual",
        exit_size_pct: float = 1.0,
    ) -> UserFollow:
        """出场 + 算 PnL。已 closed/cancelled 抛 ValueError。

        D3: exit_size_pct=0.5 时为 partial TP（仅平一半仓位，remain open，update state）。
        """
        follow = db.query(UserFollow).filter(UserFollow.id == follow_id).with_for_update().first()
        if follow is None:
            raise ValueError(f"Follow {follow_id} not found")
        if follow.status != "open":
            raise ValueError(f"Follow {follow_id} already {follow.status}")

        # D3: partial TP — 记录 TP1 触发，SL 移到 entry (保本)
        if exit_size_pct < 1.0:
            follow.partial_tp_taken = 1
            follow.remaining_size_pct = 1.0 - exit_size_pct
            follow.current_stop_loss = follow.entry_price_ref or follow.entry_price
            follow.exit_price = exit_price
            follow.exit_time = datetime.now(UTC)
            follow.exit_reason = exit_reason
            partial_pnl_pct, partial_pnl_abs = FollowService.compute_pnl(
                entry_price=follow.entry_price or 0.0,
                exit_price=exit_price,
                direction=follow.direction,
                leverage=follow.leverage,
                stake_amount=follow.stake_amount * exit_size_pct,
            )
            follow.pnl_pct = partial_pnl_pct
            follow.pnl_abs = partial_pnl_abs
            db.commit()
            db.refresh(follow)
            return follow

        # 全平（含 trailing_stop 触发）
        pnl_pct, pnl_abs = FollowService.compute_pnl(
            entry_price=follow.entry_price or 0.0,
            exit_price=exit_price,
            direction=follow.direction,
            leverage=follow.leverage,
            stake_amount=follow.stake_amount,
        )

        follow.exit_price = exit_price
        follow.exit_time = datetime.now(UTC)
        follow.exit_reason = exit_reason
        follow.pnl_pct = pnl_pct
        follow.pnl_abs = pnl_abs
        follow.status = "closed"
        db.commit()
        db.refresh(follow)
        return follow

    @staticmethod
    def cancel(db: Session, follow_id: int, reason: str = "manual") -> UserFollow:
        """撤销未入场的跟单。已 closed/cancelled 抛 ValueError。"""
        follow = db.query(UserFollow).filter(UserFollow.id == follow_id).with_for_update().first()
        if follow is None:
            raise ValueError(f"Follow {follow_id} not found")
        if follow.status != "open":
            raise ValueError(f"Follow {follow_id} already {follow.status}")

        follow.exit_time = datetime.now(UTC)
        follow.exit_reason = reason
        follow.status = "cancelled"
        db.commit()
        db.refresh(follow)
        return follow

    @staticmethod
    def list(
        db: Session,
        status: str = "open",
        pair: str | None = None,
        limit: int = 50,
    ) -> list[UserFollow]:
        """查询 — status='all' 返回全部。"""
        q = db.query(UserFollow)
        if status != "all":
            q = q.filter(UserFollow.status == status)
        if pair:
            q = q.filter(UserFollow.pair == pair)
        q = q.order_by(UserFollow.entry_time.desc()).limit(limit)
        return q.all()

    @staticmethod
    def get(db: Session, follow_id: int) -> UserFollow | None:
        return db.query(UserFollow).filter(UserFollow.id == follow_id).first()
