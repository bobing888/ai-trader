# Dashboard 首页 — Multi-Symbol Overview + 未来预测

**Status:** Draft (待用户批准)
**Date:** 2026-10-03
**Owner:** ai-trader / Dashboard track (PR A of 缺口补完计划)
**前置依赖:** 无（仅依赖现有 `/api/ticker/batch` + `/api/signals`）
**后续 PR:** B (策略 hot-reload) → C (交易记录全量对比) → D (自进化调度器)

---

## 0. 目标（Goal）

把 ai-trader 的首页 `/` 从「单币种分析壳」升级为「多币种 dashboard 概览」，让用户进入首屏 **一眼看到**：

1. **关心的 N 个币**（默认 BTC/ETH/SOL/BNB/XRP/DOGE 共 6 个）当前价 + 24h 变动
2. **每个币的最新信号**（方向 + 置信度 + 质量档）
3. **每个币的下一预期走势**（aggregator 输出的 entry_zone / TP / SL / R:R 摘要）
4. **快速跳转到单币种深度页 / K 线 / 推荐页**

> **关键约束**：dashboard **只读**已有数据，不改信号引擎、不改任何后端核心逻辑（除非必要）。

---

## 1. 范围（Scope）

### 1.1 包含（In-Scope）

| 类别 | 组件 |
|------|------|
| **后端** | **新** `/api/dashboard/overview` — 单接口聚合 N 个币的 ticker + signal，返回 dashboard payload |
| **后端** | **新** `app/config.py` 加 `DASHBOARD_SYMBOLS` 配置项（默认 `["BTC-USDT","ETH-USDT","SOL-USDT","BNB-USDT","XRP-USDT","DOGE-USDT"]`） |
| **后端** | **新** `app/services/dashboard_service.py` — 内部用 `asyncio.gather` 并发拉 ticker + signal，组装 payload |
| **后端** | **新** Pydantic schema `app/schemas/dashboard.py`（OverviewItem / OverviewResponse） |
| **前端** | **新** `pages/DashboardPage.tsx` — 网格 + 卡片 + 跳转 |
| **前端** | **新** `components/Dashboard/SymbolCard.tsx` — 单币种卡 |
| **前端** | **新** `components/Dashboard/RecommendationSummary.tsx` — 卡片内嵌的信号摘要（方向/置信度/quality/R:R） |
| **前端** | **新** `lib/dashboardApi.ts` — API 客户端 + zod schema |
| **前端** | **改** `App.tsx` 路由：`/` → `DashboardPage`（原 AnalysisPage 保留在 `/analysis`） |
| **前端** | **改** `components/layout/AppLayout.tsx`（如有）导航 active 高亮适配 |
| **测试** | pytest：`test_dashboard_service` 验证并发聚合 / 失败降级 / mock 兼容 |
| **测试** | vitest：`SymbolCard.test.tsx` 渲染不同 quality / direction / 无信号场景 |

### 1.2 不包含（Out-of-Scope）

- ❌ **不**改 signal engine / aggregator / strategy pool
- ❌ **不**改 ticker 现有 API 行为（仅消费）
- ❌ **不**加 WS 实时推送（首页 5s 自动 refresh 即可，避免改造 ws_router）
- ❌ **不**加 ML/regime 校准
- ❌ **不**改 `/analysis` 路由（保留单币种深度页）
- ❌ **不**做移动端专项（响应式 grid 即可）
- ❌ **不**加"自选 watchlist 持久化"（v1 用配置项 + 本地 localStorage 临时偏好）

---

## 2. 架构（Architecture）

### 2.1 数据流

```
┌─────────────────────────────────────────────────────────────┐
│ GET /api/dashboard/overview                                  │
│   ?symbols=BTC-USDT,ETH-USDT,...&timeframe=1h               │
└─────────────┬───────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│ dashboard_service.fetch_overview(symbols, timeframe)         │
│   1. asyncio.gather(*ticker_batch)   ── 已有 /api/ticker/batch│
│   2. asyncio.gather(*signals_each)   ── 复用 aggregator       │
│      (内部复用现有 _fetch_candles_for + SignalAggregator)    │
│   3. 组装 OverviewResponse                                   │
└─────────────┬───────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│ DashboardPage (前端)                                         │
│   useEffect → fetch /api/dashboard/overview                  │
│   setInterval 5s auto-refresh                                │
│   grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3             │
│     → <SymbolCard> × N                                       │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 后端新文件

**`backend/app/api/dashboard.py`**
```python
router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/overview", response_model=OverviewResponse)
async def get_overview(
    symbols: Annotated[str, Query(description="逗号分隔")],
    timeframe: Annotated[str, Query(...)] = "1h",
):
    return await dashboard_service.fetch_overview(symbol_list, timeframe)
```

**`backend/app/services/dashboard_service.py`**（核心）
- `async def fetch_overview(symbols, timeframe) -> OverviewResponse`
- 内部用 `asyncio.gather` 并发拉
- 任意一个币失败 → 该币 payload 标记 `"degraded": true` + `"error": "..."`，**整体不失败**
- signal 复用 `signals.aggregator.SignalAggregator` 已经在 `/api/signals` 里用的逻辑（DRY）
- ticker 复用 `data.get_client().get_tickers_batch()`

**`backend/app/schemas/dashboard.py`**
```python
class OverviewItem(BaseModel):
    symbol: str
    price: float
    change_24h_pct: float
    signal: Optional[SignalSummary]  # null = 无信号
    degraded: bool = False
    error: Optional[str] = None

class SignalSummary(BaseModel):
    direction: str  # "long" | "short"
    confidence: float
    calibrated_confidence: Optional[float]
    quality: str  # "high" | "medium" | "low" | "reject"
    timeframe: str
    entry_zone_first: Optional[str]
    take_profit_1: Optional[float]
    stop_loss: Optional[float]
    risk_reward_ratio: float
    next_predicted_move: str  # e.g. "看多 ↑ 0.5% (high quality)"

class OverviewResponse(BaseModel):
    items: list[OverviewItem]
    timeframe: str
    source: str  # "binance" | "okx" | "mock"
    generated_at: datetime
```

### 2.3 前端新文件

**`frontend/src/lib/dashboardApi.ts`**
- `fetchOverview(symbols: string[], timeframe: string): Promise<OverviewResponse>`
- zod schema 校验 + type export

**`frontend/src/components/Dashboard/SymbolCard.tsx`**
- Props: `item: OverviewItem`, `onJump: (symbol) => void`
- 三种状态渲染:
  1. **有信号**（item.signal != null）:
     - 顶部：symbol + 24h change% (红/绿)
     - 中部：当前价 + 方向徽章（long=绿↑ / short=红↓ / no-signal=灰）
     - 置信度条 + quality 徽章（high/medium/low/reject 4 档配色）
     - 底部：R:R + "TP / SL" 摘要
     - 点击 → 跳 `/kline?symbol=BTC-USDT`
  2. **无信号**（item.signal == null 且 !degraded）:
     - 灰色卡片，"观望" 提示，点击仍可跳 K 线
  3. **降级**（degraded=true）:
     - 黄色边框 + ⚠️ 图标 + error 提示
- 视觉借鉴 `lauramyol13/crypto-signal-dashboard/src/components/indicator-card.tsx` 的 `signalConfig` map + icon
- 颜色系统借鉴 `marketcalls/trading-dashboard/src/App.js` 的 watchlist 红绿配色

**`frontend/src/components/Dashboard/RecommendationSummary.tsx`**
- SymbolCard 内部的子组件，专注信号摘要布局

**`frontend/src/pages/DashboardPage.tsx`**
- 顶部：标题 + timeframe 切换器（1h / 4h / 1d）+ 币种筛选（多选 checkbox，从配置读）
- 主区：响应式 grid
- 自动 5s refresh（用 useState + setInterval + cleanup）
- 空态：loading skeleton / error retry

**`frontend/src/App.tsx`** 路由改动：
```tsx
<Route path="/" element={<DashboardPage />} />          {/* 改 */}
<Route path="/analysis" element={<AnalysisPage />} />   {/* 保留 */}
```

### 2.4 借鉴的 GitHub 调研成果

> 完整调研笔记见 `docs/architecture/github-survey-dashboard-2026-10-03.md`（本 PR 一并提交）

| 借鉴源 | 借鉴点 | 本项目怎么用 |
|--------|--------|------------|
| `lauramyol13/crypto-signal-dashboard` (MIT) | `signalConfig` 颜色/图标 map (indicator-card.tsx:5-12) | SymbolCard 的 direction/quality 配色 |
| `lauramyol13/crypto-signal-dashboard` (MIT) | `ALL_PAIRS as const` 类型化 symbol 列表 (binance.ts:11-19) | `DASHBOARD_SYMBOLS` 配置项的 type hint |
| `lauramyol13/crypto-signal-dashboard` (MIT) | `fetchCandles` + `fetch24hStats` 24h 拉一次 + price 10s 拉一次的分级缓存 (binance.ts:31,49) | 我们的 ticker 已有 revalidate 概念，dashboard 5s refresh 沿用 |
| `marketcalls/trading-dashboard` (MIT) | Market Summary 顶部 grid + Watchlist 侧边双区布局 (App.js:56-103) | 顶部 grid 1x3 重要币 + 主区 6 币卡片 |
| `nMaroulis/sibyl` (Apache-2.0) | multi-symbol `dashboard/api/overview` 思路 + LLM 摘要（仅借鉴模式，不抄 LLM 集成） | 我们用 aggregator 替代 LLM 摘要，但 payload 形态相似 |

**不抄**：
- crypto-signal-dashboard 的 TEE/LLM/OpenGradient — 我们不引入 LLM 链
- sibyl 的 Streamlit/llm_gateway — 我们是 React/FastAPI 栈
- marketcalls 的静态 mock — 我们是真数据

---

## 3. 数据 / 接口契约（Contract）

### 3.1 API 契约

**请求**：
```
GET /api/dashboard/overview?symbols=BTC-USDT,ETH-USDT,SOL-USDT&timeframe=1h
```

**响应** (200)：
```json
{
  "items": [
    {
      "symbol": "BTC-USDT",
      "price": 67890.12,
      "change_24h_pct": 1.45,
      "signal": {
        "direction": "long",
        "confidence": 0.72,
        "calibrated_confidence": 0.68,
        "quality": "high",
        "timeframe": "1h",
        "entry_zone_first": "📈 中线：现价下方 2-3% 分批建仓",
        "take_profit_1": 68560.0,
        "stop_loss": 67200.0,
        "risk_reward_ratio": 1.33,
        "next_predicted_move": "看多 ↑ 0.5% (high)"
      },
      "degraded": false,
      "error": null
    }
  ],
  "timeframe": "1h",
  "source": "okx",
  "generated_at": "2026-10-03T03:04:05Z"
}
```

**降级示例** (单币失败)：
```json
{
  "symbol": "DOGE-USDT",
  "price": 0.0,
  "change_24h_pct": 0.0,
  "signal": null,
  "degraded": true,
  "error": "rate limit"
}
```

**错误** (400 / 500)：
- 400: `symbols` 缺失 / 超过 50 个
- 500: 全局错误（极少见，因为 gather 内 catch 全部降级）

### 3.2 前端契约

- `OverviewResponse` zod schema 必须 100% 匹配后端
- SymbolCard 接受 `degraded` / `error` 渲染降级态，**不** throw
- DashboardPage 整体错误（fetch 失败）→ 顶部 banner + retry 按钮

---

## 4. 验证（Verification）

### 4.1 后端测试

| 测试 | 文件 | 验证 |
|------|------|------|
| `test_fetch_overview_normal` | `tests/test_dashboard.py` | mock ticker + signal → 正确聚合 |
| `test_fetch_overview_degraded` | 同上 | 单币 signal 抛异常 → 该币 degraded=true，整体 200 |
| `test_fetch_overview_empty_symbols` | 同上 | 空 symbols → 400 |
| `test_fetch_overview_too_many` | 同上 | 51 个 symbol → 400 |
| `test_fetch_overview_no_signal` | 同上 | signal=None → item.signal=null，但 price 仍返回 |
| `test_overview_response_schema` | 同上 | pydantic 校验通过 |
| 集成 | `curl 'http://127.0.0.1:8765/api/dashboard/overview?symbols=BTC-USDT,ETH-USDT&timeframe=1h'` | 返回 200 + items 长度 = 2 |

### 4.2 前端测试

| 测试 | 文件 | 验证 |
|------|------|------|
| `SymbolCard.test.tsx` | vitest | 3 态（有信号 / 无信号 / 降级）各 snapshot 一张 |
| `DashboardPage.test.tsx` | vitest | render + mock fetch + 验证 grid 数量 + 跳转 onJump 被调 |
| `dashboardApi.test.ts` | vitest | zod schema 校验 + 错误响应 throw |

### 4.3 手动验证（E2E）

启动 dev server，按 scenario 走：
1. **空态**：清空 DB → / 显示 loading → 6 个 SymbolCard 渲染 → 无信号卡片灰色
2. **有信号**：注入一条 aggregator 产出 → / 显示绿色 long 卡片 + 置信度条
3. **降级**：让 OKX 单 symbol 限流 → 该卡片变黄 + ⚠️
4. **跳转**：点 BTC 卡 → 路由到 `/kline?symbol=BTC-USDT`
5. **timeframe 切换**：1h → 4h → 重新 fetch + 卡片刷新
6. **auto refresh**：5s 后无操作 → 卡片数据更新（用 console.log 验证 refetch）

### 4.4 部署验证

按规则 9 走 `bash scripts/deploy.sh` → 等部署完成 → `curl -sS 'http://kbkkk.com/api/dashboard/overview?symbols=BTC-USDT&timeframe=1h'` → 截图证明线上可用。

---

## 5. 风险与回滚（Risk & Rollback）

| 风险 | 缓解 |
|------|------|
| 6 个 symbol × signal 计算 = 6 × 200ms → 总 1.2s 首屏慢 | `asyncio.gather` 并发；超时 3s 单币失败即降级 |
| ticker 限流 | 沿用 `/api/ticker/batch` 现有 rate limit；dashboard 5s 间隔 OKX 远低于 20 req/s |
| 前端 auto refresh 频繁触发 WS 类似问题 | 仅 fetch 一个聚合接口，不连 WS，5s 一次远低于 ticker 限流 |
| schema 不匹配前端 | pydantic + zod 双 schema + curl 验证后写前端 |
| 改造 App.tsx 路由影响现有用户 | `/analysis` 路由保留，旧用户书签无影响；`/` 改 DashboardPage 是新增行为，不删旧功能 |

**回滚**：PR revert + `bash scripts/deploy.sh` 即可（前端是纯静态 dist，无状态）

---

## 6. 改动文件清单（File Manifest）

**新增**（10）：
- `backend/app/api/dashboard.py`
- `backend/app/services/dashboard_service.py`
- `backend/app/schemas/dashboard.py`
- `backend/app/config.py`（追加 DASHBOARD_SYMBOLS）
- `backend/tests/test_dashboard.py`
- `frontend/src/lib/dashboardApi.ts`
- `frontend/src/components/Dashboard/SymbolCard.tsx`
- `frontend/src/components/Dashboard/RecommendationSummary.tsx`
- `frontend/src/pages/DashboardPage.tsx`
- `frontend/src/__tests__/DashboardPage.test.tsx`
- `frontend/src/__tests__/SymbolCard.test.tsx`
- `docs/architecture/github-survey-dashboard-2026-10-03.md`

**修改**（3）：
- `backend/app/main.py`（注册新 router）
- `frontend/src/App.tsx`（`/` 路由改 DashboardPage）
- `frontend/src/components/layout/AppLayout.tsx`（如有，导航 active 高亮）

---

## 7. 实施步骤（Implementation Steps）

按 TDD-scaffold 走 RED → GREEN → REFACTOR：

1. **RED #1**：写 `test_dashboard.py` 的失败用例
2. **GREEN #1**：实现 `dashboard_service.py` + `schemas/dashboard.py`
3. **RED #2**：写 `test_dashboard.py` 的 API 集成测试
4. **GREEN #2**：实现 `api/dashboard.py` + 注册到 `main.py`
5. **集成测试**：`curl` 跑通 `/api/dashboard/overview`
6. **RED #3**：写前端 zod schema test
7. **GREEN #3**：实现 `dashboardApi.ts`
8. **RED #4**：写 `SymbolCard.test.tsx` 3 态 snapshot
9. **GREEN #4**：实现 `SymbolCard.tsx` + `RecommendationSummary.tsx`
10. **RED #5**：写 `DashboardPage.test.tsx`
11. **GREEN #5**：实现 `DashboardPage.tsx`
12. **改 App.tsx** 路由
13. **REFACTOR**：提 PR 前的代码 review（spec compliance + code quality）
14. **提 PR + 自合**（按规则 7/9）
15. **部署**：`bash scripts/deploy.sh`
16. **线上验证**：`curl http://kbkkk.com/api/dashboard/overview` + 浏览器截图

---

## 8. 后续 PR 链接

- **PR B**：策略 hot-reload（github_sync → strategy_pool 自动 reload）
- **PR C**：交易记录全量对比（UserFollow vs 全 RecommendationHistory）
- **PR D**：自进化调度器（outcome → 策略权重自调 + 回滚）
