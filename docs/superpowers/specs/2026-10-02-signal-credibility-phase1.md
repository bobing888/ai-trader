# Signal Credibility Phase 1 — Calibration + Cost-Aware Backtest

**Status:** Approved by user (2026-10-02 19:08 UTC+8)
**Date:** 2026-10-02
**Owner:** ai-trader / Signal Credibility track
**Refs:** docs/architecture/github-survey-trend-2026-10-02.md, PR #26 (UserFollow), PR #25 (signals-v2), Step 2 spec (`2026-10-02-b-follow-step2-recommendation-history.md`), `backend/scripts/backtest_confluence.py` (offline script, NOT integrated into API)

---

## 0. 目标（Goal）

让 ai-trader 的**推荐单 confidence 数值**从「规则打分」升级为「数据驱动、可回测、可验证」的真实胜率估计，并在前端演示完整的 walk-forward 回测结果。

1. **每个 recommendation 的 confidence 数值 = 该 bin 真实胜率**（经 per-timeframe isotonic 校准）
2. **每个 timeframe 的策略池**在「过去 N 天」的真实命中率 / Sharpe / 最大回撤可查
3. **回测与推荐信号**都感知交易成本（OKX taker 0.08% / maker 0.02% / 滑点 0.05%）
4. **前端 BacktestPage** 从 100% mock 改造为调真实 `/api/backtest`
6. 整套只接真实 K 线（OKX 公开数据），mock 模式不存历史 → 保证可信度

---

## 1. 范围（Scope）

### 1.1 包含（In-Scope）

| 类别 | 组件 |
|------|------|
| DB schema | `RecommendationHistory` 表加 `pnl_pct`、`holding_minutes`、`outcome_label`、`calibrated_confidence` 字段 |
| DB schema | 新表 `BacktestRun`（存回测元数据 + 摘要指标） |
| DB schema | 新表 `BacktestTrade`（存每次回测的每笔模拟成交） |
| 校准模块 | `app/signals/calibration.py`（per-timeframe Isotonic regression）|
| 成本模型 | `app/signals/cost_model.py`（OKX fee + slippage + min_hold/min_profit 阈值）|
| 服务 | `outcome_worker.py`（每 5 分钟扫未 close 的 RecommendationHistory → 模拟出场 → 写 pnl/outcome）|
| 服务 | `calibration_trainer.py`（每日 02:00 cron → 重训 6 个 isotonic 模型）|
| 服务 | `aggregator.py` 集成：每个 signal → cost_model + calibration → calibrated_confidence + net_pnl_estimate |
| API | `POST /api/backtest`（body: symbol, timeframe, strategies[], days, fee_bps, slippage_bps）→ walk-forward 回测 → JSON: equity_curve[], per_trade[], sharpe, max_dd, hit_rate, net_pnl |
| API | `GET /api/backtest/runs`（查历史回测记录）|
| API | `GET /api/backtest/runs/{id}`（查单次回测明细）|
| API | `POST /api/calibration/retrain`（手动触发重训）|
| API | `GET /api/calibration/status`（查 6 个校准器状态）|
| CLI | `scripts/calibrate.py`（独立跑 calibration 训练）|
| CLI | `scripts/backtest_engine.py`（独立跑回测，输出 JSON 到 stdout）|
| 前端 | `BacktestPage.tsx` 改造：删除 mock，调 `/api/backtest` |
| 前端 | `lib/backtestApi.ts`（API 客户端 + zod schema）|
| 前端 | `components/EquityCurve.tsx`（recharts，净 PnL 曲线 + drawdown 阴影）|
| 测试 | 单元 + 集成：calibration Brier < 0.15、cost_model 单边费率、outcome_worker 出场路径、backtest 端到端、前端契约 |

### 1.2 不包含（Out-of-Scope, Phase 2/3+）

- ❌ ML 模型训练（XGBoost/Transformer/LOB 微结构）— Phase 2/3
- ❌ freqtrade 实盘对接
- ❌ 多用户 / 鉴权 / 角色
- ❌ trailing stop
- ❌ 移动端 push notification
- ❌ 自动部署 / 生产热更 — 单独 PR 处理
- ❌ 真实账户成交额验证（账户端 PnL 对账）— Phase 3

---

## 2. 架构（Architecture）

```
                            ┌────────────────────────────────────┐
                            │      现有信号流 (PR #25)           │
                            │  K 线 → strategy_pool             │
                            │  → aggregator (raw_confidence)   │
                            └──────────────────┬────────────────┘
                                               │
                ┌──────────────────────────────┼──────────────────────────────┐
                ▼                              ▼                              ▼
    ┌──────────────────────┐      ┌──────────────────────────┐     ┌──────────────────────────┐
    │ cost_model.py        │      │ calibration.py            │     │ outcome_worker.py        │
    │ • taker 0.08%        │      │ • per-tf Isotonic        │     │ • 5min 扫              │
    │ • maker 0.02%        │      │ • train: history.Rec.    │     │ • check TP/SL/expired   │
    │ • slippage 0.05%     │      │   + 真实 PnL             │     │ • write pnl/outcome    │
    │ • min_hold 5m        │      │ • predict: calibrated_p  │     │   → RecommendationH.    │
    │ • min_profit 0.10%   │      │ • retrain cron: 02:00    │     └──────────────────────────┘
    └──────────┬───────────┘      └───────────┬──────────────┘
               │                              │
               └──────────────┬───────────────┘
                              ▼
              ┌──────────────────────────────────┐
              │ aggregator.py (MODIFIED)         │
              │ • raw_confidence                 │
              │   → cost_model.estimate_pnl()    │
              │     → calibration.calibrate()    │
              │     → calibrated_confidence      │
              │     → net_pnl_estimate           │
              └──────────────────┬───────────────┘
                                 ▼
                  RecommendationHistory (extended)
                  ├─ raw_confidence: Float
                  ├─ calibrated_confidence: Float (NEW)
                  ├─ net_pnl_estimate: Float (NEW)
                  ├─ holding_minutes: Int (NEW)
                  ├─ outcome_label: StrEnum (NEW)
                  │   → PENDING/HIT_TP/HIT_SL/EXPIRED/HOLD
                  └─ pnl_pct: Float (NEW, after close)

═══════════════════════════════════════════════════════════════════════════════════════════════

   ┌───────────────────────────────────────────────────────────────────────────────────────┐
   │                            POST /api/backtest                                         │
   │  body: { symbol, timeframe, strategies[], fee_taker_bps, slippage_bps, days }         │
   └───────────────────────────────────────────────────────────────────────────────────────┘
                │
                ▼ backtest_engine.py
                │
                ├─ 1. 拉真实 K 线 (OKX/Binance) → 过去 N 天 × requested timeframe
                │
                ├─ 2. walk-forward CV: 70% train + 30% test (e.g. 30 天 train + 7 天 test)
                │
                ├─ 3. per-bar 模拟:
                │     • strategy_pool.evaluate(bar) → raw_signal
                │     • cost_model.estimate_entry_fee()
                │     • cost_model.estimate_exit_fee()
                │     • if raw_signal.confidence >= 0.6 AND volatility < regime cap:
                │         → open_virtual_trade(bar.close, target=+0.5%, stop=-0.3%)
                │         → track_until(next_bar OR max_hold)
                │
                ├─ 4. 计算指标:
                │     • net_pnl (after fees)
                │     • hit_rate
                │     • sharpe_ratio
                │     • max_drawdown
                │     • equity_curve[]
                │
                ├─ 5. 写 BacktestRun + BacktestTrade × N
                │
                └─ 6. 返 JSON
```

---

## 3. 关键决策（Key Decisions）

| 决策 | 选择 | 理由 |
|------|------|------|
| 校准算法 | **Isotonic regression per-timeframe** | 比 Platt 更准、对小样本稳定、对非线性响应好；token 充足 |
| Fee 默认值 | OKX taker 0.08% / maker 0.02% | 用户做加杠杆超短线 = taker 为主 |
| Slippage 模型 | 固定 0.05% 默认 + ATR-adaptive fallback | 1m/5m 滑点大，简化用固定值 |
| min_hold | 5 min（防止 1m/5m 噪声）|
| 校准触发 | cron daily 02:00 + 手动 POST /api/calibration/retrain | 自动 + 可控 |
| Walk-forward split | 70/30 with 5-day embargo | 防 look-ahead |
| Outcome label 枚举 | PENDING / HIT_TP / HIT_SL / EXPIRED / HOLD | 5 状态简单清晰 |
| Calibration 字段 | `calibrated_confidence: Float nullable`（NULL 表示尚未校准）| 渐进上线，旧记录 NULL |
| Backtest 默认 days | 30（可在 API 改）| 平衡速度与样本量 |
| 出场规则（虚拟）| target +0.5% / stop -0.3% / max_hold 60min | 1m/5m/15m 三档可配 |

---

## 4. 数据模型扩展

### 4.1 `RecommendationHistory`（MODIFY）

```python
# 已有字段（spec B-Follow Step 2）
id, pair, timeframe, created_at, direction, raw_confidence,
strategy_signals (JSON), regime, etc.

# 新增字段（Phase 1）
calibrated_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
#   → 经 per-tf Isotonic 校准后的真实胜率估计；NULL 表示尚未校准（默认状态）
net_pnl_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
#   → cost_model 估算的「若按当前信号入场的预期净 PnL (bps)」
holding_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
#   → outcome_worker 写入；NULL 表示未出场
outcome_label: Mapped[str | None] = mapped_column(String(20), nullable=True)
#   → OutcomeLabel 枚举: PENDING/HIT_TP/HIT_SL/EXPIRED/HOLD
pnl_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
#   → 实际净 PnL (扣 fee + slippage 后)
closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
#   → outcome_worker 写入的实际 close 时间
```

**索引**：`(timeframe, created_at, outcome_label)`、`(timeframe, outcome_label, pnl_pct)` 用于校准训练。

### 4.2 新表 `BacktestRun`

```python
class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: int (PK)
    symbol: str (e.g. "BTC-USDT")
    timeframe: str (e.g. "1h")
    strategies: JSON (List[str], e.g. ["MomentumStrategy", "BreakoutStrategy"])
    days: int (e.g. 30)
    fee_taker_bps: float (e.g. 8.0)
    slippage_bps: float (e.g. 5.0)
    min_confidence: float (e.g. 0.6)
    target_pct: float (e.g. 0.005)
    stop_pct: float (e.g. 0.003)
    max_hold_minutes: int (e.g. 60)
    started_at: datetime
    finished_at: datetime
    total_trades: int
    hit_rate: float (0-1)
    net_pnl_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    equity_curve: JSON (List[{ts, equity}])
    status: str (running/done/error)
    error_message: str | None
```

### 4.3 新表 `BacktestTrade`

```python
class BacktestTrade(Base):
    __tablename__ = "backtest_trades"

    id: int (PK)
    run_id: int (FK to BacktestRun.id)
    symbol: str
    timeframe: str
    strategy_name: str
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    raw_confidence: float
    calibrated_confidence: float | None
    target_pct: float
    stop_pct: float
    gross_pnl_pct: float (未扣费)
    fee_pct: float (本次往返已扣)
    slippage_pct: float
    net_pnl_pct: float
    outcome: str (HIT_TP/HIT_SL/EXPIRED/HOLD)
    holding_minutes: int
```

---

## 5. 模块签名（接口契约）

### 5.1 `app/signals/cost_model.py`

```python
@dataclass
class CostEstimate:
    entry_fee_pct: float          # 入场费率 (e.g. 0.08%)
    exit_fee_pct: float           # 出场费率
    slippage_pct: float           # 滑点 (e.g. 0.05%)
    total_round_trip_pct: float   # 往返合计
    net_pnl_estimate: float       # raw_signal.confidence * target_pct - total_round_trip

def estimate_cost(side: Literal["entry", "exit"]) -> float:
    """OKX taker 默认 0.08% / maker 默认 0.02%。可通过 env var 覆盖。"""

def estimate_round_trip_cost() -> float:
    """单笔往返总成本 = entry_fee + exit_fee + slippage。"""

def is_profitable_threshold(target_pct: float, confidence: int) -> bool:
    """target_pct * confidence > total_round_trip 才算「有 alpha」。"""
```

### 5.2 `app/signals/calibration.py`

```python
@dataclass
class CalibrationModel:
    timeframe: str                    # 1m/5m/15m/1h/4h/1d
    isotonic: IsotonicRegression       # sklearn-like 实现
    train_size: int
    train_brier_score: float
    trained_at: datetime
    is_ready: bool

_calibrators: dict[str, CalibrationModel] = {}  # module-level cache

def get_calibrator(timeframe: str) -> CalibrationModel:
    """懒加载：先读 .pkl 文件，若无则返 None。"""

def train_calibrator(
    timeframe: str,
    samples: list[tuple[float, float]],   # (raw_confidence, actual_pnl_pct)
) -> CalibrationModel:
    """输入 100+ 样本 → 训练 Isotonic → 保存 .pkl → 更新 cache。"""

def calibrate(raw_confidence: float, timeframe: str) -> float | None:
    """0.0-1.0；若 calibrator 未就绪返 None。"""
```

### 5.3 `app/services/outcome_worker.py`

```python
async def outcome_worker_loop(interval_seconds: int = 300):
    """每 5 分钟：
       1. 查 RecommendationHistory where outcome_label == 'PENDING'
       2. 拉最新 K 线检查 TP/SL
       3. 命中 → 写 pnl/outcome_label/closed_at
       4. 超 max_hold → EXPIRED label
    """

@dataclass
class TraceResult:
    outcome_label: Literal["HIT_TP", "HIT_SL", "EXPIRED", "HUD", "PENDING"]
    pnl_pct: float
    holding_minutes: int

def trace_position(
    record: RecommendationHistory,
    candles_since_open: list[Candle],
    target_pct: float,
    stop_pct: float,
    max_hold_minutes: int,
) -> TraceResult:
```

### 5.4 `app/services/calibration_trainer.py`

```python
async def calibration_trainer_loop(cron_hour: int = 2):
    """每日 02:00：
       1. 查 RecommendationHistory where outcome_label IN ('HIT_TP','HIT_SL','EXPIRED')
       2. 按 timeframe 分组
       3. 喂 train_calibrator(timeframe, samples)
       4. 校验 Brier score < 0.20 → 更新 .pkl；否则报警（用上一版）
    """
```

### 5.5 `backend/scripts/backtest_engine.py`

```python
@dataclass
class BacktestConfig:
    symbol: str
    timeframe: str
    strategies: list[str]
    days: int
    fee_taker_bps: float = 8.0
    slippage_bps: float = 5.0
    min_confidence: float = 0.6
    target_pct: float = 0.005
    stop_pct: float = 0.003
    max_hold_minutes: int = 60

@dataclass
class BacktestResult:
    trades: list[VirtualTrade]
    equity_curve: list[tuple[datetime, float]]
    total_trades: int
    hit_rate: float
    net_pnl_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float

def run_backtest(config: BacktestConfig) -> BacktestResult:
    """walk-forward CV: 70/30 split, 5-day embargo."""
```

### 5.6 `POST /api/backtest`

```http
POST /api/backtest
Content-Type: application/json

{
  "symbol": "BTC-USDT",
  "timeframe": "1h",
  "strategies": ["MomentumStrategy", "BreakoutStrategy", "ConfluenceStrategy"],
  "days": 30,
  "fee_taker_bps": 8.0,
  "slippage_bps": 5.0,
  "min_confidence": 0.6,
  "target_pct": 0.005,
  "stop_pct": 0.003,
  "max_hold_minutes": 60
}

→ 200 OK
{
  "run_id": 42,
  "summary": {
    "total_trades": 28,
    "hit_rate": 0.642,
    "net_pnl_pct": 0.0412,
    "sharpe_ratio": 1.84,
    "max_drawdown_pct": -0.061,
    "started_at": "2026-10-01T00:00:00Z",
    "finished_at": "2026-10-01T00:02:31Z",
    "status": "done"
  },
  "equity_curve": [{"ts": "...", "equity": 1.0023}, ...],
  "trades": [{ "id": 1, "entry_time": "...", "exit_time": "...", "net_pnl_pct": 0.0041, "outcome": "HIT_TP" }, ...]
}
```

---

## 6. 错误处理（Error Handling）

| 错误 | 处理 |
|------|------|
| 校准器未就绪（<100 个样本） | `calibrate()` 返 None；`calibrated_confidence` 字段写 NULL；前端显示「calibrating...」|
| 回测期间 K 线拉取失败 | `BacktestRun.status = 'error'` + `error_message`；前端 toast 报错 |
| OutcomeWorker 找不到 K 线（symbol 已下架）| 跳过该 record + log warning，不抛异常 |
| Isotonic 训练样本 <10 | 用 fallback = raw_confidence（即不校准）+ log warning |
| 回测 running 时同 symbol 并发跑 | 用 `BacktestRun.status` 串行化（同一 symbol 仅一单 running）|
| Calibration 训练失败（Brier > 0.20） | 保留旧 .pkl + 报警 + 不更新 |
| 滑点模型 ATR-adaptive 模式 K 线不足 | 退化为固定 0.05% |

---

## 7. 测试策略（Test Strategy）

每个模块都有 RED → GREEN：

### 7.1 `tests/test_cost_model.py`
- 单边费率（OKX taker 0.08%）= 0.0008
- 往返费率 + 滑点 = 0.08 + 0.08 + 0.05 = 0.0021（21 bps）
- `is_profitable_threshold(target=0.5%, conf=0.5)` = False
- `is_profitable_threshold(target=0.5%, conf=0.7)` = True（0.7 * 0.5 = 0.35% > 0.21%）

### 7.2 `tests/test_calibration.py`
- 喂 1000 个随机 (raw_conf, pnl) 样本 → 训练 → Brier score < 0.15
- 校准后 calibration_curve < 0.05（理想 + 误差斜率）
- per-tf / 6 个 timeframe 都各自有效

### 7.3 `tests/test_outcome_worker.py`
- mock K 线+RecommendationHistory → trace_position 返回正确 outcome_label
- HIT_TP: 价格触达 +0.5% → pnl_pct = +0.0029（扣费后）
- HIT_SL: 价格触达 -0.3% → pnl_pct = -0.0051
- EXPIRED: 超过 max_hold_minutes → pnl_pct = 当前价格位移 - 费率
- HOLD: 24h 后仍未触发 → label 仍然hold

### 7.4 `tests/test_backtest_engine.py`
- 固定 K 线 fixture → 跑 30 天回测 → 验证净 PnL、Sharpe、MaxDD 字段类型正确
- equity_curve 长度 >= 1
- trades 数组每个元素有 entry_time/exit_time/net_pnl_pct
- 无策略 in 推荐盘：返 0 trades + 净 PnL = 0

### 7.5 `tests/test_backtest_api.py`
- FastAPI TestClient → POST /api/backtest → 200 + JSON 结构
- 入参缺 strategies → 422
- 入参 days 不超 365 → 400

### 7.7 端到端
- `curl POST /api/backtest -d '{...}'` → 看 net_pnl
- 浏览器跑 BacktestPage → 截图净值曲线

---

## 8. 验证与上线（Verification & Rollout）

### 8.1 本地验证
- 每个 task 完成后跑对应 test
- 4 task 全完成后跑 `pytest backend/tests/test_calibration.py backend/tests/test_cost_model.py backend/tests/test_outcome_worker.py backend/tests/test_backtest_api.py` 走完
- 起 backend，跑 curl 验证 /api/backtest

### 8.2 部署验证
- 合入 main → 触发自动 deploy (规则 9)
- 部署后浏览器跑 BacktestPage，截图

### 8.3 灰度（calibration 字段）
- Phase 1 部署后 calibration.py 字段先写 NULL
- 收集 7 天 RecommendationHistory
- 7 天后首次 cron 触发 calibration 训练 → calibrator is_ready = true
- 8 天后所有新 recommendation 有 calibrated_confidence

---

## 9. 不在本次范围（Future）

- ML 模型训练（XGBoost / Transformer / LOB 微结构）— Phase 2
- freqtrade 实盘对接 — Phase 3
- 多用户 / 鉴权 — 单独 track
- trailing stop / 自适应 TP/SL — Phase 2
- 真实账户 PnL 对账 — Phase 3
- 移动端 push — 单独 track

---

## 10. 参考资料（References）

- GitHub 调研：`docs/architecture/github-survey-trend-2026-10-02.md`
- 参考 repo：
  - [sfeirc/Short-Horizon-Price-Direction-5-min-from-LOB-Microstructure](https://github.com/sfeirc/Short-Horizon-Price-Direction-5-min-from-LOB-Microstructure) — confidence >= 0.6 过滤范式
  - [mefai-dev/mefai-signal-engine](https://github.com/mefai-dev/mefai-signal-engine) — 5 层信号融合
  - [VersoXBT/latent-regime-discovery-crypto](https://github.com/VersoXBT/latent-regime-discovery-crypto) — regime + walk-forward
  - [jesse-ai/jesse](https://github.com/jesse-ai/jesse) — 回测引擎参考
- 已有 PR：#25 (signals-v2), #26 (UserFollow), #27 (regime engine), #28-#37 (UI/WS/deploy)
- Step 2 spec：`2026-10-02-b-follow-step2-recommendation-history.md`