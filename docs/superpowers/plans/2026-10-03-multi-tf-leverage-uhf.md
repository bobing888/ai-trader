# Multi-TF + Multi-Leverage + UHF Paper-Trading Implementation Plan

> **For implementers:** REQUIRED SUB-SKILL: Use subagent-driven-development (推荐)
> 或 executing-plans 来逐 task 实施本 plan。Step 用 checkbox (`- [ ]`) 标记。

**Goal:** 把 ai-trader 从单 timeframe + 现货 升级到 6 个 horizon tier (P0 长期/跨月 / P1 中期/短期 / P2 超短期 / P3 UHF paper) + 杠杆档位 (1x-5x 现货 + 100x delta-neutral paper) + 4 周 paper 验证后开实盘。

**Architecture:** 借鉴 freqtrade `informative_decorator` 多 TF merge 模式 + jesse `Strategy.py` 基类 + godzilla delta-neutral funding rate arbitrage 模式。新增 `horizon.py` / `informative.py` / `leverage.py` / `paper_trading.py` 4 个核心模块，按 P0→P1→P2→P3 串行实施。

**Tech Stack:** Python 3.12 (backend) / TypeScript + React 18 (frontend) / SQLite (recorder) / OKX v5 API (data + futures) / freqtrade-inspired TLRUCache (多 TF merge).

**Spec:** [../specs/2026-10-03-multi-tf-leverage-uhf-design.md](../specs/2026-10-03-multi-tf-leverage-uhf-design.md)

---

## Global Constraints

- OKX v5 API 限速 20 req/2s (req rate limit), sub-account rate 更严
- 杠杆 ≤ 5x 给现货 + 1m-4h 短期 (用户已确认)
- 100x UHF 必须 delta-neutral (不能裸多/裸空)
- UHF 实盘门槛: 4 周 paper 胜率 > 55% + 最大回撤 < 10%
- 容器内 commit 历史: 4 子系统改动禁止互相污染, 走 multi-task-dispatch
- License 借鉴: freqtrade GPL-3.0 只借鉴模式不拷代码; jesse MIT / godzilla Apache-2.0 可抄

---

## Review Focus (5 类易漏输入)

1. **regime 跨 TF 矛盾**: P0 1d 说 bull, P1 1h 说 bear → aggregator 应该输出 "mixed" 而不是任选一个
2. **杠杆档位边界**: volatility 突然飙升 (BTC 1h ±5%) → leverage.py 必须返回 1x 而非默认值 5x
3. **OKX 永续 API 限速**: 100x UHF 需要 OI/funding rate/mark price 3 个 endpoint, 频率高, 必须 cache + 共享 request slot
4. **paper_trading 4 周时间窗**: 启动后不能因代码 bug 丢失 PnL 数据, 必须 transaction log
5. **前端卡片 P3 "PAPER" 标签**: 用户必须一眼看出哪些是实盘哪些是 paper, 不能错

---

## PR 拆分

- **PR #55 (P0)**: horizon.py + informative.py + strategy_pool 改 + aggregator 改 + 前端 P0 卡片
- **PR #56 (P1)**: leverage.py + 中期/短期 tier + 前端杠杆徽章
- **PR #57 (P2)**: 超短期 (5m/15m) + 5x 杠杆
- **PR #58 (P3)**: okx_futures.py + paper_trading.py + 100x delta-neutral
- **PR #59 (复盘, 4 周后)**: 胜率/回撤分析报告 + 决定是否开实盘

---

## Task 列表

### Task 1: horizon tier 决策 (P0 起点)

**Files:**
- Create: `backend/app/signals/horizon.py`
- Test: `tests/test_signals/test_horizon.py`

**Interfaces:**
- Consumes: 无 (叶子模块)
- Produces: `HorizonTier` enum (P0_LONG / P0_CROSS_MONTH / P1_MID / P1_SHORT / P2_ULTRA / P3_UHF) + `TIER_CONFIG` dict (tf_list, hold_time, leverage_max)

- [ ] **Step 1: 写 failing test**

```python
def test_horizon_tier_enum_values():
    from app.signals.horizon import HorizonTier
    assert HorizonTier.P0_LONG.value == "P0_long"
    assert HorizonTier.P3_UHF.value == "P3_uhf"

def test_tier_config_p0_long():
    from app.signals.horizon import HorizonTier, TIER_CONFIG
    cfg = TIER_CONFIG[HorizonTier.P0_LONG]
    assert cfg.timeframes == ["1d", "1w"]
    assert cfg.leverage_max == 1
    assert cfg.hold_time_hours == 24 * 7  # 1 周

def test_tier_config_p3_uhf_delta_neutral():
    from app.signals.horizon import HorizonTier, TIER_CONFIG
    cfg = TIER_CONFIG[HorizonTier.P3_UHF]
    assert cfg.timeframes == ["1m", "5m"]
    assert cfg.leverage_max == 100
    assert cfg.delta_neutral_only is True
```

- [ ] **Step 2: 跑测试看它 fail**

Run: `cd backend && pytest tests/test_signals/test_horizon.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'app.signals.horizon')

- [ ] **Step 3: 实施 `horizon.py`**

```python
# backend/app/signals/horizon.py
from dataclasses import dataclass
from enum import Enum
from typing import List

class HorizonTier(str, Enum):
    P0_LONG = "P0_long"
    P0_CROSS_MONTH = "P0_cross_month"
    P1_MID = "P1_mid"
    P1_SHORT = "P1_short"
    P2_ULTRA = "P2_ultra"
    P3_UHF = "P3_uhf"

@dataclass(frozen=True)
class TierConfig:
    timeframes: List[str]
    hold_time_hours: int
    leverage_max: int
    delta_neutral_only: bool = False

TIER_CONFIG = {
    HorizonTier.P0_LONG: TierConfig(["1d", "1w"], 24*7, 1),
    HorizonTier.P0_CROSS_MONTH: TierConfig(["1w", "1M"], 24*60, 1),
    HorizonTier.P1_MID: TierConfig(["4h", "1d"], 24, 3),
    HorizonTier.P1_SHORT: TierConfig(["1h", "4h"], 12, 5),
    HorizonTier.P2_ULTRA: TierConfig(["5m", "15m"], 2, 5),
    HorizonTier.P3_UHF: TierConfig(["1m", "5m"], 1, 100, delta_neutral_only=True),
}
```

- [ ] **Step 4: 跑测试看它 pass**

Run: `cd backend && pytest tests/test_signals/test_horizon.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/signals/horizon.py backend/tests/test_signals/test_horizon.py
git commit -m "feat(signals): add horizon tier enum + tier config (P0-P3)"
```

---

### Task 2: informative 多 TF merge (P0 核心)

**Files:**
- Create: `backend/app/signals/informative.py`
- Test: `tests/test_signals/test_informative.py`

**Interfaces:**
- Consumes: `timeframe_to_seconds` (from freqtrade) + raw OHLCV DataFrame per TF
- Produces: merged DataFrame with all informative_timeframes joined

- [ ] **Step 1: 写 failing test**

```python
def test_merge_informative_timeframes_basic():
    from app.signals.informative import merge_informative_timeframes
    base = pd.DataFrame({"ts": [...], "close": [100, 101, 102]}, index=pd.to_datetime([...]))
    informative = pd.DataFrame({"ts": [...], "close": [200, 201]}, index=pd.to_datetime([...]))
    merged = merge_informative_timeframes(base, informative, base_tf="1h", informative_tf="4h")
    assert "close_4h" in merged.columns
    assert "close" in merged.columns  # 原 base close 保留
    assert len(merged) == len(base)

def test_merge_cache_ttl_respects_informative_candle_boundary():
    from app.signals.informative import InformativeCache
    cache = InformativeCache(maxsize=100)
    # 2 个 4h candle 之后, 1h 数据更新应触发 cache miss
    ...
```

- [ ] **Step 2: 跑测试看它 fail**

Run: `cd backend && pytest tests/test_signals/test_informative.py -v`
Expected: FAIL

- [ ] **Step 3: 实施 `informative.py`**

借鉴 [freqtrade `informative_decorator.py:1-50`](https://github.com/freqtrade/freqtrade/blob/develop/freqtrade/strategy/informative_decorator.py) 的 `_merge_prepared_informative_pair` 模式 + TLRUCache（`cachetools.TLRUCache`），**不拷代码**（GPL-3.0 传染）。

```python
# backend/app/signals/informative.py
import pandas as pd
from cachetools import TLRUCache, cached
from typing import Tuple

_INFORMATIVE_CACHE_TTL_CANDLES = 2

def merge_informative_timeframes(
    base_df: pd.DataFrame,
    informative_df: pd.DataFrame,
    base_tf: str,
    informative_tf: str,
) -> pd.DataFrame:
    """把 informative TF 的数据 join 到 base TF 上, 列加 _<informative_tf> 后缀"""
    suffix = f"_{informative_tf}"
    informative_renamed = informative_df.add_suffix(suffix)
    # 用 merge_asof 找最近一个 informative candle
    merged = pd.merge_asof(
        base_df.sort_index(),
        informative_renamed.sort_index(),
        left_index=True,
        right_index=True,
        direction="backward",
    )
    return merged

class InformativeCache(TLRUCache):
    """TLRU cache, entries expire 2 informative candles after last update"""
    pass
```

- [ ] **Step 4: 跑测试看它 pass**

Run: `cd backend && pytest tests/test_signals/test_informative.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/signals/informative.py backend/tests/test_signals/test_informative.py
git commit -m "feat(signals): add multi-timeframe merge (freqtrade-inspired)"
```

---

### Task 3: strategy_pool 加 horizon_tier 字段

**Files:**
- Modify: `backend/app/signals/strategy_pool.py:1-50` (每个 strategy dataclass)
- Test: `tests/test_signals/test_strategy_pool_horizon.py`

- [ ] **Step 1: 写 failing test**

```python
def test_each_strategy_declares_horizon_tier():
    from app.signals.strategy_pool import STRATEGIES
    for s in STRATEGIES:
        assert hasattr(s, "horizon_tier"), f"{s.name} missing horizon_tier"
        assert hasattr(s, "informative_timeframes"), f"{s.name} missing informative_timeframes"

def test_strategy_pool_covers_all_p0_tiers():
    from app.signals.strategy_pool import STRATEGIES
    from app.signals.horizon import HorizonTier
    p0_tiers = {s.horizon_tier for s in STRATEGIES if s.horizon_tier in (HorizonTier.P0_LONG, HorizonTier.P0_CROSS_MONTH)}
    assert len(p0_tiers) >= 1  # 至少 1 个 P0 策略
```

- [ ] **Step 2: 跑测试看它 fail**

Run: `cd backend && pytest tests/test_signals/test_strategy_pool_horizon.py -v`
Expected: FAIL

- [ ] **Step 3: 改 `strategy_pool.py`**

每个 strategy dataclass 加:
```python
horizon_tier: HorizonTier
informative_timeframes: List[str]  # e.g. ["1h", "4h"]
```

7 策略各自分配: P0×2 (long + cross-month), P1×2 (mid + short), P2×1 (ultra), P3×2 (uhf delta-neutral)

- [ ] **Step 4: 跑测试看它 pass**

Run: `cd backend && pytest tests/test_signals/test_strategy_pool_horizon.py -v`
Expected: PASS

- [ ] **Step 5: 跑全量测试看没回归**

Run: `cd backend && pytest tests/ -v`
Expected: 现有 60+ test 全 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/signals/strategy_pool.py backend/tests/test_signals/test_strategy_pool_horizon.py
git commit -m "feat(signals): tag each strategy with horizon_tier + informative_timeframes"
```

---

### Task 4: aggregator 跨 TF 共识 + 杠杆感知

**Files:**
- Modify: `backend/app/signals/aggregator.py:1-100`
- Test: `tests/test_signals/test_aggregator_multi_tf.py`

- [ ] **Step 1: 写 failing test**

```python
def test_aggregator_outputs_horizon_tier_field():
    from app.signals.aggregator import aggregate
    signals = [...]  # 7 个 strategy signals
    result = aggregate(signals, regime_probs={"bull": 0.7, "bear": 0.3})
    assert "horizon_tier" in result
    assert result["horizon_tier"] in ("P0_long", "P0_cross_month", "P1_mid", "P1_short", "P2_ultra", "P3_uhf")

def test_aggregator_detects_cross_tf_conflict():
    """P0 1d bull + P1 1h bear → output 'mixed' (不强加方向)"""
    from app.signals.aggregator import aggregate, detect_cross_tf_conflict
    conflict = detect_cross_tf_conflict([
        {"timeframe": "1d", "direction": "long"},
        {"timeframe": "1h", "direction": "short"},
    ])
    assert conflict is True
```

- [ ] **Step 2: 跑测试看它 fail**

Run: `cd backend && pytest tests/test_signals/test_aggregator_multi_tf.py -v`
Expected: FAIL

- [ ] **Step 3: 改 `aggregator.py`**

```python
def aggregate(signals, regime_probs):
    # 1. 按 horizon_tier 分组
    by_horizon = group_by(signals, key=lambda s: s.horizon_tier)
    # 2. 每组内部加权共识
    tier_results = {tier: weighted_consensus(group) for tier, group in by_horizon.items()}
    # 3. 跨 tier 冲突检测
    if cross_tf_conflict(tier_results):
        return {**tier_results, "horizon_tier": "mixed", "confidence": min(tier_results.values(), key=lambda x: x["confidence"])}
    # 4. 取主导 tier
    dominant = max(tier_results, key=lambda t: tier_results[t]["confidence"])
    return {**tier_results[dominant], "horizon_tier": dominant.value}
```

- [ ] **Step 4: 跑测试看它 pass**

Run: `cd backend && pytest tests/test_signals/test_aggregator_multi_tf.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/signals/aggregator.py backend/tests/test_signals/test_aggregator_multi_tf.py
git commit -m "feat(signals): aggregator cross-TF consensus + horizon_tier output"
```

---

### Task 5: quality_gate UHF 严格模式

**Files:**
- Modify: `backend/app/signals/quality_gate.py:1-80`
- Test: `tests/test_signals/test_quality_gate_uhf.py`

- [ ] **Step 1: 写 failing test**

```python
def test_quality_gate_rejects_uhf_without_funding_rate_data():
    from app.signals.quality_gate import gate
    signal = {"horizon_tier": "P3_uhf", "leverage": 100}
    market = {"funding_rate": None, "oi_24h_change": 0.02, "volume_24h_usdt": 1.5e9}
    result = gate(signal, market)
    assert result.passed is False
    assert "funding_rate_missing" in result.reasons

def test_quality_gate_accepts_uhf_delta_neutral_with_good_funding():
    from app.signals.quality_gate import gate
    signal = {"horizon_tier": "P3_uhf", "leverage": 100, "delta_neutral": True}
    market = {"funding_rate": 0.0001, "oi_24h_change": 0.01, "volume_24h_usdt": 1.5e9, "spread": 0.0003}
    result = gate(signal, market)
    assert result.passed is True
```

- [ ] **Step 2: 跑测试看它 fail**

Run: `cd backend && pytest tests/test_signals/test_quality_gate_uhf.py -v`
Expected: FAIL

- [ ] **Step 3: 改 `quality_gate.py`**

P3_UHF 走严 6 闸门（spec §3.D），其他 tier 走现有 gate

- [ ] **Step 4: 跑测试看它 pass**

Run: `cd backend && pytest tests/test_signals/test_quality_gate_uhf.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/signals/quality_gate.py backend/tests/test_signals/test_quality_gate_uhf.py
git commit -m "feat(signals): quality_gate UHF strict mode (6 hard thresholds)"
```

---

### Task 6: schema + API 输出 horizon_tier + leverage

**Files:**
- Modify: `backend/app/schemas/recommendations.py:1-40`
- Modify: `backend/app/api/recommendations.py:latest`
- Test: `tests/test_api/test_recommendations_horizon.py`

- [ ] **Step 1: 写 failing test**

```python
def test_recommendation_latest_filters_by_horizon(client):
    r = client.get("/api/recommendations/latest?pair=BTC-USDT&horizon=P0_long")
    assert r.status_code == 200
    data = r.json()
    assert data["horizon_tier"] == "P0_long"
    assert "leverage" in data
    assert "expires_at" in data

def test_recommendation_latest_without_horizon_returns_default(client):
    r = client.get("/api/recommendations/latest?pair=BTC-USDT")
    assert r.status_code == 200
    data = r.json()
    # 默认 P1_short (向后兼容, 现有前端用它)
    assert data["horizon_tier"] == "P1_short"
```

- [ ] **Step 2: 跑测试看它 fail**

Run: `cd backend && pytest tests/test_api/test_recommendations_horizon.py -v`
Expected: FAIL

- [ ] **Step 3: 改 schema + API**

```python
# schemas/recommendations.py
class RecommendationOut(BaseModel):
    pair: str
    direction: str
    confidence: float
    horizon_tier: str  # P0_long / P0_cross_month / P1_mid / P1_short / P2_ultra / P3_uhf
    leverage: int
    expires_at: datetime
    entry_price: float
    stop_loss: float | None
    take_profit: float | None
    paper_trading: bool  # True if P3
```

- [ ] **Step 4: 跑测试看它 pass**

Run: `cd backend && pytest tests/test_api/test_recommendations_horizon.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/recommendations.py backend/app/api/recommendations.py backend/tests/test_api/test_recommendations_horizon.py
git commit -m "feat(api): recommendations/latest filter by horizon + return leverage + paper_trading"
```

---

### Task 7: 前端 Recommendations 页面分组卡片

**Files:**
- Modify: `frontend/src/pages/Recommendations.tsx:1-200`
- Modify: `frontend/src/lib/api.ts:1-50`
- Test: `frontend/tests/recommendations-horizon.test.tsx`

- [ ] **Step 1: 写 failing test (component)**

```tsx
test("renders cards grouped by horizon_tier", () => {
  render(<Recommendations />);
  // mock API 返回 3 个不同 tier
  expect(screen.getByText("长期 1d/1w")).toBeInTheDocument();
  expect(screen.getByText("短期 1h")).toBeInTheDocument();
  expect(screen.getByText("UHF 1m (PAPER)")).toBeInTheDocument();
});

test("UHF card shows PAPER badge", () => {
  render(<Recommendations />);
  const uhfCard = screen.getByTestId("card-P3_uhf");
  expect(within(uhfCard).getByText("PAPER")).toBeInTheDocument();
});

test("leverage badge color: 1x gray, 3-5x yellow, 100x red", () => {
  render(<Recommendations />);
  expect(screen.getByTestId("leverage-100")).toHaveClass("bg-red-500");
  expect(screen.getByTestId("leverage-5")).toHaveClass("bg-yellow-500");
  expect(screen.getByTestId("leverage-1")).toHaveClass("bg-gray-500");
});
```

- [ ] **Step 2: 跑测试看它 fail**

Run: `cd frontend && npm test -- recommendations-horizon`
Expected: FAIL

- [ ] **Step 3: 改 `Recommendations.tsx`**

按 horizon_tier 分 6 个 section，每 section 渲染该 tier 的卡片。杠杆徽章按值染色。UHF 卡片加 "PAPER" 红标。

- [ ] **Step 4: 跑测试看它 pass**

Run: `cd frontend && npm test -- recommendations-horizon`
Expected: PASS

- [ ] **Step 5: 浏览器 e2e (用 browser-use MCP)**

```
1. navigate http://kbkkk.com/recommendations
2. screenshot 验证 6 个 section 都渲染
3. 点击 "UHF 1m (PAPER)" section, screenshot 看 PAPER 标签
4. 验证 leverage 100x 徽章是红色
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Recommendations.tsx frontend/src/lib/api.ts frontend/tests/recommendations-horizon.test.tsx
git commit -m "feat(frontend): recommendations page grouped by horizon + PAPER badge"
```

---

### Task 8: P0 完整验证 + PR #55

- [ ] **Step 1: 跑全量测试**

Run: `cd backend && pytest tests/ -v && cd ../frontend && npm test`
Expected: ALL PASS

- [ ] **Step 2: e2e 浏览器截图**

浏览器 MCP 打开 http://kbkkk.com/recommendations，截图 P0/P1/P2 卡片

- [ ] **Step 3: 部署到 kbkkk-prod**

Run: `bash scripts/deploy.sh` （规则 9 自动 deploy）

- [ ] **Step 4: 线上验证**

```bash
curl -s 'http://kbkkk.com/api/recommendations/latest?pair=BTC-USDT&horizon=P0_long' | jq '.horizon_tier, .leverage, .paper_trading'
```

Expected: `"P0_long"`, `1`, `false`

- [ ] **Step 5: Commit + Push + PR**

```bash
git checkout -b feat/multi-tf-p0
git push -u origin feat/multi-tf-p0
gh pr create --base main --head feat/multi-tf-p0 --title "feat(signals): P0 multi-TF long/short tier + horizon-aware recommendations"
```

---

## Self-Review 摘要

1. **Spec coverage**: spec 7 章节全覆盖 (3.A-3.E / 4 / 5 / 6 / 7)
2. **Step scan**: 7 tasks × 5-6 steps = 40 steps, 每 step 1 动作 + 1 检查
3. **Type consistency**: `HorizonTier` / `TIER_CONFIG` / `horizon_tier` 字段名一致
4. **Review Focus 5 类**: 跨 TF 矛盾 (T4) / 杠杆边界 (待 P1 Task 9) / OKX 限速 (待 P3 Task 12) / paper PnL (待 P3) / PAPER 徽章 (T7)
5. **Proportion**: plan 7 tasks (P0 范围) + 占位 P1/P2/P3 8-15 tasks = 完整 plan 预计 15-20 tasks，本 plan 写 P0 8 tasks = 平衡

---

**Plan 完成，保存在 `docs/superpowers/plans/2026-10-03-multi-tf-leverage-uhf.md`。请审阅本 plan。**

**实施方式选哪个**？
- **Subagent-driven**: 每 task 派 1 subagent + review 间 = 最彻底但慢
- **Native**: 本会话直接实施 = 快但上下文紧

**本 plan 我推荐 subagent-driven 因为**: TDD 6 步串行 + 跨 3 个子系统 (signals/api/frontend) + 16 文件改动，主对话上下文紧；子 agent 各 task 1 干净分支，冲突少。
