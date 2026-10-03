# Spec: 2026-10-03 Recommendation 只跑 BTC+ETH + 进/离场时间

**Status**: Proposed
**Author**: agent (per user request)
**Date**: 2026-10-03

---

## Why

用户反馈（2026-10-03 18:04）：

1. **币种太多乱视线**："连主流币都没玩明白，还玩其他野路子币" — `recommendation_pairs` 当前 6 个币（SOL/BNB/XRP/DOGE + BTC/ETH），但用户实际操作只做 BTC/ETH。
2. **缺进/离场时间**："推荐单中还是没有进/离场的价格和时间，你有想让我可以操作吗" — 前端卡片已显示 Entry/SL/TP1/TP2 价格，但**没有时间指引**，用户拿到的卡片无法直接下单（不知道挂单有效到几时、SL 该几时挂）。

---

## What

### 改动 1：币种范围收敛到 BTC + ETH

| 层 | 文件 | 当前 | 改为 |
|---|---|---|---|
| 配置 | `backend/app/config.py` | 6 币 | `["BTC-USDT", "ETH-USDT"]` |
| WS 默认订阅 | `backend/app/data/okx_ws.py` `DEFAULT_PAIRS` | 5 币（含 DOGE） | `["BTC-USDT", "ETH-USDT"]` |
| 前端默认显示 | `frontend/src/pages/RecommendationsPage.tsx` `DEFAULT_PAIRS` | 6 币 | `["BTCUSDT", "ETHUSDT"]` |

### 改动 2：加进/离场时间字段

**Backend**（aggregator → schema → 写库）：

- `SignalAggregator.aggregate()` 输出新增 `entry_window_minutes` 和 `exit_window_minutes`：
  - **入场时段** = 当根 K 线 confirm 后到下一根 K 线 confirm 之间的窗口（min）
  - **离场时段** = SL/TP 期望被触发的窗口（min）
  - 计算口径：**基于 timeframe 推 N 根 K 线**（用户 18:04 已选）
    - `5m` → entry=5min, exit=15min (3 根)
    - `15m` → entry=15min, exit=60min (4 根)
    - `1h` → entry=60min, exit=240min (4 根)
    - `1d` → entry=1440min, exit=4320min (3 根)

- `RecommendationHistoryOut` schema 加 `entry_window_minutes: int | None` + `exit_window_minutes: int | None`
- DB 模型 `RecommendationHistory` 加同名字段（migration 用 `ALTER TABLE ADD COLUMN`，兼容已有 6 币历史）
- `recommendation_recorder._build_record()` 写入

**Frontend**（`EnhancedSignalCard`）：

- Entry 卡片下面加 1 行小字：「建议入场时段：生成后 1h 内（13:42 之前）」
- SL 卡片下面加 1 行小字：「预计离场时段：4h 内（17:42 之前）」
- TP1 卡片下面加 1 行小字：「预计离场时段：4h 内（17:42 之前）」
- 时间用本地时区显示

---

## How

### 阶段 1：改币种范围（最小风险，立即可上线）

1. 改 `config.py` `recommendation_pairs`
2. 改 `okx_ws.py` `DEFAULT_PAIRS`
3. 改 `frontend` `DEFAULT_PAIRS`
4. 重 build backend + 重启
5. 验证：看 `/api/signals?symbol=BTC-USDT` 和 ETH 仍正常，SOL/BNB/DOGE 404

### 阶段 2：加进/离场时间（按 TDD 顺序）

**RED**：写 backend 测试 `tests/test_aggregator_entry_exit_window.py`
- 给定 candles + timeframe=5m → 期望 entry_window_minutes=5, exit_window_minutes=15
- timeframe=1h → 60 / 240
- 缺 candles 时 → None / None

**GREEN**：改 `aggregator.py` 加常量表 + 输出字段
**DOR**：schema/db/前端展示串通

### 阶段 3：DB 迁移

```sql
ALTER TABLE recommendation_history
  ADD COLUMN IF NOT EXISTS entry_window_minutes INTEGER,
  ADD COLUMN IF NOT EXISTS exit_window_minutes INTEGER;
```

（用 `IF NOT EXISTS` 防重跑）

### 阶段 4：前端 build + 验证

1. 前端 `npm run build`
2. 看 kbkkk.com 上推荐卡片，Entry 卡片下是否出现"建议入场时段"
3. 浏览器截图存证

---

## Tasks

| # | 类型 | 内容 | 验证 |
|---|------|------|------|
| T1 | backend config | `config.py` `recommendation_pairs` → BTC+ETH | docker restart, `/api/recommendations/history?pair=SOL-USDT` 应为空 |
| T2 | backend ws | `okx_ws.py` `DEFAULT_PAIRS` → BTC+ETH | docker logs 无 "DOGE subscribe" |
| T3 | frontend | `DEFAULT_PAIRS` → BTCUSDT+ETHUSDT | `npm run build` 通过 |
| T4 | backend test | `test_aggregator_entry_exit_window.py` RED | `pytest` 期望 `SignalError` |
| T5 | backend impl | aggregator 加 entry/exit window 常量 + 字段 | `pytest` 绿 |
| T6 | schema | `RecommendationHistoryOut` 加 2 字段 | `tests/test_recommendations_schema.py` 通过 |
| T7 | db model | `RecommendationHistory` 加 2 列 + 写库字段 | alembic/autocommit 跑通 |
| T8 | db migration | `ALTER TABLE ADD COLUMN IF NOT EXISTS` | 生产 db 直接跑 |
| T9 | recorder | `_build_record` 写入新字段 | `_scan_one` 写后 db 查得到 |
| T10 | frontend | `EnhancedSignalCard` Entry/SL/TP1 卡片加"时段"行 | 浏览器 manual 验 + 截图 |
| T11 | deploy | 后端 rebuild + frontend rebuild + 重启 | `curl http://kbkkk.com/api/health` |
| T12 | 端到端验证 | BTC-USDT 1h 卡片 → 截图含 "建议入场时段" | 截图 + 上传 |

---

## Out of Scope

- 其他币种（SOL/BNB/DOGE/XRP）临时隐藏不删（用户没明确说删，留余地）
- entry_levels 多档（仍是 3 档：40/35/25%）
- 跟单流程（FollowDialog 不动）

---

## Risks

- 🟡 DB 迁移：旧 6 币历史行 `entry_window_minutes = NULL`，前端需隐藏 — 用 `?? '—'` fallback
- 🟡 前端 build cache：旧的 BTC/ETH 推荐缓存可能挡住新卡片展示，要 `refetch`

---

## Verification

| 方法 | 适用 |
|------|------|
| pytest test_aggregator_entry_exit_window | T4/T5 |
| pytest test_recommendations_api | T6/T7 |
| `curl http://kbkkk.com/api/recommendations/history?pair=BTC-USDT&timeframe=1h` | T11 看 entry_window_minutes 字段 |
| 浏览器 manual 验 + 截图 | T10/T12 |