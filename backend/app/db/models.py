"""SQLAlchemy ORM 模型 — Strategy + Follow 持久化"""

from datetime import UTC, datetime, timezone
from enum import StrEnum

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserFollowStatus(StrEnum):
    """UserFollow.status 合法值（与 §6.2.1 schema + API 一致）。"""
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class FollowSource(StrEnum):
    """UserFollow.source 合法值。"""
    AI_RECOMMENDATION = "ai_recommendation"
    MANUAL = "manual"


class Strategy(Base):
    """交易策略元数据。

    `code` 字段保存策略的 Python 源码或 JSON 配置（取决于 strategy_type）。
    """

    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    strategy_type: Mapped[str] = mapped_column(String(40), nullable=False, default="custom")
    # source: manual | github:<owner/repo> | builtin
    source: Mapped[str] = mapped_column(String(120), nullable=False, default="manual")
    # parameters 是策略参数 (dict)
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # code 是策略源码（如果有）
    code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # status: enabled | disabled
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="enabled")
    # 权重（用于组合权重投票）
    weight: Mapped[float] = mapped_column(nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class UserFollow(Base):
    """用户跟单记录（§6.2.1 B-Follow schema）。

    与 AI recommendations 双表分离：跟单时 snapshot AI 价位，但允许用户
    手动覆盖 entry/stop/target。PnL mock 计算（不接 freqtrade 实盘）。

    状态机: OPEN → CLOSED（出场）| CANCELLED（撤销未入场）。
    """

    __tablename__ = "user_follows"
    __table_args__ = (
        Index("idx_user_follows_status", "status", "entry_time"),
        Index("idx_user_follows_pair", "pair", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 可空 — 用户手填跟单时为 None
    recommendation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    pair: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # long|short|neutral

    # 实际入场价 — 跟单时 snapshot AI 价位，用户可手动覆盖
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    target: Mapped[float | None] = mapped_column(Float, nullable=True)
    leverage: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # 状态机 — 用 str 列 + 枚举校验
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=UserFollowStatus.OPEN.value,
    )

    # PnL mock — 出场后填
    pnl_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl_abs: Mapped[float | None] = mapped_column(Float, nullable=True)

    # mock 跟单本金 USDT（默认 100.0；用户 2026-10-02 决定）
    stake_amount: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)

    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(
        String(40), nullable=True,  # manual|stop_loss|target|expired|ai_signal_reversed
    )

    source: Mapped[str] = mapped_column(
        String(40), nullable=False, default=FollowSource.MANUAL.value,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── D3: live trailing stop + partial TP ──
    trailing_stop_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    partial_tp_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    current_stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit_1_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit_2_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    entry_atr: Mapped[float | None] = mapped_column(Float, nullable=True)
    partial_tp_taken: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    remaining_size_pct: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    entry_price_ref: Mapped[float | None] = mapped_column(Float, nullable=True)
    # D1: persisted from recommendation snapshot
    risk_reward_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class RecommendationOutcome(StrEnum):
    """每帧推荐决议的状态（B-Follow Step 2 spec §3.1）。

    HAS_SIGNAL = signal 已产出且非空 → 正常业务路径
    NO_SIGNAL  = 信号引擎正常但无共识 → 记录时序供回看
    NO_DATA    = K 线不足 / recorder 启动初期 → 不误判、不 emit bus
    ERROR      = aggregator 异常 → log + 跳过+ 排查用
    """

    HAS_SIGNAL = "has_signal"
    NO_SIGNAL = "no_signal"
    NO_DATA = "no_data"
    ERROR = "error"


class OutcomeLabel(StrEnum):
    """单笔持仓的实际出场结果（Phase 1 signal credibility）。

    PENDING  = 持仓中（outcome_worker 尚未评估）
    HIT_TP   = 触达止盈位
    HIT_SL   = 触达止损位
    EXPIRED  = 超过 max_hold_minutes 强制出场
    HOLD     = 到评估时间仍未触发任何条件
    """

    PENDING = "pending"
    HIT_TP = "hit_tp"
    HIT_SL = "hit_sl"
    EXPIRED = "expired"
    HOLD = "hold"


class RecommendationHistory(Base):
    """每分钟持久化的推荐决议快照（B-Follow Step 2 spec §3.1）。

    recorder 写, recorder + scheduler 读 — 由 recorder 触发信号反转检测。
    历史保留 7 天（cron 在 lifespan 24h 调度）。
    """

    __tablename__ = "recommendation_history"
    __table_args__ = (
        Index("idx_reco_history_pair_tf_time", "pair", "timeframe", "scanned_at"),
        Index("idx_reco_history_scanned_at", "scanned_at"),
        # Phase 1: calibration training 需要按 timeframe + outcome 扫描
        Index("idx_reco_history_tf_outcome", "timeframe", "outcome_label"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    pair: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)

    # 信号决议快照（None 表示该字段在该帧不适用 — 例如 NO_DATA 时全 NULL）
    has_signal: Mapped[bool] = mapped_column(nullable=False)
    direction: Mapped[str | None] = mapped_column(String(10), nullable=True)  # long|short|null
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    regime: Mapped[str | None] = mapped_column(String(20), nullable=True)  # bull|bear|choppy|crisis
    regime_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    contributing_strategies: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    reasons: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    suggested_leverage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_agreement_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fast_path: Mapped[bool] = mapped_column(nullable=False, default=False)

    outcome: Mapped[str] = mapped_column(String(20), nullable=False)  # RecommendationOutcome

    # 时序
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(UTC),
    )

    # 数据源 — 记录实际 OKX REST 调用的 source（recorder 复用 okx_ws）
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="okx")

    # ── Phase 1 signal credibility（outcome_worker 写入）──
    # 校准后的 confidence (0~1); NULL = calibrator 尚未训练 / 样本不足
    calibrated_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 成本感知后的预期净 PnL（bps）：confidence * target_pct - round_trip_cost
    net_pnl_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 持仓分钟数（outcome_worker 写入）
    holding_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 出场 label（PENDING/HIT_TP/HIT_SL/EXPIRED/HOLD）
    outcome_label: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # 实际净 PnL（扣 fee + slippage 后）；NULL 表示未出场
    pnl_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 实际出场时间
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── D1: actionable execution levels (ATR-based) ──
    entry_levels_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON [{price, size_pct, label}]
    stop_loss_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit_1_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit_2_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    atr: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_reward_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── D2: signal quality gate ──
    quality: Mapped[str | None] = mapped_column(String(20), nullable=True)  # high|medium|low|reject
    quality_reasons_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array

    # ── 2026-10-03: 进/离场时间窗口（分钟）──
    entry_window_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exit_window_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)


class BacktestRun(Base):
    """Walk-forward 回测运行记录（Phase 1 signal credibility）。

    每次 POST /api/backtest 写入一行；run.status 用于同 symbol 串行化（409 防护）。
    """

    __tablename__ = "backtest_runs"
    __table_args__ = (
        Index("idx_backtest_runs_symbol_status", "symbol", "status"),
        Index("idx_backtest_runs_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 输入
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    strategies: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    fee_taker_bps: Mapped[float] = mapped_column(Float, nullable=False, default=8.0)
    slippage_bps: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    min_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.6)
    target_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.005)
    stop_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.003)
    max_hold_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)

    # 时序
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 摘要
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hit_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    net_pnl_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sharpe_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # 净值曲线（List[Dict] = [{ts, equity}, ...]）
    equity_curve: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # 状态机
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")  # running|done|error
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class BacktestTrade(Base):
    """单次回测内的每笔虚拟成交（Phase 1 signal credibility）。

    run_id 关联到 BacktestRun。
    """

    __tablename__ = "backtest_trades"
    __table_args__ = (
        Index("idx_backtest_trades_run_id", "run_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False)  # FK logical to BacktestRun.id

    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    strategy_name: Mapped[str] = mapped_column(String(60), nullable=False)

    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_price: Mapped[float] = mapped_column(Float, nullable=False)

    raw_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    calibrated_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    target_pct: Mapped[float] = mapped_column(Float, nullable=False)
    stop_pct: Mapped[float] = mapped_column(Float, nullable=False)

    gross_pnl_pct: Mapped[float] = mapped_column(Float, nullable=False)
    fee_pct: Mapped[float] = mapped_column(Float, nullable=False)
    slippage_pct: Mapped[float] = mapped_column(Float, nullable=False)
    net_pnl_pct: Mapped[float] = mapped_column(Float, nullable=False)

    outcome: Mapped[str] = mapped_column(String(20), nullable=False)  # HIT_TP/HIT_SL/EXPIRED/HOLD
    holding_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
