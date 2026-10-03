# GitHub Survey: Crypto / Trading Dashboard（PR A — Dashboard 首页）

**Date:** 2026-10-03
**Trigger:** AGENTS.md 规则 8（动手前先 GitHub 调研）
**Search queries 派生:**
- `crypto trading dashboard overview`
- `crypto dashboard`
- `trading dashboard`
- `okx binance signal dashboard`
- `trading signals multi symbol react`
- `ai crypto signal`

---

## 候选 repos（按 star + license 排序）

| Repo | Stars | License | Pushed | Verdict |
|------|------:|---------|--------|---------|
| `JayeshLab/vue-crypto-dashboard` | 242 | MIT | 2025-06-23 | Vue 栈，**不借鉴** |
| `nMaroulis/sibyl` | 74 | Apache-2.0 | 2026-01-07 | 借鉴 dashboard 模式（Streamlit 太重） |
| `lauramyol13/crypto-signal-dashboard` | 87 | MIT | 2026-09-14 | **首推**：单币种深页，颜色/icon map 直接借鉴 |
| `marketcalls/trading-dashboard` | 31 | MIT | 2024-06-23 | 借鉴 Watchlist + Market Summary 双区布局 |
| `olayemii/crypto-dashboard` | 117 | none | 2021-09-14 | 4 年未更新，跳过 |
| `fyangch/crypto-dashboard` | 44 | MIT | 2023-06-29 | 2 年未更新，仅参考 |
| `BobsProgrammingAcademy/cryptocurrency-dashboard` | 37 | MIT | 2025-12-28 | 纯 CoinGecko + Chart.js，借鉴有限 |

---

## 选 ≥2 个 credible repos 深入读

### 1. `lauramyol13/crypto-signal-dashboard` (MIT) ⭐ 87

**Clone path:** `/tmp/dash-research/crypto-signal-dashboard/`
**Stack:** Next.js 15 + TypeScript + Tailwind + lucide-react + Redis (cache)
**核心结构**：
```
src/
├── app/api/signals/route.ts   ← /api/signals 单币种 GET
├── app/page.tsx                ← 单页 (pair selector + indicators + chart)
├── components/
│   ├── indicator-card.tsx      ← 单指标卡
│   ├── consensus-bar.tsx       ← 共识进度条
│   ├── signal-history.tsx      ← 历史信号列表
│   └── pair-selector.tsx
└── lib/
    ├── binance.ts              ← ALL_PAIRS const + fetchCandles/fetchCurrentPrice/fetch24hStats
    ├── indicators.ts           ← 6 个指标 (SMA, EMA, RSI, MACD, Bollinger, Volume)
    ├── opengradient.ts         ← TEE 验证的 AI 集成（**不抄**）
    ├── og-models.ts            ← ONNX 模型（**不抄**）
    └── types.ts
```

**借鉴点（已落到 spec §2.4）**：

1. **颜色 + icon map 模式**（`indicator-card.tsx:5-12`）
   ```tsx
   const signalConfig = {
     bullish:   { icon: TrendingUp,   color: 'text-og-success', ... },
     bearish:   { icon: TrendingDown, color: 'text-og-error',   ... },
     neutral:   { icon: Minus,        color: 'text-zinc-400',   ... },
   };
   ```
   → 我们的 `SymbolCard` 用 `direction → {icon, color}` + `quality → {border, badge}` 同样模式

2. **类型化 symbol 列表**（`binance.ts:11-19`）
   ```ts
   export const ALL_PAIRS = ['BTCUSDT', 'ETHUSDT', ...] as const;
   export type Pair = (typeof ALL_PAIRS)[number];
   ```
   → 我们的 `DASHBOARD_SYMBOLS` 在 `config.py` 同样强类型（`list[str]` + 白名单校验）

3. **分级缓存策略**（`binance.ts:31,49`）
   ```ts
   fetchCandles:   revalidate: 60   // 1 小时
   fetch24hStats:  revalidate: 60   // 1 小时
   fetchCurrentPrice: revalidate: 10 // 10 秒
   ```
   → 我们的 `/api/ticker/batch` 已有，但 dashboard 5s refresh 是用户主动行为，不调缓存策略

4. **consensus 三色进度条**（`consensus-bar.tsx`）—— 不直接抄（我们已有 aggregator confidence），但 `bullish/bearish/neutral` 三色配色值得借鉴

**License 兼容**：MIT ✅，可借鉴模式 + 部分代码片段（不抄整段）

### 2. `nMaroulis/sibyl` (Apache-2.0) ⭐ 74

**Clone path:** `/tmp/dash-research/sibyl/`
**Stack:** Python + Streamlit + FastAPI + llm_gateway（重）
**核心：** AI-powered crypto insights + LLM agent 工具调用
**借鉴点**：
- multi-symbol `dashboard/api/overview` 模式（**模式借鉴**，不抄 llm_gateway 集成）
- LLM 作为"摘要生成器"的思路（**不采用**，我们用 aggregator 输出 + 模板字符串生成 `next_predicted_move`）

**License 兼容**：Apache-2.0 ✅

### 3. `marketcalls/trading-dashboard` (MIT) ⭐ 31

**Clone path:** `/tmp/dash-research/trading-dashboard/`
**Stack:** React + Recharts + Tailwind (单文件 App.js)
**核心：** Stock indices dashboard，**不是 crypto** 但布局可借鉴

**借鉴点**（`App.js:56-103`）：
- **顶部 Market Summary 4 列 grid** + **侧边 Watchlist 列表**的双区布局
- hover 高亮 + 红绿配色（绿涨红跌）
- 4 个 index + 8 个 watchlist 的密度

→ 我们的 dashboard 借鉴：**顶部 grid 1x3 重要币 + 主区 6 币卡片**的密度

**License 兼容**：MIT ✅

---

## 适配决策（adaptation）

| 借鉴项 | 怎么改 |
|--------|--------|
| 类型化 ALL_PAIRS | ai-trader 用 `OKX_SYMBOL_WHITELIST` 已有，我们加 `DASHBOARD_SYMBOLS` 配置 + pydantic 校验 |
| signalConfig map | 我们的 SymbolCard 用 `direction` + `quality` 双 map |
| consensus 三色 | 不抄进度条（已有 confidence 度量），但配色用同一套 tailwind 红绿灰 |
| Market Summary grid | 借鉴 4 列 grid 形态，**不**做侧边 watchlist（首屏太挤） |
| LLM 摘要 | **不引入 LLM**，用 `aggregator.entry_zones[0]` + quality 模板拼 `next_predicted_move` |

---

## 没解决的问题

3 个 repo **都没**真正实现"多币种 dashboard 概览"：
- crypto-signal-dashboard 是**单币种深页**（pair selector 切换）
- sibyl 是**单页 LLM insight**
- marketcalls 是**静态 mock + 股票**

→ 这是 ai-trader Dashboard 的差异化点，**我们自己造 grid**（靠已有 `/api/ticker/batch` + `/api/signals` 拼装）

---

## 引用出处

- lauramyol13/crypto-signal-dashboard: https://github.com/lauramyol13/crypto-signal-dashboard (MIT)
- nMaroulis/sibyl: https://github.com/nMaroulis/sibyl (Apache-2.0)
- marketcalls/trading-dashboard: https://github.com/marketcalls/trading-dashboard (MIT)
