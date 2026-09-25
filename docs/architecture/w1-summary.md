# W1 总结 — 基础设施 + 数据层

> 日期：2026-09-25  
> 状态：✅ 完成  
> 耗时：约 1 小时（含 GitHub 调研 4 份子任务）

---

## 完成清单

### 1. GitHub 调研（4 份并行，异步完成）

| 调研 | 子 agent | License 覆盖 | 关键结论 |
|------|---------|------------|---------|
| freqtrade 策略库 | ✅ | MIT/Apache-2.0 7 个 | CryptoFrog + SmartMoneyStrategy + GeneStrategy 最值得借鉴 |
| 推荐单引擎架构 | ✅ | 6 方案 + 平台实现 | Gaussian HMM + Affinity Matrix 是最严谨方案 |
| Dashboard UI | ✅ | 5 个 React 项目源码 | lightweight-charts v5 + Zustand + Socket.io 是 2026 最佳组合 |
| 回测复盘系统 | ✅ | 7 工具 + SQL 聚合 | QuantInvestStrats (Apache-2.0) 归因算法最完整 |

全部汇总至 [github-survey.md](github-survey.md)。

---

### 2. 后端骨架（FastAPI）

```
backend/
├── app/
│   ├── main.py              # FastAPI 入口 + CORS
│   ├── config.py            # pydantic-settings 配置
│   ├── api/
│   │   ├── health.py        # GET /api/health, /api/ping
│   │   ├── klines.py        # GET /api/klines/{symbol}
│   │   └── trades.py        # GET /api/trades, /api/trades/stats/summary
│   └── models.py            # Pydantic schemas（预留）
├── tests/
│   ├── conftest.py
│   ├── test_health.py       # 4 个测试
│   ├── test_klines.py       # 6 个测试
│   └── test_trades.py       # 7 个测试
└── pyproject.toml
```

**REST API 端点（当前）**：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/ping` | GET | 存活检查 |
| `/api/klines/{symbol}` | GET | K 线数据（mock，freqtrade 接入留接口）|
| `/api/trades` | GET | 交易列表（freqtrade SQLite 优先，mock fallback）|
| `/api/trades/stats/summary` | GET | 交易统计概览 |
| `/api/trades/{id}` | GET | 单笔交易详情 |

**测试结果**：18/18 通过 ✅

---

### 3. 前端骨架（React + TypeScript + Vite）

```
frontend/
├── src/
│   ├── main.tsx             # QueryClient + i18n 初始化
│   ├── App.tsx             # 路由 + 侧边栏布局
│   ├── lib/api.ts          # Axios 客户端 + API 类型
│   ├── stores/klineStore.ts # Zustand store
│   ├── components/
│   │   ├── KlineChart.tsx  # lightweight-charts 完整 K 线 + 成交量
│   │   └── SymbolPicker.tsx # Symbol 下拉 + Timeframe 切换
│   ├── pages/
│   │   ├── KlinePage.tsx   # K 线主页面
│   │   ├── TradesPage.tsx  # 交易记录 + KPI 仪表盘
│   │   ├── RecommendationsPage.tsx  # 推荐单（占位，W2）
│   │   ├── BacktestPage.tsx       # 回测复盘（占位，W3）
│   │   └── SettingsPage.tsx        # 设置（语言切换）
│   ├── i18n/
│   │   ├── index.ts        # react-i18next 初始化
│   │   └── locales/
│   │       ├── zh-CN.json
│   │       └── en.json
│   └── __tests__/
│       └── App.test.tsx     # 2 个测试
├── vite.config.ts          # Tailwind v4 + React + Proxy 到后端 8765
├── package.json
└── tsconfig.json
```

**技术栈（2026 最佳组合）**：

| 组件 | 选型 |
|------|------|
| K 线 | lightweight-charts v5（CandlestickSeries + HistogramSeries）|
| 状态管理 | Zustand |
| 服务器状态 | TanStack Query v5 |
| i18n | react-i18next |
| UI | Tailwind CSS v4 + @theme CSS 变量 |
| 图表 | Candlestick + Volume（复用 lightweight-charts）|

**测试结果**：2/2 通过 ✅（Network Error 是 jsdom 环境预期行为）

**Type check**：✅ 通过  
**Build**：✅ 通过（489KB → 159KB gzip）

---

## 场景覆盖验证

| 场景 | 验证方式 | 结果 |
|------|---------|------|
| K 线加载（BTCUSDT，1h，500 根）| 截图 | ✅ |
| K 线加载（ETHUSDT，1d，500 根）| 截图 | ✅ |
| Timeframe 切换（1m → 4h）| 截图 | ✅ |
| Symbol 切换（BTCUSDT → ETHUSDT）| 截图 | ✅ |
| 交易页加载 + KPI 卡渲染 | 截图 | ✅ |
| 交易页数据正负色（绿/红 PnL）| 截图 | ✅ |
| 设置页语言切换按钮 | 截图 | ✅ |
| 健康检查 `/api/health` | curl | ✅ 200 |
| K 线 API `/api/klines/BTCUSDT` | curl | ✅ 200 |
| 交易 API `/api/trades` | curl | ✅ 200 |
| 统计 API `/api/trades/stats/summary` | curl | ✅ 200 |
| 前端代理到后端 | curl | ✅ 200 |
| 前端 build 成功 | pnpm build | ✅ |

**场景覆盖：13/13 通过** ✅

---

## 截图证据

### K 线页面（BTCUSDT 1h）
![K线页面](w1-kline-btcusdt-1h.png)

### K 线页面（切换 4h）
![K线切换4h](w1-kline-btcusdt-4h.png)

### 交易页面（KPI + 表格）
![交易页面](w1-trades-page.png)

### 设置页面（语言切换）
![设置页面](w1-settings-page.png)

---

## 技术债务 / 待改进

| 事项 | 优先级 | 说明 |
|------|--------|------|
| Tailwind v4 `@theme` CSS 变量与 shadcn/ui 配色体系未完全对齐 | 低 | W3 UI 增强时统一 |
| 推荐单/回测页为占位文本 | 低 | W2/W3 分别实现 |
| 缺乏 E2E 测试（Playwright）| 中 | W4 阶段补入 |
| 后端 freqtrade SQLite 路径硬编码 | 中 | W2 前改为配置化 |

---

## 下一步（W2：推荐单引擎）

1. **RegimeDetector** — Gaussian HMM 4 态（bull/choppy/high_vol/crisis）
2. **StrategyPool** — 7 个策略骨架（模板从 github-survey.md 选取）
3. **SignalAggregator** — Affinity Matrix 软加权
4. **ConfidenceScorer** — 置信度公式
5. **推荐单 REST API** — `GET /api/recommendations`
6. **前端推荐单页面** — 卡片列表 + K 线联动 + WebSocket 实时

---

## 服务地址

| 服务 | 地址 |
|------|------|
| 后端 FastAPI | `http://127.0.0.1:8765` |
| 后端 API 文档 | `http://127.0.0.1:8765/docs` |
| 前端 Vite | `http://127.0.0.1:5174` |
| 前端 proxy → 后端 | `/api` → `127.0.0.1:8765` |
