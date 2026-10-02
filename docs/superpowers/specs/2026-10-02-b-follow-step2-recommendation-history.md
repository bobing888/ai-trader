# B-Follow Step 2 + Recommendation History — Design Spec

**Status:** Draft (awaiting user approval)
**Date:** 2026-10-02
**Owner:** ai-trader / B-Follow track
**Refs:** experience-refinement §6.2.1, PR #26 (UserFollow schema), PR #25 (signals-v2), PR #24 (notif-ui), PR #23 (regime engine)

---

## 0. 目标（Goal）

让 ai-trader 上的「跟单」从**一次性手动登记**升级为**实时高灵敏度的可信信号驱动闭环**：

1. **每分钟持久化所有币种 + timeframe 的 AI 推荐决议**（不依赖用户访问）
2. **前端通过 WS 推送实时收到信号变化**（不等 30s refetch）
3. **跟单**能用「AI signal 反转」作为出场条件之一（用户期望的「高灵敏度」）
4. 整套**只接真实 K 线**（OKX/Binance），mock 模式不存历史 → 保证「可信度高」

---

## 1. 范围

### 1.1 包含（In-Scope）

| 类别 | 组件 |
|------|------|
| 数据 | `recommendation_history` 表（每分钟快照）|
| 服务 | `RecommendationRecorder`（每分钟扫所有 pair + timeframe 写库）|
| 服务 | `SignalChangeDetector`（按 3min 动量 + 2次确认 + regime flip 判反转）|
| 服务 | `FollowScheduler`（每 60s 拉 OPEN 列表，跑 SL/TP/expired/Signal 反转出场）|
| API | `/api/recommendations/history?pair=...&timeframe=...&limit=...`（查询历史）|
| API | `/api/recommendations/latest?pair=...&timeframe=...`（查询最新一帧）|
| API | `/api/recommendations/ws`（WS 推送，pair 订阅制）|
| API | `/api/follows/*` 完整 CRUD（Step 2 原定范围）|
| 前端 | `FollowsPage`（OPEN / CLOSED / CANCELLED 三档 tab）|
| 前端 | `RecommendationsPage` 每张卡「📌 跟单」按钮 → `FollowDialog`|
| 前端 | WS 客户端 hook `useSignalStream(pair, timeframe)` 收到推送后 invalidate react-query cache |
| 测试 | 单元 + 集成：recorder 写入、detector 3 种机制、scheduler 出场路径、API contract、前端 hook |

### 1.2 不包含（Out-of-Scope, Step 3+）

- ❌ trailing stop 移动止损
- ❌ freqtrade 实盘对接
- ❌ 多用户 / 鉴权 / 角色
- ❌ leader-copy 复制交易
- ❌ 信号历史回放 UI（仅 API 可查，不做时间轴图）
- ❌ PnL 真实账户对账
- ❌ 移动端 push notification（Web push 需 HTTPS 证书，kbkkk.com 没 SSL）

---

## 2. 架构（Architecture）

```
   ┌──────────────┐  WS 1m candle 推送   ┌──────────────────────────────────────────────────┐
   │  OkxWsClient │ ───────────────────► │            FastAPI Lifespan (single process)      │
   │  (existing)  │    6 路订阅          │                                                   │
   └──────────────┘                     │  RecommendationRecorder (asyncio task)            │
                                        │   • 1m K 线 confirm 后触发                         │
                                        │   • 本地重采样到 5m/15m/1h/1d                     │
                                        │   • 调 SignalAggregator.aggregate() (同步)         │
                                        │   • 写 recommendation_history 表                    │
                                        │   • 跟上一帧对比 → 推 SignalChangeBus              │
                                        │   • mock 模式整链跳过                              │
                                        └────────────┬────────────────────────────────────┘
                                                     │ bus 事件
                                                     ▼
                                        ┌──────────────────────────────────────────────┐
                                        │         SignalChangeBus (asyncio.Queue)        │
                                        └────────────┬────────────────────────────────────┘
                                                     │ fanout
                                       ┌─────────────┴──────────────┐
                                       ▼                            ▼
                                ┌────────────────┐         ┌──────────────────────┐
                                │ WS 推送 endpoint │         │ FollowScheduler       │  (asyncio task)
                                │ /api/            │         │ • bus 事件触发 detector │
                                │  recommendations/│         │ • 60s tick 兜底        │
                                │  ws              │         │ • 4 种出场检测         │
                                └────────────────┘         │   - stop_loss / target │
                                                             │   - expired            │
                                                             │   - consecutive_rev    │
                                                             │   - regime_flip        │
                                                             │ • 命中 → 写 CLOSED + pnl│
                                                             └──────────────────────────┘
                                                                       │
                                                                       ▼
                                                            NotificationService (existing)
                                                            → 前端 toast + K-line marker
```

**关键设计点：**
- **数据源**：recorder 复用 `okx_ws_client` 6 路 candle1m 订阅，**0** REST 调用（OKX 限速 20 req/s 远高于实际 0 req/s）
- **Recorder 调度策略**：每根 1m K 线 confirm 后触发；target timeframe 通过本地重采样生成
- **WS 推送**：按订阅 push（前端连接时送 `{pair, timeframe}` 列表；服务只 push 已订阅的变化）
- **FollowScheduler 双驱动**：bus 事件立刻响应（无延迟） + 60s tick 兜底（防止 bus 漏事件 + 处理 expired）

---

## 3. 数据模型

### 3.0 Recorder 数据源策略（关键修正）

**核心发现：** 6 个 pair × 1 个 1m candle WS 订阅 = 6 路复用，OKX 单 IP 限速 20 req/s 远低于 0.4 req/s 实际用量。

**架构：** recorder **不**主动 REST 拉 K 线。复用 `okx_ws_client.subscribe_candles(pair, "candle1m")` 拿实时 1m K 线，1m K 线确认后：
1. 缓存到 `RecorderState.candles_1m[pair]`（保留最近 200 根）
2. 对 4 个 timeframe（5m/15m/1h/1d）从 1m K 线**本地重采样**得到
3. 调 `SignalAggregator.aggregate()` 算推荐
4. 写库 + 触发 bus

**好处：**
- REST 调用从 24 次/分钟 → 0 次/分钟（WS 推送已含价格）
- 重采样逻辑跟 strategies 现有 get_klines 一致（用 `aggregator.py` 已有的方式）
- OKX 网络挂了 → WS 已自动重连，recorder 继续工作
- mock 模式下不走此路径

### 3.1 新增 `recommendation_history` 表

```python
class RecommendationOutcome(StrEnum):
    """每帧推荐结果的状态"""
    HAS_SIGNAL = "has_signal"          # has_signal=true, signal 非空
    NO_SIGNAL = "no_signal"            # has_signal=true, signal=None
    NO_DATA = "no_data"                # 拉 K 线失败 / 数据不足
    ERROR = "error"                    # aggregator 异常


class RecommendationHistory(Base):
    __tablename__ = "recommendation_history"
    __table_args__ = (
        Index("idx_reco_history_pair_tf_time", "pair", "timeframe", "scanned_at"),
        Index("idx_reco_history_scanned_at", "scanned_at"),  # 全局时间扫表
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    pair: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)

    # 信号决议快照
    has_signal: Mapped[bool] = mapped_column(Boolean, nullable=False)
    direction: Mapped[str | None] = mapped_column(String(10), nullable=True)  # long/short/null
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    regime: Mapped[str | None] = mapped_column(String(20), nullable=True)
    regime_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    contributing_strategies: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON 数组
    reasons: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON 数组
    suggested_leverage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_agreement_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fast_path: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 状态
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)  # RecommendationOutcome

    # 时序
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))

    # 数据源
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="okx")  # okx | binance
```

### 3.2 `UserFollow` 不变

PR #26 schema 已经定。Step 2 复用即可。

### 3.3 配置项（config.py 新增，pydantic-settings `AI_TRADER_` 前缀自动应用）

```python
# Pydantic 字段名 = 环境变量名（去掉 AI_TRADER_ 前缀）
recommendation_scan_interval: int = 60       # seconds
recommendation_pairs: list[str] = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "DOGE-USDT", "XRP-USDT"]
recommendation_timeframes: list[str] = ["5m", "15m", "1h", "1d"]
recommendation_history_retention_days: int = 7
follow_scan_interval: int = 60                # seconds
follow_max_hours: int = 24                    # expired 阈值
follow_default_stake_amount: float = 100.0    # PnL mock stake 默认（用户 2026-10-02 决定）
follow_max_loss_pct: float = 0.5              # PnL pnl_abs 上限（mock 演示用）
```

环境变量示例：`AI_TRADER_FOLLOW_DEFAULT_STAKE_AMOUNT=200`。

---

## 4. 服务层（Services）

**命名约定：所有服务用模块级 singleton + `set_xxx()` 注入**（跟 `notification_service` 一致，避免循环 import）

### 4.0 `SignalChangeBus`（轻量进程内 pub/sub）

```python
@dataclass
class SignalChangeEvent:
    pair: str
    timeframe: str
    previous: RecommendationHistory | None
    current: RecommendationHistory
    change_type: Literal["direction", "regime", "confidence", "no_signal", "first_emit"]


class SignalChangeBus:
    """
    进程内 asyncio 事件总线。
    - recorder emit SignalChangeEvent
    - FollowScheduler subscribe → 跑 detector
    - WS 推送 endpoint subscribe → fanout 给订阅浏览器
    """
    def __init__(self):
        self._subscribers: list[asyncio.Queue[SignalChangeEvent]] = []

    def subscribe(self) -> asyncio.Queue[SignalChangeEvent]:
        q: asyncio.Queue[SignalChangeEvent] = asyncio.Queue(maxsize=1024)
        self._subscribers.append(q)
        return q

    async def emit(self, event: SignalChangeEvent) -> None:
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("[bus] subscriber queue full, dropping %s", event)
```

### 4.1 `RecommendationRecorder`（数据源修正：WS 1m 推送驱动）

```python
class RecommendationRecorder:
    """
    订阅 OKX WS 1m K 线 → 缓存 → 本地重采样到 4 个 timeframe → 算推荐 → 写库 + emit bus。

    不主动 REST 拉 K 线（OKX 限速 20 req/s，WS 推送 0 消耗）。
    """

    def __init__(self, ws_client: OkxWsClient, bus: SignalChangeBus, db_session_factory):
        self._ws = ws_client
        self._bus = bus
        self._session = db_session_factory
        # 每个 (pair, channel) 一个订阅 queue
        self._candle_queues: dict[str, asyncio.Queue[dict]] = {}
        # pair → 最近 200 根 1m K 线
        self._candles_1m: dict[str, deque[dict]] = {}
        self._running = False
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        if self._running: return
        self._running = True
        for pair in settings.recommendation_pairs:
            q = await self._ws.subscribe_candles(pair, "candle1m")
            self._candle_queues[pair] = q
            self._tasks.append(asyncio.create_task(self._consume(pair, q)))
        logger.info("[recorder] started for %d pairs", len(self._candle_queues))

    async def stop(self) -> None:
        self._running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _consume(self, pair: str, queue: asyncio.Queue) -> None:
        """每条 1m K 线推送就触发一次 scan。"""
        while self._running:
            candle = await queue.get()  # 阻塞等 WS
            if not candle.get("confirm"):
                continue  # 跳过未确认 K 线（OKX confirm=False 意味着还在这一分钟内变动）
            self._push_candle(pair, candle)
            await self._scan_all_timeframes(pair)

    def _push_candle(self, pair: str, candle: dict) -> None:
        buf = self._candles_1m.setdefault(pair, deque(maxlen=200))
        buf.append(candle)

    async def _scan_all_timeframes(self, pair: str) -> None:
        for tf in settings.recommendation_timeframes:
            try:
                await self._scan_one(pair, tf)
            except Exception as e:
                logger.warning("[recorder] %s %s scan failed: %s", pair, tf, e)

    async def _scan_one(self, pair: str, timeframe: str) -> None:
        """本地重采样 1m → 目标 timeframe → 算推荐 → 写库 → 触发 bus。"""
        # 1. mock 模式跳过
        if settings.use_mock_data:
            return

        # 2. 取 1m 缓存 → 重采样到目标 timeframe
        candles_1m = list(self._candles_1m.get(pair, []))
        if len(candles_1m) < 60:
            await self._write_no_data(pair, timeframe, "insufficient_1m_history")
            return
        candles = _resample_ohlcv(candles_1m, timeframe)
        if not candles or len(candles) < 30:
            await self._write_no_data(pair, timeframe, "resample_too_short")
            return

        # 3. 算推荐（同步 — aggregator.aggregate() 不 await）
        try:
            signal = self._compute_signal(pair, timeframe, candles)
        except Exception as e:
            await self._write_error(pair, timeframe, str(e))
            return

        # 4. 写库（独立 session，Background task 不用 Depends）
        record = self._build_record(pair, timeframe, signal)
        with self._session() as db:
            db.add(record)
            db.commit()
            db.refresh(record)

        # 5. 查上一帧 + 触发 bus
        with self._session() as db:
            previous = self._get_previous(db, pair, timeframe, record.scanned_at)
        change_type = _classify_change(previous, record)
        if change_type != "no_change":
            await self._bus.emit(SignalChangeEvent(
                pair=pair, timeframe=timeframe,
                previous=previous, current=record,
                change_type=change_type,
            ))

    def _compute_signal(self, pair: str, tf: str, candles: list[dict]) -> AggregatedSignal:
        """调 strategies + aggregator。同步，不 await。"""
        from app.signals.aggregator import SignalAggregator
        from app.signals.regime import RegimeDetector
        regime_info = RegimeDetector().detect(candles, tf)
        strategy_results = [s.evaluate(candles, ...) for s in STRATEGY_INSTANCES]
        return SignalAggregator().aggregate(strategy_results, regime_info.regime, regime_info.confidence, tf)

    def _get_previous(self, db, pair, timeframe, before_ts) -> RecommendationHistory | None:
        return db.query(RecommendationHistory).filter(
            RecommendationHistory.pair == pair,
            RecommendationHistory.timeframe == timeframe,
            RecommendationHistory.scanned_at < before_ts,
        ).order_by(RecommendationHistory.scanned_at.desc()).first()

    def _build_record(self, pair, tf, signal) -> RecommendationHistory: ...
    async def _write_no_data(self, pair, tf, reason: str) -> None: ...
    async def _write_error(self, pair, tf, err: str) -> None: ...


def _resample_ohlcv(candles_1m: list[dict], timeframe: str) -> list[dict]:
    """
    从 1m OHLCV 列表重采样到目标 timeframe。
    timeframe ∈ {"5m", "15m", "1h", "1d"} → bucket_minutes = 5/15/60/1440
    """
    minutes = {"5m": 5, "15m": 15, "1h": 60, "1d": 1440}[timeframe]
    if not candles_1m:
        return []
    # 按 bucket ts 对齐
    buckets: dict[int, dict] = {}
    for c in candles_1m:
        ts = c["ts"]
        bucket_ts = (ts // (minutes * 60)) * (minutes * 60)
        if bucket_ts not in buckets:
            buckets[bucket_ts] = {"ts": bucket_ts, "o": c["o"], "h": c["h"], "l": c["l"], "c": c["c"], "vol": 0.0}
        b = buckets[bucket_ts]
        b["h"] = max(b["h"], c["h"])
        b["l"] = min(b["l"], c["l"])
        b["c"] = c["c"]  # 最后一根的 close
        b["vol"] += c["vol"]
    return sorted(buckets.values(), key=lambda x: x["ts"])
```

### 4.2 `SignalChangeDetector`（纯函数）

```python
def detect_reversal(
    follow: UserFollow,
    current: RecommendationHistory,
    previous: RecommendationHistory | None,
    lookback_history: list[RecommendationHistory],  # 最近 3 分钟 ~3 帧
) -> ReversalVerdict:
    """
    返回: ReversalVerdict(reversed: bool, reason: str | None)
    reason ∈ {"consecutive_reversal", "regime_flip", None}
    """
    # 机制 3：regime flip 优先（无需 2 次确认）
    if _is_regime_flip(follow, current):
        return ReversalVerdict(True, "regime_flip")

    # 机制 1+2：3 分钟动量 + 2 次确认
    if previous is None:
        return ReversalVerdict(False, None)
    if not _in_3min_window(lookback_history, follow):
        return ReversalVerdict(False, None)
    if _consecutive_reversal(follow, previous, current):
        return ReversalVerdict(True, "consecutive_reversal")

    return ReversalVerdict(False, None)
```

### 4.3 `FollowScheduler`

```python
class FollowScheduler:
    """
    监听 SignalChangeBus，每 60s 一次大轮询（兜底）：
    - bus 事件立刻触发 detector 评估
    - 60s tick 兜底（防止 bus 事件丢失 + expired 检测）
    """

    def __init__(self, bus: SignalChangeBus, db_session_factory):
        self._bus = bus
        self._session = db_session_factory
        self._running = False

    async def start(self) -> None:
        if self._running: return
        self._running = True
        self._bus_task = asyncio.create_task(self._bus_loop())
        self._tick_task = asyncio.create_task(self._tick_loop())

    async def _bus_loop(self) -> None:
        q = self._bus.subscribe()
        while self._running:
            event = await q.get()
            await self._handle_event(event)

    async def _tick_loop(self) -> None:
        while self._running:
            await asyncio.sleep(settings.follow_scan_interval)
            await self._scan_all_open_follows()

    async def _handle_event(self, event: SignalChangeEvent) -> None:
        if event.change_type == "no_change":
            return
        # 只处理 direction / regime 类变化（影响反转检测）
        if event.change_type in ("direction", "regime"):
            await self._scan_open_follows_for_pair(event.pair)

    async def _scan_all_open_follows(self) -> None:
        """每 60s 兜底：处理 expired + 反向 detector。"""
        with self._session() as db:
            open_follows = db.query(UserFollow).filter(UserFollow.status == "open").all()
        # 按 pair 去重拉最新信号（避免每条 follow 单独 query）
        latest_per_pair = self._get_latest_signals({f.pair for f in open_follows})
        for follow in open_follows:
            latest = latest_per_pair.get(follow.pair)
            await self._evaluate_and_close(follow, latest)

    async def _scan_open_follows_for_pair(self, pair: str) -> None:
        with self._session() as db:
            follows = db.query(UserFollow).filter(
                UserFollow.pair == pair, UserFollow.status == "open"
            ).all()
        latest = self._get_latest_signals({pair}).get(pair)
        for follow in follows:
            await self._evaluate_and_close(follow, latest)

    async def _evaluate_and_close(self, follow: UserFollow, current_signal) -> None:
        # 拉最新价格（实时价格 — 用 okx ticker 或 ws 推送）
        price = self._get_current_price(follow.pair)
        if price is None:
            return

        verdict = None
        # 价格出场
        if follow.stop_loss and price <= follow.stop_loss:
            verdict = ExitVerdict(True, "stop_loss", price)
        elif follow.target and price >= follow.target:
            verdict = ExitVerdict(True, "target", price)
        elif (datetime.now(UTC) - follow.entry_time).total_seconds() >= settings.follow_max_hours * 3600:
            verdict = ExitVerdict(True, "expired", price)
        # signal 反转
        if not verdict.should_exit and current_signal:
            prev, lookback = self._load_history(follow.pair, follow.timeframe or follow.timeframe)
            rev = detect_reversal(follow, current_signal, prev, lookback)
            if rev.reversed:
                verdict = ExitVerdict(True, rev.reason, price)

        if verdict.should_exit:
            await self._close(follow, verdict)

    async def _close(self, follow: UserFollow, verdict: ExitVerdict) -> None:
        with self._session() as db:
            # SELECT ... FOR UPDATE 锁避免并发 close
            locked = db.query(UserFollow).filter(
                UserFollow.id == follow.id, UserFollow.status == "open"
            ).with_for_update().first()
            if not locked:
                return  # 已被并发 close
            pnl_pct, pnl_abs = FollowService.compute_pnl(
                locked.entry_price, verdict.exit_price,
                locked.direction, locked.leverage, locked.stake_amount
            )
            locked.exit_price = verdict.exit_price
            locked.exit_time = datetime.now(UTC)
            locked.exit_reason = verdict.reason
            locked.pnl_pct = pnl_pct
            locked.pnl_abs = pnl_abs
            locked.status = "closed"
            db.commit()
        # 通知
        notification_service.emit(FollowClosedNotification(...))
```

### 4.4 `FollowService`（业务层 — 写 / 出场 / 撤销 / PnL mock）

```python
class FollowService:
    def create(db, payload) -> UserFollow: ...
    def cancel(db, follow_id, reason="manual") -> UserFollow: ...
    def close(db, follow_id, exit_price, exit_reason) -> UserFollow: ...
    def list(db, status=None, pair=None, limit=50) -> list[UserFollow]: ...
    def get(db, follow_id) -> UserFollow | None: ...

    @staticmethod
    def compute_pnl(
        entry_price: float,
        exit_price: float,
        direction: str,
        leverage: int,
        stake_amount: float = 100.0,
    ) -> tuple[float, float]:
        """
        mock pnl — 跟 freqtrade close_profit 公式一致。
        默认 stake_amount=100.0 USDT（用户 2026-10-02 决定）。
        """
        if direction == "long":
            pnl_pct = (exit_price - entry_price) / entry_price * leverage
        else:
            pnl_pct = (entry_price - exit_price) / entry_price * leverage
        pnl_abs = pnl_pct * stake_amount
        return round(pnl_pct, 4), round(pnl_abs, 2)
```

UserFollow schema 需新增字段：`stake_amount: float = 100.0`（PR #26 改造工作量，spec 划线给 PR #27 提）。

---

## 5. API 端点

### 5.1 Follows

| Method | Path | Body | Returns |
|--------|------|------|---------|
| POST | `/api/follows` | `{pair, timeframe, direction, entry_price?, stop_loss?, target?, leverage?, stake_amount?, source?, recommendation_id?, notes?}` | `UserFollowOut` |
| GET | `/api/follows` | query: `status?` (open/closed/cancelled/all), `pair?`, `limit?` (default 50, max 500) | `FollowListOut{items, total}` |
| GET | `/api/follows/{id}` | — | `UserFollowOut` |
| POST | `/api/follows/{id}/close` | `{exit_price, exit_reason?}` | `UserFollowOut` |
| POST | `/api/follows/{id}/cancel` | `{reason?}` | `UserFollowOut` |

### 5.2 Recommendations

| Method | Path | Returns |
|--------|------|---------|
| GET | `/api/recommendations/history?pair=BTC-USDT&timeframe=1h&limit=60` | `RecommendationHistoryList` |
| GET | `/api/recommendations/latest?pair=BTC-USDT&timeframe=1h` | `RecommendationHistoryOut` |
| WS | `/api/recommendations/ws` | 推送 `{type: "signal_change", pair, timeframe, current, previous, change_type}` |

### 5.3 Pydantic Schemas（app/schemas/）

```python
class UserFollowOut(BaseModel):
    id: int
    recommendation_id: int | None
    pair: str
    timeframe: str
    direction: str
    entry_price: float | None
    stop_loss: float | None
    target: float | None
    leverage: int
    status: str
    pnl_pct: float | None
    pnl_abs: float | None
    entry_time: datetime
    exit_time: datetime | None
    exit_price: float | None
    exit_reason: str | None
    source: str
    notes: str | None
    created_at: datetime
    updated_at: datetime

class FollowListOut(BaseModel):
    items: list[UserFollowOut]
    total: int

class RecommendationHistoryOut(BaseModel):
    id: int
    pair: str
    timeframe: str
    has_signal: bool
    direction: str | None
    confidence: float | None
    regime: str | None
    regime_confidence: float | None
    suggested_leverage: int | None
    fast_path: bool
    outcome: str
    scanned_at: datetime
    source: str
```

---

## 6. 错误处理

| 场景 | 处理 |
|------|------|
| Recorder 拉 K 线失败 | outcome=NO_DATA, 写库（保留时序完整性），不 emit bus 事件 |
| Recorder 算 signal 抛异常 | outcome=ERROR, 写库, log warning, 不 emit |
| FollowScheduler 拉最新 signal 失败 | 该次 tick 跳过该 follow（不误判 expired / 反转） |
| 同 pair 多个 OPEN follow | 允许多笔并存（schema 没说唯一） |
| 并发 close 同一笔 | DB 层用 `SELECT ... FOR UPDATE` (SQLite 串行化) + status guard |
| 撤销非 OPEN 状态 | 409 Conflict |
| close 非 OPEN 状态 | 409 Conflict |
| expired 出场时已 CLOSED | status guard 跳过 |
| WS 客户端断开 | 服务端 cleanup subscription；不推送 |
| mock 模式下 Recorder | 跳过（不写库，不推 WS） |
| follow 跟 AI 跟单后 AI 反转 | detector 触发 `consecutive_reversal` 或 `regime_flip` |
| follow 来源 = manual + 出场触发 ai_signal_reversed | 仍然触发（设计目的：无论手动/AI 跟单，都受同一信号反转规则保护） |

---

## 7. 测试策略

### 7.1 单元测试（必须全绿）

| 文件 | 覆盖点 |
|------|------|
| `test_recommendation_recorder.py` | 写入 happy path, K 线失败→NO_DATA, mock 模式不写, bus event 触发 |
| `test_signal_change_detector.py` | 3 种机制 8 个 case: regime_flip 立即 / 3min 窗口外不触发 / 2次确认失败 / 2次确认成功 / mock 跳过 / 没有 previous 不触发 / lookback 缺帧容忍 |
| `test_follow_service.py` | create / close / cancel / PnL 计算（long/short/leverage）/ status 转换 / 并发 close 防护 |
| `test_follow_scheduler.py` | 4 种出场检测 (SL/TP/expired/ai_signal_reversed) / 价格拉取失败跳过 / 没有 OPEN 列表 noop |
| `test_follows_api.py` | 4 个 endpoint FastAPI TestClient + 错误码 (409/422/404) |
| `test_recommendations_api.py` | history/latest/ws 三条路径 + mock 模式禁用 |

### 7.2 集成测试（必须 1 个）

`test_integration_follow_lifecycle.py`：
- 启动 lifespan → 触发 recorder → 触发 follow scheduler → 验证 DB 状态
- 手工 step 走完：创建 follow → mock signal 触发 SL → 看到 CLOSED + pnl
- 验证 NotificationService 收到事件

### 7.3 手动验证（生产前）

- `curl POST /api/follows` 创建跟单
- 等 60s → `curl GET /api/follows/{id}` 看到状态未变
- 在 OKX 测试环境（kbkkk.com）触发出场条件 → 60s 内看到 CLOSED
- 浏览器打开 `/follows` 看到 UI 实时刷新

### 7.4 前端测试

`__tests__/FollowsPage.test.tsx`：
- 三档 tab 切换 + 列表展示
- 「关闭跟单」按钮 → 调 API → 状态更新
- 「跟单」对话框 → 填表 → 提交 → 创建

`__tests__/useSignalStream.test.ts`：
- WS 连接成功 → 收到 signal_change → invalidates query
- 断线重连（mock 断开 → 重连成功）

### 7.5 场景覆盖矩阵（按规则 4 强制）

| 场景 | 验证 |
|------|------|
| 单跟单 1H long 正常 SL 出场 | 单测 + 集成 |
| 单跟单 4H short TP 出场 | 单测 |
| 单跟单 15m 24h expired | 单测 |
| 跟 AI 推荐 1H long + AI 5min 后反转 | detector 单测 + 集成 |
| 跟 AI 推荐 1H long + regime bull→bear | detector 单测 |
| 手动跟单（manual source） + AI 反转 | detector 单测（应触发） |
| mock 模式下 Recorder 不写 | recorder 单测 |
| mock 模式下 WS 推送不活跃 | api 单测 |
| 前端 FollowsPage 0 跟单（空状态）| 截图 |
| 前端 FollowsPage OPEN 1 / CLOSED 5 | 截图 |
| 前端 RecommendationsPage 跟单按钮 → 弹窗 → 创建 | 截图 |

---

## 8. 改动清单（文件级）

### 8.1 后端新增

```
backend/app/db/models.py            # +RecommendationHistory, RecommendationOutcome
backend/app/schemas/follows.py      # Pydantic
backend/app/schemas/recommendations.py
backend/app/services/follow_service.py
backend/app/services/follow_scheduler.py
backend/app/services/recommendation_recorder.py
backend/app/services/signal_change_detector.py
backend/app/services/signal_change_bus.py      # 进程内 asyncio.Queue
backend/app/api/follows.py
backend/app/api/recommendations.py
backend/app/api/recommendations_ws.py
backend/tests/test_recommendation_recorder.py
backend/tests/test_signal_change_detector.py
backend/tests/test_follow_service.py
backend/tests/test_follow_scheduler.py
backend/tests/test_follows_api.py
backend/tests/test_recommendations_api.py
backend/tests/test_integration_follow_lifecycle.py
```

### 8.2 后端修改

```
backend/app/config.py              # +6 个配置项
backend/app/main.py                # lifespan: 启动 recorder + scheduler + bus
backend/app/db/session.py          # init_db() 注册 RecommendationHistory
backend/app/api/__init__.py        # 暴露新 router
backend/pyproject.toml             # 如有需要（暂不引入新依赖）
```

### 8.3 前端新增

```
frontend/src/pages/FollowsPage.tsx
frontend/src/components/follows/FollowCard.tsx
frontend/src/components/follows/FollowDialog.tsx           # 跟单创建对话框
frontend/src/components/follows/PnLBadge.tsx
frontend/src/hooks/useSignalStream.ts                       # WS 订阅
frontend/src/stores/followStore.ts                          # 或 react-query 直连
frontend/src/__tests__/FollowsPage.test.tsx
frontend/src/__tests__/useSignalStream.test.ts
```

### 8.4 前端修改

```
frontend/src/App.tsx               # +/follows 路由
frontend/src/lib/api.ts            # +follows/recommendations 5 个调用
frontend/src/components/layout/Sidebar.tsx   # +「跟单」nav
frontend/src/pages/RecommendationsPage.tsx   # 每张卡 +「📌 跟单」按钮
```

---

## 9. 风险与回退

### 9.1 风险

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| OKX REST 限速 | **低**（WS 推送 0 REST 消耗，20 req/s 限制 vs 实际 0 req/s）| — | 监控 50011；如需回归 REST 模式保留 fallback |
| SQLite 写入并发 | 低 | recorder + scheduler 同时写 | SQLite WAL 模式（已在用）+ 每事务短 + session 短 |
| WS 客户端累积订阅 | 中 | 内存泄漏 | 定期清理 inactive subscription (no message > 5min) |
| 信号反转误触发 | 中 | 提前出场 → 用户亏损 | 2 次确认 + 3min 窗口（已设计）|
| Recorder 写库失败 | 低 | 历史缺帧 | 重试 3 次后落 ERROR record |
| ai_signal_reversed 在 regime=choppy 噪声 | 中 | 频繁出场 | choppy 排除 regime_flip（只在 bull/bear flip + crisis 触发）|
| 进程重启后 recorder 没有 previous | 中 | 重启 1 分钟内 detector 全部返回 None | `_get_previous` 从 DB 查最新一帧做基线（不是 None）|
| 前端 WS 断线 + react-query stale | 中 | 用户看到旧信号 | `useSignalStream` 失败时 fallback refetchInterval=30s |

### 9.2 回退

- Step 2 整体 ship 后如果发现 detector 误判率 > 10%：disable `consecutive_reversal`，仅保留 `regime_flip`（硬指标）
- WS 推送如果 client 不稳定：保留 REST polling fallback
- RecommendationHistory 数据量增长：cron 每天清 7 天前的

### 9.3 数据保留

`recommendation_history` 默认保留 7 天，每天凌晨 3 点（lifespan 启动时 +24h 调度）清旧。

---

## 10. 验证清单（ship 前必走）

- [ ] 单测全绿（`pytest backend/tests/ -v`）
- [ ] 集成测试 1 个全绿
- [ ] lint 全绿（ruff / mypy）
- [ ] 手动 curl 4 个 follow endpoint + 2 个 recommendation endpoint
- [ ] 前端 vitest 全绿
- [ ] 前端 typecheck 全绿
- [ ] 浏览器 11 场景截图（场景覆盖矩阵）
- [ ] 部署 kbkkk-prod（按规则 9）→ 线上 curl 验证 → 浏览器访问

---

## 11. 后续 Step（明确划线）

- **Step 3**（trailing stop）：需 schema 扩展 + backtest 后定默认参数
- **Step 4**（ai_signal_reversed 已经包含在 Step 2 — 故下面升级项）
- **Step 4**（recommendation replay UI）：API 已支持，前端时间轴图
- **Step 5**（multi-user 鉴权）：spec 重写
- **Step 6**（freqtrade 实盘对接）：需要先解决 PR #18-21 系列 OKX 网络稳定性问题
- **Step 7**（leader-copy 复制交易）：独立子系统

---

**Spec 完，等用户批准。批准后进 writing-plans 拆任务。**
