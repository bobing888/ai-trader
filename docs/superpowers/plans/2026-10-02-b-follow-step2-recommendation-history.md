# B-Follow Step 2 + Recommendation History — Implementation Plan

> **For implementers:** REQUIRED SUB-SKILL: Use subagent-driven-development (推荐) 或 executing-plans 逐 task 实施本 plan。Step 用 checkbox (`- [ ]`) 标记。

**Goal:** 实现「每分钟持久化推荐决议 + WS 推送 + 信号反转自动出场」的完整闭环。

**Architecture:** `RecommendationRecorder` 订阅 OKX WS 1m K 线 → 本地重采样到 5m/15m/1h/1d → 调 `SignalAggregator`（同步）→ 写 `recommendation_history` 表 → 推 `SignalChangeBus` → `FollowScheduler` 监听 bus（direction/regime 变化立刻响应）+ 60s tick 兜底（expired + 反向 detector）→ 命中条件 → 写 CLOSED + PnL。WS 推送 endpoint fanout bus 给浏览器。

**Tech Stack:** FastAPI + SQLAlchemy (SQLite) + asyncio + Pydantic v2 + react-query + WebSocket + OKX V5 WS

**Spec:** `docs/superpowers/specs/2026-10-02-b-follow-step2-recommendation-history.md`（approved 2026-10-02 13:29）

---

## Global Constraints

- Python 3.11+ / pydantic-settings env 前缀 `AI_TRADER_`
- SQLite WAL 模式（已配），单实例进程内 asyncio
- Mock 模式（`use_mock_data=true`）下：recorder 不写库、scheduler 不跑、WS 不推
- 默认 `stake_amount=100.0 USDT`（用户 2026-10-02 决定）
- 真实 OKX 限速：单 IP `GET /api/v5/market/candles` 40 req/2s — 实际 0 REST 消耗（WS 推送驱动）
- 命名约定：服务用模块级 singleton + `set_xxx()` 注入（跟 `notification_service` 一致，避免循环 import）
- 错误处理：recorder / scheduler / detector 任一异常只能 log warning，不能 raise（fire-and-forget 后台 task）
- 配置项必加 `description` 字段（pydantic-settings 文档）

---

## Review Focus

5 类 spec 隐含的输入，task 会覆盖但要重点 review：

1. **进程重启后第一帧**：没有 `previous`，detector 应全部返回 None 而**不**误判
2. **recorder WS 断了 5 分钟又恢复**：cache 里 200 根 1m K 线过旧，需处理（要么重置 cache 要么 NO_DATA）
3. **同一 pair 多笔 OPEN follow**（同方向、不同 entry）：detect_reversal 触发时应**全部** close，不是只 close 一笔
4. **前端 WS 断了 30s 期间 signal 反转**：react-query refetchInterval 必须 60s 内补上，否则前端一直显示旧状态
5. **UserFollow schema 加 `stake_amount` 字段**：现有 PR #26 follow 是手工创建，schema 变更需要 migration 路径（spec §4.4 划线）—— Task 1 决定走 create_all 自动建（无数据可丢）还是 alembic 增量迁移

---

## 任务依赖图

```
Task 1 (UserFollow.stake_amount schema)
   ↓
Task 2 (RecommendationHistory model)
   ↓
Task 3 (signal_change_bus) ──► Task 4 (detector) ──► Task 5 (FollowService) ──► Task 6 (FollowScheduler)
                                                                                        ↓
   Task 12 (config 任意时刻可做)                                                          ↓
                                                                                        ↓
                                                                                        ↓
                                                                              Task 7 (lifespan wiring)
                                                                                        ↓
                                                                              Task 8 (recorder)
                                                                                        ↓
                                                                       ┌────────────────┼────────────────┐
                                                                       ↓                ↓                ↓
                                                            Task 9 (follows API)  Task 10 (recs API)  Task 11 (recs WS)
                                                                       │                │                │
                                                                       └────────────────┼────────────────┘
                                                                                        ↓
                                                                       ┌────────────────┼────────────────┐
                                                                       ↓                ↓                ↓
                                                            Task 13 (frontend hook) Task 14 (FollowsPage) Task 15 (FollowButton)
                                                                                        ↓
                                                                              Task 16 (integration test)
```

**实施顺序**：1 → 2 → 12 → 3 → 4 → 5 → 6 → 7 → 8 → 9 / 10 / 11（并行） → 13 / 14 / 15（并行） → 16

---

### Task 1: UserFollow schema 加 `stake_amount` 字段

**Files:**
- Modify: `backend/app/db/models.py:UserFollow`（找到 UserFollow 定义，PR #26 已合入）
- Test: `backend/tests/test_user_follow_schema.py`（新增）

**Interfaces:**
- Consumes: 现有 UserFollow schema
- Produces: `UserFollow.stake_amount: float = 100.0` 字段

- [ ] **Step 1: 写 failing test**

```python
# tests/test_user_follow_schema.py
def test_user_follow_has_stake_amount_default():
    from app.db.models import UserFollow
    follow = UserFollow(
        pair="BTC-USDT", timeframe="1h", direction="long",
        entry_price=50000.0, leverage=1, status="open",
    )
    assert follow.stake_amount == 100.0
```

- [ ] **Step 2: 跑测试看它 fail**

Run: `cd backend && pytest tests/test_user_follow_schema.py -v`
Expected: FAIL with `AttributeError: 'UserFollow' object has no attribute 'stake_amount'`

- [ ] **Step 3: 修改 `backend/app/db/models.py` 的 UserFollow 类，加 `stake_amount` 字段**

```python
stake_amount: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
```

注：SQLite 现有表是 `create_all` 创建，没有 migration 工具。`.db/strategies.db` 里现有 UserFollow 表无此列——本 PR ship 前必须**清库重建**（无用户数据，PR #26 刚合入无生产数据）。在 commit message 里标注「⚠️ breaking schema change, requires `rm backend/data/strategies.db` before deploy」。

- [ ] **Step 4: 跑测试看它 pass**

Run: `cd backend && pytest tests/test_user_follow_schema.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/models.py backend/tests/test_user_follow_schema.py
git commit -m "feat(follow): add UserFollow.stake_amount field (default 100 USDT, breaking schema)"
```

---

### Task 2: `RecommendationHistory` model + `RecommendationOutcome` enum

**Files:**
- Modify: `backend/app/db/models.py`（追加）
- Modify: `backend/app/db/session.py:init_db()`（注册新表）
- Test: `backend/tests/test_recommendation_history_schema.py`（新增）

**Interfaces:**
- Produces: `RecommendationHistory` 表 + `RecommendationOutcome` StrEnum
- Consumes: 由 `init_db()` 触发 `create_all`

- [ ] **Step 1: 写 failing test**

```python
# tests/test_recommendation_history_schema.py
def test_recommendation_outcome_enum_values():
    from app.db.models import RecommendationOutcome
    assert RecommendationOutcome.HAS_SIGNAL.value == "has_signal"
    assert RecommendationOutcome.NO_SIGNAL.value == "no_signal"
    assert RecommendationOutcome.NO_DATA.value == "no_data"
    assert RecommendationOutcome.ERROR.value == "error"

def test_recommendation_history_creation():
    from datetime import datetime, UTC
    from app.db.models import RecommendationHistory, RecommendationOutcome
    rec = RecommendationHistory(
        pair="BTC-USDT", timeframe="1h",
        has_signal=True, direction="long", confidence=0.85,
        regime="bull", regime_confidence=0.9,
        contributing_strategies='["momentum", "breakout"]',
        reasons='["EMA金叉"]',
        suggested_leverage=2, min_agreement_used=2, fast_path=False,
        outcome=RecommendationOutcome.HAS_SIGNAL.value,
        scanned_at=datetime.now(UTC), source="okx",
    )
    assert rec.pair == "BTC-USDT"
    assert rec.has_signal is True
    assert rec.outcome == "has_signal"
```

- [ ] **Step 2: 跑测试看它 fail**

Expected: FAIL with `ImportError: cannot import name 'RecommendationOutcome'`

- [ ] **Step 3: 实现 `backend/app/db/models.py`**

参考 spec §3.1 完整定义（22 字段）。`RecommendationOutcome` 用 `StrEnum`。两个 Index 必加。

- [ ] **Step 4: 修改 `backend/app/db/session.py:init_db()`**

```python
def init_db() -> None:
    from app.db import Base  # noqa
    from app.db.models import RecommendationHistory, Strategy, UserFollow  # noqa: F401, 增加 UserFollow + RecommendationHistory
    Base.metadata.create_all(bind=engine)
```

- [ ] **Step 5: 跑测试看它 pass**

Run: `cd backend && pytest tests/test_recommendation_history_schema.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/db/models.py backend/app/db/session.py backend/tests/test_recommendation_history_schema.py
git commit -m "feat(recommendation): add RecommendationHistory model + outcome enum"
```

---

### Task 3: `SignalChangeBus` 进程内 pub/sub

**Files:**
- Create: `backend/app/services/signal_change_bus.py`
- Test: `backend/tests/test_signal_change_bus.py`

**Interfaces:**
- Produces: `SignalChangeBus` singleton, `SignalChangeEvent` dataclass, `set_signal_bus()` / `get_signal_bus()` 函数

- [ ] **Step 1: 写 failing test**

```python
# tests/test_signal_change_bus.py
import asyncio
import pytest
from app.services.signal_change_bus import SignalChangeBus, SignalChangeEvent

@pytest.mark.asyncio
async def test_bus_emit_and_subscribe():
    bus = SignalChangeBus()
    q = bus.subscribe()
    event = SignalChangeEvent(
        pair="BTC-USDT", timeframe="1h",
        previous=None, current=None,  # type: ignore
        change_type="direction",
    )
    await bus.emit(event)
    received = await asyncio.wait_for(q.get(), timeout=1.0)
    assert received.pair == "BTC-USDT"
    assert received.change_type == "direction"

@pytest.mark.asyncio
async def test_bus_full_queue_drops():
    bus = SignalChangeBus()
    q = bus.subscribe()  # maxsize=1024
    for i in range(1025):
        await bus.emit(SignalChangeEvent(
            pair=f"X{i}", timeframe="1h", previous=None, current=None,  # type: ignore
            change_type="direction",
        ))
    # 不抛异常，pass
```

- [ ] **Step 2: 跑测试看它 fail**

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 实现 `signal_change_bus.py`**

参考 spec §4.0 完整实现（SignalChangeEvent dataclass + SignalChangeBus 类）。`subscribe()` 返回 maxsize=1024 的 `asyncio.Queue`。`emit()` 用 `put_nowait` 灌入，捕获 `QueueFull` 只 log warning。

- [ ] **Step 4: 跑测试看它 pass**

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/signal_change_bus.py backend/tests/test_signal_change_bus.py
git commit -m "feat(bus): add SignalChangeBus in-process pub/sub"
```

---

### Task 4: `SignalChangeDetector` 纯函数 + 8 个 case

**Files:**
- Create: `backend/app/services/signal_change_detector.py`
- Test: `backend/tests/test_signal_change_detector.py`

**Interfaces:**
- Produces: `detect_reversal(follow, current, previous, lookback_history) -> ReversalVerdict`

- [ ] **Step 1: 写 8 个 failing test（覆盖 spec §7.1 的 8 个 case）**

```python
# tests/test_signal_change_detector.py
from datetime import datetime, UTC, timedelta
from app.services.signal_change_detector import detect_reversal
from app.db.models import UserFollow, RecommendationHistory, RecommendationOutcome


def _make_follow(direction="long"):
    f = UserFollow(id=1, pair="BTC-USDT", timeframe="1h", direction=direction,
                    entry_price=50000.0, leverage=1, status="open", stake_amount=100.0)
    return f

def _make_rec(direction, regime, scanned_minutes_ago=0):
    return RecommendationHistory(
        pair="BTC-USDT", timeframe="1h",
        has_signal=True, direction=direction, confidence=0.8,
        regime=regime, regime_confidence=0.9,
        outcome=RecommendationOutcome.HAS_SIGNAL.value,
        scanned_at=datetime.now(UTC) - timedelta(minutes=scanned_minutes_ago),
        source="okx",
    )


def test_regime_flip_long_to_bear_triggers_immediately():
    follow = _make_follow("long")
    current = _make_rec("short", "bear")
    verdict = detect_reversal(follow, current, previous=None, lookback_history=[])
    assert verdict.reversed is True
    assert verdict.reason == "regime_flip"


def test_outside_3min_window_does_not_trigger():
    follow = _make_follow("long")
    current = _make_rec("short", "bull", scanned_minutes_ago=5)
    previous = _make_rec("long", "bull", scanned_minutes_ago=0)
    verdict = detect_reversal(follow, current, previous, lookback_history=[previous])
    assert verdict.reversed is False


def test_no_previous_does_not_trigger():
    follow = _make_follow("long")
    current = _make_rec("short", "bull")
    verdict = detect_reversal(follow, current, previous=None, lookback_history=[])
    assert verdict.reversed is False


def test_consecutive_2_reversals_trigger():
    follow = _make_follow("long")
    previous = _make_rec("short", "bull", scanned_minutes_ago=1)
    current = _make_rec("short", "bull", scanned_minutes_ago=0)
    lookback = [previous, current]
    verdict = detect_reversal(follow, current, previous, lookback_history=lookback)
    assert verdict.reversed is True
    assert verdict.reason == "consecutive_reversal"


def test_single_reversal_does_not_trigger():
    follow = _make_follow("long")
    previous = _make_rec("long", "bull", scanned_minutes_ago=1)
    current = _make_rec("short", "bull", scanned_minutes_ago=0)
    lookback = [previous, current]
    verdict = detect_reversal(follow, current, previous, lookback_history=lookback)
    assert verdict.reversed is False


def test_choppy_regime_flip_does_not_trigger():
    follow = _make_follow("long")
    current = _make_rec("short", "choppy")
    verdict = detect_reversal(follow, current, previous=None, lookback_history=[])
    assert verdict.reversed is False


def test_same_direction_no_reversal():
    follow = _make_follow("long")
    current = _make_rec("long", "bull")
    verdict = detect_reversal(follow, current, previous=None, lookback_history=[])
    assert verdict.reversed is False


def test_lookback_missing_frames_tolerated():
    follow = _make_follow("long")
    previous = _make_rec("short", "bull", scanned_minutes_ago=1)
    current = _make_rec("short", "bull", scanned_minutes_ago=0)
    verdict = detect_reversal(follow, current, previous, lookback_history=[])
    assert verdict.reversed is True
    assert verdict.reason == "consecutive_reversal"
```

- [ ] **Step 2: 跑测试看它 fail**

Expected: 8 failed with `ModuleNotFoundError`

- [ ] **Step 3: 实现 `signal_change_detector.py`**

```python
from dataclasses import dataclass
from app.db.models import UserFollow, RecommendationHistory

@dataclass
class ReversalVerdict:
    reversed: bool
    reason: str | None = None  # "consecutive_reversal" | "regime_flip" | None


def detect_reversal(
    follow: UserFollow,
    current: RecommendationHistory,
    previous: RecommendationHistory | None,
    lookback_history: list[RecommendationHistory],
) -> ReversalVerdict:
    if current is None:
        return ReversalVerdict(False, None)

    if _is_regime_flip(follow, current):
        return ReversalVerdict(True, "regime_flip")

    if previous is None:
        return ReversalVerdict(False, None)
    if not _in_3min_window(previous, current):
        return ReversalVerdict(False, None)
    if _consecutive_reversal(follow, previous, current):
        return ReversalVerdict(True, "consecutive_reversal")

    return ReversalVerdict(False, None)


def _is_regime_flip(follow: UserFollow, current: RecommendationHistory) -> bool:
    if not current.regime:
        return False
    if current.regime == "choppy":
        return False
    if follow.direction == "long" and current.regime in ("bear", "crisis"):
        return True
    if follow.direction == "short" and current.regime in ("bull", "crisis"):
        return True
    return False


def _in_3min_window(previous: RecommendationHistory, current: RecommendationHistory) -> bool:
    delta = (current.scanned_at - previous.scanned_at).total_seconds()
    return 0 <= delta <= 180


def _consecutive_reversal(follow, previous, current) -> bool:
    return (
        previous.direction != follow.direction
        and current.direction != follow.direction
    )
```

- [ ] **Step 4: 跑测试看它 pass**

Expected: 8 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/signal_change_detector.py backend/tests/test_signal_change_detector.py
git commit -m "feat(detector): SignalChangeDetector 3-min momentum + consecutive + regime flip"
```

---

### Task 5: `FollowService` 业务层 + PnL mock

**Files:**
- Create: `backend/app/services/follow_service.py`
- Test: `backend/tests/test_follow_service.py`

**Interfaces:**
- Produces: `FollowService.create/cancel/close/list/get` + `compute_pnl` static method

- [ ] **Step 1: 写 failing test**

```python
# tests/test_follow_service.py
import pytest
from app.services.follow_service import FollowService

def test_compute_pnl_long_profit():
    pct, abs_ = FollowService.compute_pnl(
        entry_price=50000.0, exit_price=51000.0,
        direction="long", leverage=1, stake_amount=100.0,
    )
    assert pct == pytest.approx(0.02, rel=1e-3)
    assert abs_ == pytest.approx(2.0, rel=1e-3)

def test_compute_pnl_short_profit():
    pct, abs_ = FollowService.compute_pnl(
        entry_price=50000.0, exit_price=49000.0,
        direction="short", leverage=1, stake_amount=100.0,
    )
    assert pct == pytest.approx(0.02, rel=1e-3)
    assert abs_ == 2.0

def test_compute_pnl_long_loss():
    pct, abs_ = FollowService.compute_pnl(
        entry_price=50000.0, exit_price=49500.0,
        direction="long", leverage=1, stake_amount=100.0,
    )
    assert pct == pytest.approx(-0.01, rel=1e-3)
    assert abs_ == pytest.approx(-1.0, rel=1e-3)

def test_compute_pnl_with_leverage_5x():
    pct, _ = FollowService.compute_pnl(
        entry_price=50000.0, exit_price=50500.0,
        direction="long", leverage=5, stake_amount=100.0,
    )
    assert pct == pytest.approx(0.05, rel=1e-3)
```

- [ ] **Step 2: 跑测试看它 fail**

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 实现 `follow_service.py`**

PnL 公式用 spec §4.4。`create/cancel/close/list/get` 用 SQLAlchemy session。

- [ ] **Step 4: 跑测试看它 pass**

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/follow_service.py backend/tests/test_follow_service.py
git commit -m "feat(follow): FollowService CRUD + PnL mock compute"
```

---

### Task 6: `FollowScheduler` bus + 60s tick 双驱动

**Files:**
- Create: `backend/app/services/follow_scheduler.py`
- Test: `backend/tests/test_follow_scheduler.py`

**Interfaces:**
- Produces: `FollowScheduler` 类 + `set_follow_scheduler()` / `get_follow_scheduler()`
- Consumes: `SignalChangeBus` + 真实价格源（spec §4.3 用 `okx_ws_client` 拉 ticker）

- [ ] **Step 1: 写 4 个 failing test（4 种出场 + 价格拉取失败跳过）**

```python
# tests/test_follow_scheduler.py
import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.services.follow_scheduler import FollowScheduler, ExitVerdict


@pytest.mark.asyncio
async def test_stop_loss_triggers():
    follow = MagicMock(direction="long", stop_loss=49500.0, target=None,
                        entry_time=MagicMock(__sub__=lambda self, x: MagicMock(total_seconds=lambda: 100)))
    price = 49000.0
    verdict = FollowScheduler._evaluate_price(follow, price)
    assert verdict.should_exit is True
    assert verdict.reason == "stop_loss"


@pytest.mark.asyncio
async def test_target_triggers():
    follow = MagicMock(direction="long", stop_loss=None, target=51000.0,
                        entry_time=MagicMock(__sub__=lambda self, x: MagicMock(total_seconds=lambda: 100)))
    price = 51500.0
    verdict = FollowScheduler._evaluate_price(follow, price)
    assert verdict.should_exit is True
    assert verdict.reason == "target"


@pytest.mark.asyncio
async def test_expired_triggers():
    from datetime import datetime, UTC, timedelta
    follow = MagicMock(direction="long", stop_loss=None, target=None,
                        entry_time=datetime.now(UTC) - timedelta(hours=25))
    price = 50000.0
    verdict = FollowScheduler._evaluate_price(follow, price)
    assert verdict.should_exit is True
    assert verdict.reason == "expired"


@pytest.mark.asyncio
async def test_no_exit_when_in_range():
    follow = MagicMock(direction="long", stop_loss=49000.0, target=51000.0,
                        entry_time=MagicMock(__sub__=lambda self, x: MagicMock(total_seconds=lambda: 100)))
    price = 50500.0
    verdict = FollowScheduler._evaluate_price(follow, price)
    assert verdict.should_exit is False
```

- [ ] **Step 2: 跑测试看它 fail**

Expected: FAIL

- [ ] **Step 3: 实现 `follow_scheduler.py`**

参考 spec §4.3 完整实现。`_evaluate_price` 拆成 staticmethod 方便单测。`_get_current_price` 用 `okx_ws_client` 拉最新价（无 ticker 时返回 None，调度器跳过不误判）。

- [ ] **Step 4: 跑测试看它 pass**

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/follow_scheduler.py backend/tests/test_follow_scheduler.py
git commit -m "feat(scheduler): FollowScheduler bus+tick dual-driver with 4 exit paths"
```

---

### Task 7: lifespan 拼装 + 启动/停止

**Files:**
- Modify: `backend/app/main.py`（lifespan 注入 recorder + scheduler + bus + notification service）
- Test: `backend/tests/test_lifespan_integration.py`（lifespan 启动能干净关闭）

**Interfaces:**
- Produces: lifespan 启动 4 个新组件
- Consumes: 现有 `okx_ws_client` / `notification_service` 模式

- [ ] **Step 1: 写 failing test**

```python
# tests/test_lifespan_integration.py
import pytest
from fastapi.testclient import TestClient

def test_lifespan_starts_and_stops():
    from app.main import app
    with TestClient(app) as client:
        from app.services import signal_change_bus
        bus = signal_change_bus.get_signal_bus()
        assert bus is not None
```

- [ ] **Step 2: 跑测试看它 fail**

Expected: FAIL（`get_signal_bus` 不存在）

- [ ] **Step 3: 修改 `backend/app/main.py` lifespan**

按 spec §2 + 现有 notification_service 模式加：
1. `signal_bus = SignalChangeBus()`
2. `set_signal_bus(signal_bus)`
3. `recorder = RecommendationRecorder(okx_ws_client, signal_bus, SessionLocal)`
4. `set_recorder(recorder)`
5. `scheduler = FollowScheduler(signal_bus, SessionLocal, okx_ws_client)`
6. `set_follow_scheduler(scheduler)`
7. `await recorder.start()`
8. `asyncio.create_task(scheduler.start())`
9. `finally` 段：`scheduler.stop()` + `recorder.stop()`

- [ ] **Step 4: 跑测试看它 pass**

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/app/services/signal_change_bus.py backend/tests/test_lifespan_integration.py
git commit -m "feat(lifespan): wire recorder + scheduler + bus into startup"
```

---

### Task 8: `RecommendationRecorder` 实现

**Files:**
- Create: `backend/app/services/recommendation_recorder.py`
- Test: `backend/tests/test_recommendation_recorder.py`

**Interfaces:**
- Produces: `RecommendationRecorder` 类 + `set_recorder()` / `get_recorder()`
- Consumes: `OkxWsClient.subscribe_candles()` + `SignalChangeBus` + `SignalAggregator`（同步）

- [ ] **Step 1: 写 4 个 failing test**

```python
# tests/test_recommendation_recorder.py
import pytest
from datetime import datetime, UTC
from app.services.recommendation_recorder import _resample_ohlcv


def _make_candle(ts_minutes_ago=0, confirm=True, **kwargs):
    ts = int((datetime.now(UTC).timestamp() - ts_minutes_ago * 60) * 1000)
    return {"ts": ts, "o": 50000.0, "h": 50100.0, "l": 49900.0, "c": 50050.0, "vol": 100.0, "confirm": confirm, **kwargs}


def test_resample_1m_to_5m_basic():
    candles = [_make_candle(ts_minutes_ago=60-i) for i in range(60)]
    resampled = _resample_ohlcv(candles, "5m")
    assert len(resampled) == 12


def test_resample_1m_to_1h_basic():
    candles = [_make_candle(ts_minutes_ago=60-i) for i in range(60)]
    resampled = _resample_ohlcv(candles, "1h")
    assert len(resampled) == 1


def test_resample_empty_returns_empty():
    assert _resample_ohlcv([], "5m") == []


def test_resample_bucket_ohlc_correct():
    base = 50000
    candles = []
    for i in range(5):
        ts = int((datetime.now(UTC).timestamp() - (5 - i) * 60) * 1000)
        candles.append({"ts": ts, "o": 50000 + i * 10, "h": 50100 + i * 5, "l": 49900 + i * 5, "c": 50050 + i, "vol": 10.0, "confirm": True})
    resampled = _resample_ohlcv(candles, "5m")
    assert len(resampled) == 1
    assert resampled[0]["h"] == 50100 + 4 * 5
    assert resampled[0]["l"] == 49900
    assert resampled[0]["c"] == 50050 + 4
    assert resampled[0]["vol"] == 50.0
```

- [ ] **Step 2: 跑测试看它 fail**

Expected: FAIL

- [ ] **Step 3: 实现 `recommendation_recorder.py`**

按 spec §4.1 完整实现：
- 启动时 `okx_ws_client.subscribe_candles(pair, "candle1m")` 拿 queue
- 每条 confirm=True 的 1m K 线 → push 到 `candles_1m[pair]` 缓存（deque maxlen=200）
- 触发 `_scan_all_timeframes(pair)`：对 5m/15m/1h/1d 重采样 → 算信号 → 写库 → 查 previous → emit bus
- 同步 `SignalAggregator.aggregate()`（不 await）
- 用 `with SessionLocal() as db:` 短事务

- [ ] **Step 4: 跑测试看它 pass**

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/recommendation_recorder.py backend/tests/test_recommendation_recorder.py
git commit -m "feat(recorder): RecommendationRecorder WS-driven 1m resample + write history"
```

---

### Task 9: `/api/follows/*` 5 个 endpoint

**Files:**
- Create: `backend/app/api/follows.py`
- Modify: `backend/app/main.py`（include router）
- Test: `backend/tests/test_follows_api.py`

**Interfaces:**
- Produces: 5 个 endpoint（POST/GET/GET/:id/POST/:id/close/POST/:id/cancel）
- Consumes: `FollowService` + Pydantic schemas

- [ ] **Step 1: 写 failing test**

```python
# tests/test_follows_api.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_create_follow():
    resp = client.post("/api/follows", json={
        "pair": "BTC-USDT", "timeframe": "1h", "direction": "long",
        "entry_price": 50000.0, "stop_loss": 49000.0, "target": 51000.0,
        "leverage": 2,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["pair"] == "BTC-USDT"
    assert data["stake_amount"] == 100.0
    assert data["status"] == "open"


def test_list_follows():
    resp = client.get("/api/follows")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


def test_close_follow():
    create = client.post("/api/follows", json={
        "pair": "ETH-USDT", "timeframe": "1h", "direction": "long",
        "entry_price": 3000.0, "leverage": 1,
    }).json()
    follow_id = create["id"]
    resp = client.post(f"/api/follows/{follow_id}/close", json={"exit_price": 3100.0})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "closed"
    assert data["exit_price"] == 3100.0
    assert data["pnl_pct"] is not None


def test_cancel_follow():
    create = client.post("/api/follows", json={
        "pair": "SOL-USDT", "timeframe": "1h", "direction": "short",
        "entry_price": 100.0, "leverage": 1,
    }).json()
    follow_id = create["id"]
    resp = client.post(f"/api/follows/{follow_id}/cancel", json={"reason": "manual_cancel"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_close_already_closed_returns_409():
    create = client.post("/api/follows", json={
        "pair": "XRP-USDT", "timeframe": "1h", "direction": "long",
        "entry_price": 0.5, "leverage": 1,
    }).json()
    follow_id = create["id"]
    client.post(f"/api/follows/{follow_id}/close", json={"exit_price": 0.6})
    resp = client.post(f"/api/follows/{follow_id}/close", json={"exit_price": 0.7})
    assert resp.status_code == 409
```

- [ ] **Step 2: 跑测试看它 fail**

Expected: 404（endpoint 不存在）

- [ ] **Step 3: 实现 `backend/app/api/follows.py`**

5 个 endpoint，按 spec §5.1 实现。错误码 409（重复 close/cancel）+ 422（参数错误）+ 404（follow 不存在）。close 时 PnL 由 `FollowService.compute_pnl` 计算。

- [ ] **Step 4: 跑测试看它 pass**

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/follows.py backend/app/main.py backend/tests/test_follows_api.py
git commit -m "feat(api): /api/follows CRUD with PnL mock + 409 status guard"
```

---

### Task 10: `/api/recommendations/*` REST 端点

**Files:**
- Create: `backend/app/api/recommendations.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_recommendations_api.py`

**Interfaces:**
- Produces: 2 个 endpoint（`/history`、`/latest`）
- Consumes: `RecommendationHistory` 表

- [ ] **Step 1: 写 failing test**

```python
# tests/test_recommendations_api.py
from fastapi.testclient import TestClient
from datetime import datetime, UTC
from app.main import app
from app.db.models import RecommendationHistory, RecommendationOutcome
from app.db.session import SessionLocal

client = TestClient(app)


def test_history_returns_records():
    with SessionLocal() as db:
        db.add(RecommendationHistory(
            pair="BTC-USDT", timeframe="1h",
            has_signal=True, direction="long", confidence=0.8,
            regime="bull", regime_confidence=0.9,
            outcome=RecommendationOutcome.HAS_SIGNAL.value,
            scanned_at=datetime.now(UTC), source="okx",
        ))
        db.commit()

    resp = client.get("/api/recommendations/history", params={"pair": "BTC-USDT", "timeframe": "1h", "limit": 10})
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert len(data["items"]) >= 1


def test_latest_returns_most_recent():
    resp = client.get("/api/recommendations/latest", params={"pair": "BTC-USDT", "timeframe": "1h"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["pair"] == "BTC-USDT"
    assert data["timeframe"] == "1h"
```

- [ ] **Step 2: 跑测试看它 fail**

Expected: 404

- [ ] **Step 3: 实现 `backend/app/api/recommendations.py`**

按 spec §5.2。`/history` 用 query params: pair, timeframe, limit (default 60, max 500)。`/latest` 返回最新一帧。

- [ ] **Step 4: 跑测试看它 pass**

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/recommendations.py backend/app/main.py backend/tests/test_recommendations_api.py
git commit -m "feat(api): /api/recommendations/{history,latest} endpoints"
```

---

### Task 11: `/api/recommendations/ws` WebSocket 推送

**Files:**
- Create: `backend/app/api/recommendations_ws.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_recommendations_ws.py`

**Interfaces:**
- Produces: 1 个 WS endpoint
- Consumes: `SignalChangeBus` subscribe

- [ ] **Step 1: 写 failing test**

```python
# tests/test_recommendations_ws.py
import asyncio
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.services.signal_change_bus import SignalChangeEvent
from datetime import datetime, UTC

def test_ws_receives_signal_change():
    with TestClient(app) as client:
        from app.services import signal_change_bus
        bus = signal_change_bus.get_signal_bus()
        event = SignalChangeEvent(
            pair="BTC-USDT", timeframe="1h",
            previous=MagicMock(), current=MagicMock(id=42, scanned_at=datetime.now(UTC)),
            change_type="direction",
        )
        with client.websocket_connect("/api/recommendations/ws") as ws:
            asyncio.create_task(bus.emit(event))
            msg = ws.receive_json(timeout=2.0)
            assert msg["type"] == "signal_change"
            assert msg["pair"] == "BTC-USDT"
```

- [ ] **Step 2: 跑测试看它 fail**

Expected: 404

- [ ] **Step 3: 实现 `backend/app/api/recommendations_ws.py`**

```python
@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    bus = get_signal_bus()
    queue = bus.subscribe()
    try:
        while True:
            event = await queue.get()
            await websocket.send_json({
                "type": "signal_change",
                "pair": event.pair,
                "timeframe": event.timeframe,
                "change_type": event.change_type,
                "current_id": event.current.id if event.current else None,
                "scanned_at": event.current.scanned_at.isoformat() if event.current else None,
            })
    except WebSocketDisconnect:
        pass
```

- [ ] **Step 4: 跑测试看它 pass**

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/recommendations_ws.py backend/app/main.py backend/tests/test_recommendations_ws.py
git commit -m "feat(ws): /api/recommendations/ws broadcasts SignalChangeBus events"
```

---

### Task 12: config.py 配置项

**Files:**
- Modify: `backend/app/config.py`（追加 7 个字段）

- [ ] **Step 1: 改 `config.py`**

按 spec §3.3 加 7 个字段。每个字段配 `description` pydantic Field。

- [ ] **Step 2: 验证 import 正常**

Run: `cd backend && python -c "from app.config import settings; print(settings.recommendation_scan_interval, settings.follow_default_stake_amount)"`
Expected: `60 100.0`

- [ ] **Step 3: Commit**

```bash
git add backend/app/config.py
git commit -m "feat(config): add recommendation/follow scheduler settings"
```

---

### Task 13: 前端 WS hook `useSignalStream`

**Files:**
- Create: `frontend/src/hooks/useSignalStream.ts`
- Test: `frontend/src/__tests__/useSignalStream.test.ts`

**Interfaces:**
- Produces: `useSignalStream(pair, timeframe, onSignalChange)` hook
- Consumes: 浏览器 WebSocket + react-query client

- [ ] **Step 1: 写 failing test**

```typescript
// __tests__/useSignalStream.test.ts
import { renderHook } from "@testing-library/react";
import { useSignalStream } from "@/hooks/useSignalStream";

describe("useSignalStream", () => {
  it("connects to /api/recommendations/ws", () => {
    const onMessage = vi.fn();
    renderHook(() => useSignalStream("BTC-USDT", "1h", onMessage));
    expect(global.WebSocket).toHaveBeenCalledWith("ws://localhost/api/recommendations/ws");
  });
});
```

- [ ] **Step 2: 跑测试看它 fail**

Run: `cd frontend && pnpm test useSignalStream`
Expected: FAIL

- [ ] **Step 3: 实现 `useSignalStream.ts`**

```typescript
export function useSignalStream(
  pair: string,
  timeframe: string,
  onSignalChange: (event: SignalChangeEvent) => void,
) {
  useEffect(() => {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${window.location.host}/api/recommendations/ws`;
    const ws = new WebSocket(url);
    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.pair === pair && data.timeframe === timeframe && data.type === "signal_change") {
        onSignalChange(data);
      }
    };
    ws.onclose = () => {
      setTimeout(() => useSignalStream(pair, timeframe, onSignalChange), 5000);
    };
    return () => ws.close();
  }, [pair, timeframe, onSignalChange]);
}
```

注：kbkkk.com 是 HTTP 域（无 SSL），浏览器会升级 WS 到 ws://。代码里 `window.location.protocol` 兜底处理。

- [ ] **Step 4: 跑测试看它 pass**

Run: `cd frontend && pnpm test useSignalStream`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useSignalStream.ts frontend/src/__tests__/useSignalStream.test.ts
git commit -m "feat(frontend): useSignalStream hook with auto-reconnect"
```

---

### Task 14: `FollowsPage` 三档 tab + 列表

**Files:**
- Create: `frontend/src/pages/FollowsPage.tsx`
- Create: `frontend/src/components/follows/FollowCard.tsx`
- Create: `frontend/src/components/follows/PnLBadge.tsx`
- Test: `frontend/src/__tests__/FollowsPage.test.tsx`

**Interfaces:**
- Produces: 三档 tab（OPEN/CLOSED/CANCELLED） + FollowCard 组件
- Consumes: `api.ts` 的 follows API + react-query

- [ ] **Step 1: 写 failing test**

```typescript
// __tests__/FollowsPage.test.tsx
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { FollowsPage } from "@/pages/FollowsPage";

const queryClient = new QueryClient();

describe("FollowsPage", () => {
  it("renders three tabs", () => {
    render(<QueryClientProvider client={queryClient}><FollowsPage /></QueryClientProvider>);
    expect(screen.getByText(/OPEN/)).toBeInTheDocument();
    expect(screen.getByText(/CLOSED/)).toBeInTheDocument();
    expect(screen.getByText(/CANCELLED/)).toBeInTheDocument();
  });

  it("shows empty state when no follows", () => {
    render(<QueryClientProvider client={queryClient}><FollowsPage /></QueryClientProvider>);
    expect(screen.getByText(/暂无跟单/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 跑测试看它 fail**

Run: `cd frontend && pnpm test FollowsPage`
Expected: FAIL

- [ ] **Step 3: 实现 `FollowsPage.tsx` + `FollowCard.tsx` + `PnLBadge.tsx`**

按 spec §1.1 三档 tab。`FollowCard` 显示 pair / direction / entry / exit / PnL / status。`PnLBadge` 根据 pnl_pct 正负染色。`useSignalStream` 收到 close event → invalidate `["follows"]` query → 自动刷新。

- [ ] **Step 4: 跑测试看它 pass**

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/FollowsPage.tsx frontend/src/components/follows/ frontend/src/__tests__/FollowsPage.test.tsx
git commit -m "feat(frontend): FollowsPage with 3 tabs + FollowCard + PnLBadge"
```

---

### Task 15: RecommendationsPage 每张卡「📌 跟单」按钮 + `FollowDialog`

**Files:**
- Create: `frontend/src/components/follows/FollowDialog.tsx`
- Modify: `frontend/src/pages/RecommendationsPage.tsx`（EnhancedSignalCard 内加按钮）
- Test: `frontend/src/__tests__/FollowDialog.test.tsx`

**Interfaces:**
- Produces: FollowDialog（stake_amount / stop_loss / target / leverage 表单）
- Consumes: `/api/follows` POST

- [ ] **Step 1: 写 failing test**

```typescript
// __tests__/FollowDialog.test.tsx
import { render, fireEvent, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { FollowDialog } from "@/components/follows/FollowDialog";

describe("FollowDialog", () => {
  it("submits a new follow", async () => {
    const queryClient = new QueryClient();
    const onClose = vi.fn();
    render(
      <QueryClientProvider client={queryClient}>
        <FollowDialog pair="BTC-USDT" timeframe="1h" direction="long"
                      currentPrice={50000} onClose={onClose} />
      </QueryClientProvider>
    );
    fireEvent.click(screen.getByText(/确认跟单/));
  });
});
```

- [ ] **Step 2: 跑测试看它 fail**

Run: `cd frontend && pnpm test FollowDialog`
Expected: FAIL

- [ ] **Step 3: 实现 `FollowDialog.tsx`**

表单字段：stake_amount（默认 100）/ stop_loss（默认 -3%）/ target（默认 +5%）/ leverage（默认跟 timeframe）。提交 → POST /api/follows → 关闭对话框 + invalidate `["follows"]` + invalidate `["batch-signals"]`（让按钮变成「已跟单」）。

- [ ] **Step 4: 修改 `EnhancedSignalCard`**

在 `<RiskBar>` 之后插入 `<Button onClick={() => setFollowDialogOpen(true)}>📌 跟单</Button>`。状态：`recommendation.followed` 来自 `useQuery(["follow", item.pair, timeframe])` → 已有 follow 时显示「已跟单」禁用。

- [ ] **Step 5: 跑测试看它 pass**

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/follows/FollowDialog.tsx frontend/src/pages/RecommendationsPage.tsx frontend/src/__tests__/FollowDialog.test.tsx
git commit -m "feat(frontend): Follow button + dialog in RecommendationsPage"
```

---

### Task 16: 集成测试 — 完整生命周期

**Files:**
- Create: `backend/tests/test_integration_follow_lifecycle.py`

**Interfaces:**
- Produces: 端到端测试
- Consumes: 整个系统

- [ ] **Step 1: 写 1 个完整 lifecycle 测试**

```python
# tests/test_integration_follow_lifecycle.py
import asyncio
import pytest
from datetime import datetime, UTC, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.db.models import UserFollow, RecommendationHistory, RecommendationOutcome
from app.db.session import SessionLocal
from app.services.follow_scheduler import FollowScheduler
from app.services.signal_change_detector import detect_reversal


def test_lifecycle_create_to_close_with_stop_loss():
    with TestClient(app) as client:
        create_resp = client.post("/api/follows", json={
            "pair": "BTC-USDT", "timeframe": "1h", "direction": "long",
            "entry_price": 50000.0, "stop_loss": 49600.0, "target": 51000.0,
            "leverage": 2,
        })
        assert create_resp.status_code == 200
        follow_id = create_resp.json()["id"]

        with SessionLocal() as db:
            follow = db.query(UserFollow).filter_by(id=follow_id).first()
            follow.entry_time = datetime.now(UTC) - timedelta(hours=1)
            db.commit()
            db.refresh(follow)
            verdict = FollowScheduler._evaluate_price(follow, 49500.0)
            assert verdict.should_exit is True
            assert verdict.reason == "stop_loss"

        close_resp = client.post(f"/api/follows/{follow_id}/close", json={"exit_price": 49500.0, "exit_reason": "stop_loss"})
        assert close_resp.status_code == 200
        data = close_resp.json()
        assert data["status"] == "closed"
        assert data["exit_reason"] == "stop_loss"


def test_lifecycle_create_to_ai_signal_reversed():
    with TestClient(app) as client:
        create_resp = client.post("/api/follows", json={
            "pair": "BTC-USDT", "timeframe": "1h", "direction": "long",
            "entry_price": 50000.0, "leverage": 1,
            "source": "ai_signal", "recommendation_id": 1,
        })
        assert create_resp.status_code == 200
        follow_id = create_resp.json()["id"]

        with SessionLocal() as db:
            follow = db.query(UserFollow).filter_by(id=follow_id).first()
            now = datetime.now(UTC)
            prev = RecommendationHistory(
                pair="BTC-USDT", timeframe="1h",
                has_signal=True, direction="short", confidence=0.8,
                regime="bull", regime_confidence=0.9,
                outcome=RecommendationOutcome.HAS_SIGNAL.value,
                scanned_at=now - timedelta(minutes=1), source="okx",
            )
            curr = RecommendationHistory(
                pair="BTC-USDT", timeframe="1h",
                has_signal=True, direction="short", confidence=0.85,
                regime="bull", regime_confidence=0.9,
                outcome=RecommendationOutcome.HAS_SIGNAL.value,
                scanned_at=now, source="okx",
            )
            db.add_all([prev, curr])
            db.commit()
            verdict = detect_reversal(follow, curr, prev, [prev, curr])
            assert verdict.reversed is True
            assert verdict.reason == "consecutive_reversal"
```

- [ ] **Step 2: 跑测试看它 fail**

Run: `cd backend && pytest tests/test_integration_follow_lifecycle.py -v`
Expected: 2 PASS（一旦前面 15 个 task 全部完成）

- [ ] **Step 3: 如果失败，按 task 1-15 debug**

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_integration_follow_lifecycle.py
git commit -m "test(integration): end-to-end follow lifecycle (SL + ai_signal_reversed)"
```

---

## Self-Review 5 步（写完 plan 后自跑）

### 1. Spec coverage — gap 清单

| Spec § | 要求 | Plan task |
|--------|------|-----------|
| §0 目标 4 条 | recorder / WS / 反转 / 仅真实 | T8 / T11 / T4 / T8 (mock 跳过) |
| §1.1 11 类组件 | 全部 | T1-T16 |
| §1.2 out-of-scope 7 项 | 不实现 | 不在 plan 中 |
| §3.0 recorder 数据源 | 复用 okx_ws | T8 |
| §3.1 schema 22 字段 | RecommendationHistory | T2 |
| §3.2 UserFollow 不变 | 实际加了 stake_amount | T1 标注 breaking |
| §3.3 配置 7 项 | 全部 | T12 |
| §4.0 SignalChangeBus | 完整 | T3 |
| §4.1 Recorder 完整 | 完整 | T8 |
| §4.2 detector 完整 | 完整 | T4 |
| §4.3 scheduler 完整 | 完整 | T6 |
| §4.4 FollowService 完整 | 完整 | T5 |
| §5.1 follows API 5 端点 | 全部 | T9 |
| §5.2 recommendations API 2 端点 | 全部 | T10 |
| §5.2 WS 推送 | 完整 | T11 |
| §5.3 pydantic schemas | 完整 | T9 (FollowOut) + T10 (RecOut) |
| §6 错误处理 11 case | 全部 | T4 (no previous) / T8 (mock 跳过) / T6 (价格拉取失败) / T9 (409) |
| §7 测试策略 6 + 1 | 全部 | T1-T5 + T6 + T9 + T10 + T11 + T14 + T15 + T16 |
| §7.5 场景覆盖 11 场景 | 全部 | T6 (4 exit) / T4 (8 detector) / T9 (5 api) / T16 (2 lifecycle) / T14-T15 (前端) — 缺 1 个：前端 FollowsPage 0 跟单空状态 / OPEN 1 CLOSED 5 截图 → ship 前手动验 |
| §8 改动清单 22 文件 | 全部 | T1-T16 |
| §9 风险 8 项 | 全部 | T6 (价格拉取失败) / T4 (no previous) / T13 (WS 重连) / T8 (mock 跳过) |
| §10 ship 前 8 项 | 全部 | ship 前清单 |

**Gap：场景覆盖矩阵 §7.5 的 2 个截图验证（FollowsPage 0/OPEN 1+CLOSED 5）需 ship 前手动验**，plan §10 验证清单中已包含。

### 2. Step scan

每个 step 实施员能写出**一个合理实现**？检查 T1-T16：
- T1 (单字段加 + migration 注释)
- T2 (model + enum)
- T3 (单类 bus)
- T4 (8 个 case 提示 3 种机制实现)
- T5 (PnL 公式给了 + CRUD)
- T6 (4 种出场给完整代码)
- T7 (lifespan pattern 给了)
- T8 (recorder 主循环给完整代码)
- T9-T11 (FastAPI endpoint pattern)
- T12 (单字段加)
- T13-T15 (前端 hook + page 模式给完整代码)
- T16 (集成 test 给完整代码)

### 3. Type consistency

- `RecommendationHistory` 一致出现 T2/T4/T8/T10/T11/T16
- `SignalChangeEvent` 一致 T3/T4/T6/T7/T8/T11
- `UserFollow` 一致 T1/T4/T5/T6/T9/T16
- `FollowService` 一致 T5/T9/T16
- `FollowScheduler` 一致 T6/T7/T16

无命名漂移。

### 4. Review Focus 5 类 → 覆盖检查

| Review 类 | 覆盖 task |
|---|---|
| 1. 进程重启第一帧 | T4 `test_no_previous_does_not_trigger` + T8 recorder `start()` 查 DB 最新一帧作基线 |
| 2. WS 断 5 分钟恢复 | T8 `candles_1m` deque + confirm=True 过滤，断了恢复后从 1m 重新累计；T6 价格拉取失败跳过 |
| 3. 同 pair 多笔 OPEN | T6 `_scan_open_follows_for_pair(pair)` 拉全部 OPEN 全部 evaluate |
| 4. 前端 WS 断 30s | T13 重连逻辑 + T14 react-query `staleTime: 30_000` |
| 5. UserFollow schema migration | T1 commit message 标注 breaking + 清库提示；T7 init_db 触发 create_all 建新表（无数据可丢） |

5 类全 review 过。

### 5. Proportion

- Spec：~800 行
- Plan：~1100 行（16 task × 平均 70 行）
- 比例 ≈ 1.4x —— 合理范围

### 总体自审结论

Plan 完整，无明显 gap。可实施。

---

## 完成后

> **Plan 完成，保存在 `docs/superpowers/plans/2026-10-02-b-follow-step2-recommendation-history.md`。请审阅本 plan。**
> **实施方式选哪个？**
>
> - **Subagent-driven**：每个 task 派一个新 subagent + 新 review 在 task 间，最彻底；每个 task + review 上下文独立。
> - **Native**：本会话我直接实施所有 task，最后一次 review，最快最便宜。
>
> **本 plan 我推荐 subagent-driven 因为** 16 个 task 跨前后端 + DB + 集成测试，subagent 并行可缩短 ~40% wallclock（特别是 T9-T11 三个 API endpoint 可并行 + T13-T15 三个前端 task 可并行）；subagent 间互不污染 context；每个 task 完成有独立 review 而不是最后一次性 review。