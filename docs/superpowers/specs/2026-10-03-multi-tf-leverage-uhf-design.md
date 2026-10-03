# Spec: 多时间框架 + 多杠杆档位 + UHF Paper-Trading (2026-10-03)

> **状态**：DRAFT — 等用户批准
> **路径**：architectural（Tier 3 跨 4 个子系统）
> **作者**：agent (按 `brainstorming` skill 走完整 architectural 流程)
> **关联**：[`bug-case-index.md`](../../.cursor/skills/experience-refinement/reference/bug-case-index.md) AG 条目 (kbkkk 502 已修) / `ai-trader-signals-engine` skill

---

## 1. 背景与目标

### 1.1 用户需求（2026-10-03 原文）

> 现在推荐中没有卡片，我要的是你有实时的或者分钟级的趋势分析判断，可以是未来任何时间的可以是 5 分钟后的，可以是 1h 后的，可以是 1天后的，可以是一周内的，时间范围一周内的多推荐，可以有长期的跨月份的推荐单，可以是长期的/中期的/短期的/超短期加杠杆的推荐单，而且在现货推荐单稳定后，我还要做合约超高频，100 倍杠杆这种，需要您重新设计和规划

### 1.2 目标（用户已确认，3 决策）

| 决策点 | 选择 | 原因 |
|--------|------|------|
| 优先级 | **长期/中期优先**（1d-1w + 跨月） | P0 用户核心需求 |
| 杠杆 | **现货 + 3x-5x** | UHF 先 paper 4 周再决定 |
| 交易所 | **OKX** (kbkkk 香港可达) | Binance 限流 |
| UHF | **先 paper trading 4 周** | 100x 风险大 |

### 1.3 非目标（明确不做）

- ❌ OKX + Binance 套利（单交易所简化）
- ❌ 50x-100x UHF **实盘**（先 paper 4 周后复盘）
- ❌ 期权 / 永续之外的合约类型
- ❌ 跨月推荐单自动下单（仅生成信号 + 推送）

---

## 2. 现状盘点

| 模块 | 现状 | gap |
|------|------|-----|
| `backend/app/signals/regime.py` | 单 timeframe 喂入 | ❌ 多 TF merge |
| `backend/app/signals/strategy_pool.py` | 7 策略 | ❌ 每策略没声明 informative_timeframes |
| `backend/app/signals/aggregator.py` | 单 TF 聚合 | ❌ 缺跨 TF 共识 + 杠杆感知 |
| `backend/app/signals/quality_gate.py` | 单 TF 质量门 | ❌ UHF 需要更严格 |
| API: `/api/recommendations/latest` | `timeframe: 5m\|15m\|1h\|4h\|1d` | ⚠️ 已有 5 TF 但前端只展示 1 TF |
| API: `/api/recommendations/history` | 同上 | ❌ 缺 horizon / leverage_tier 字段 |
| 前端 `recommendations` 页面 | **空白**（PR #53 之前 502，#54 修复） | ❌ 卡片渲染逻辑没接 timeframe 切换 |
| OKX 现货 | `AI_TRADER_DATA_SOURCE=okx` 已配 | ✅ |
| OKX 永续合约 | ❌ 无 connector | ❌ |
| 杠杆 | ❌ 无 | ❌ |
| UHF paper-trading | ❌ 无 | ❌ |

### 2.1 关键发现：timeframe 参数已存在

`backend/app/api/recommendations.py:history` 已接受 `timeframe: 5m|15m|1h|4h|1d` — **不是从 0 加**，是把已有 5 TF **接满 + 加 horizon + 加 leverage**。

---

## 3. 架构（3 段，逐段批准）

### 3.A 时间框架分级（horizon tiers）

**借鉴**：[`freqtrade/freqtrade/strategy/informative_decorator.py`](https://github.com/freqtrade/freqtrade/blob/develop/freqtrade/strategy/informative_decorator.py) (MIT, lines 1-50) — TLRUCache 缓存多 TF 合并结果。

```
horizon tier   TF       hold time   杠杆上限   UI 标签        P 等级
─────────────────────────────────────────────────────────────────────
P0 长期       1d/1w    1d-4w       1x(spot)   长期 1d/1w     P0
P0 跨月       1w/1M    2w-3M       1x(spot)   跨月 1w/1M     P0
P1 中期       4h/1d    4h-2d       3x         中期 4h        P1
P1 短期       1h/4h    1h-12h      5x         短期 1h        P1
P2 超短期     5m/15m   5m-2h       5x (P2 阶段)  超短 5m/15m   P2
P3 UHF paper  1m/5m    1m-30m      100x delta-neutral  UHF 1m     P3
```

**关键约束**：
- **杠杆 ≤ 5x** 给现货 + 1m-4h 短期（用户已确认）
- **100x UHF 必须 delta-neutral**（参考 [`godzilla-foundation/godzilla-community`](https://github.com/godzilla-foundation/godzilla-community) Apache 2.0, README 描述 funding rate arbitrage 模式）— **不能**裸多/裸空 100x
- **paper trading 4 周** = 100x UHF 在 paper 模块跑 4 周真实行情，统计胜率 / 资金费率 / 爆仓风险

### 3.B 新增 / 修改文件

| 文件 | 改动 |
|------|------|
| `backend/app/signals/horizon.py` ✨新增 | HorizonTier enum + 每 tier 的 (tf_list, hold_time, leverage_max) 表 |
| `backend/app/signals/informative.py` ✨新增 | 借鉴 freqtrade `informative_decorator`，给 strategy 声明依赖的高频 TF，自动 merge |
| `backend/app/signals/strategy_pool.py` 改 | 每个 strategy 加 `horizon_tier` 字段 + `informative_timeframes` 列表 |
| `backend/app/signals/aggregator.py` 改 | 接受 multi-TF input + 输出 `horizon_tier: P0/P1/P2/P3` 字段 |
| `backend/app/signals/quality_gate.py` 改 | UHF (P3) 走更严 gate：资金费率方向 + 24h 量能 + OI 变化 |
| `backend/app/signals/leverage.py` ✨新增 | 杠杆档位决策树：regime × volatility × confidence → 推荐 leverage |
| `backend/app/signals/paper_trading.py` ✨新增 | UHF 模拟账户，跟踪 100x delta-neutral 仓位 PnL |
| `backend/app/schemas/recommendations.py` 改 | RecommendationOut 加 `horizon_tier` + `leverage` + `expires_at` 字段 |
| `backend/app/api/recommendations.py` 改 | `/latest` 支持 `?horizon=P0|P1|P2|P3` 查询参数 |
| `backend/app/data/okx_futures.py` ✨新增 | OKX 永续合约 data connector（funding rate, OI, mark price）|
| `frontend/src/pages/Recommendations.tsx` 改 | 卡片按 horizon 分组 + 杠杆徽章 + UHF "PAPER" 标签 |
| `frontend/src/lib/api.ts` 改 | `getRecommendations(horizon?)` |
| `tests/test_signals/test_horizon.py` ✨ | horizon tier 决策测试 |
| `tests/test_signals/test_informative.py` ✨ | multi-TF merge 单元测试 |
| `tests/test_signals/test_paper_trading.py` ✨ | UHF paper PnL 模拟测试 |
| `tests/test_signals/test_leverage.py` ✨ | 杠杆决策树测试 |
| `docs/architecture/horizon-leverage.md` ✨ | 完整架构文档 |

### 3.C 数据流

```
                    ┌─────────────────┐
                    │ OKX 5m/15m/1h  │
                    │ 4h/1d/1w/1M   │ ──┐
                    └─────────────────┘   │
                                          ▼
                    ┌────────────────────────────────────┐
                    │ informative.py (多 TF merge cache)│
                    │ freqtrade-inspired TLRUCache      │
                    └────────────────────────────────────┘
                                          │
                                          ▼
                    ┌────────────────────────────────────┐
                    │ strategy_pool.py (7 策略)          │
                    │ + horizon_tier + informative_tfs   │
                    └────────────────────────────────────┘
                                          │
                                          ▼
                    ┌────────────────────────────────────┐
                    │ regime.py (多 TF regime 检测)      │
                    │ + 跨 TF 共识 (P0 1d vs 1h 同向)    │
                    └────────────────────────────────────┘
                                          │
                                          ▼
                    ┌────────────────────────────────────┐
                    │ aggregator.py                      │
                    │ → 7 策略信号 + regime + 杠杆决策   │
                    │ → RecommendationOut{horizon, lev}  │
                    └────────────────────────────────────┘
                                          │
                            ┌─────────────┴──────────────┐
                            ▼                            ▼
                  P0/P1/P2 → 实盘 (OKX 现货 / 1x-5x)   P3 → paper_trading.py
                            │                            │
                            ▼                            ▼
                  RecommendationHistory            PnL tracking
                  (recorder)                       (4 周后复盘)
                            │
                            ▼
                  GET /api/recommendations/latest?horizon=P0
                            │
                            ▼
                  前端 Recommendations.tsx
                  按 horizon 分组卡片
```

### 3.D 风险闸门（UHF paper 必须）

| 闸门 | 阈值 | 不满足时 |
|------|------|----------|
| 资金费率绝对值 | > 0.01% / 8h | 不开仓 |
| 24h 量能 | < 1B USDT | 不开仓 |
| OI 24h 变化 | < -5% | 不开仓（多空双爆迹象） |
| spread | > 0.05% | 不开仓 |
| 净值回撤 | > 5% | paper 暂停，统计 4 周 |
| 单仓杠杆 | 100x fixed | delta-neutral only |

### 3.E 验证策略（AGENTS.md 规则 2 强制）

- 单元测试：`pytest tests/test_signals/ -v`（4 个新测试文件）
- 回测：1 个月历史 OKX 数据跑 7 策略 + 新杠杆决策
- 模拟 UHF 4 周：paper_trading.py 跑真实行情，统计胜率/最大回撤/资金费率收益
- e2e：API `curl '/api/recommendations/latest?horizon=P0'` 返回新字段
- 前端：浏览器 MCP 截图 3 个 horizon tier 卡片

---

## 4. 借鉴出处（AGENTS.md 规则 8）

| Repo | License | 借鉴点 | 行号 |
|------|---------|--------|------|
| [freqtrade/freqtrade](https://github.com/freqtrade/freqtrade) (54979⭐) | GPL-3.0 (注意: 严格传染, 借鉴**模式**不拷代码) | `informative_decorator.py` 多 TF merge 模式 | informative_decorator.py:1-50 |
| [jesse-ai/jesse](https://github.com/jesse-ai/jesse) (8605⭐) | MIT | `Strategy.py` 基类 (routes / timeframe 声明) | jesse/strategies/Strategy.py |
| [godzilla-foundation/godzilla-community](https://github.com/godzilla-foundation/godzilla-community) (377⭐) | Apache-2.0 | funding rate arbitrage + delta-neutral 100x 模式 + 125μs tick-to-trade 延迟目标 | README "What is godzilla.dev" + WHITEPAPER.md |

> **License 提示**：freqtrade GPL-3.0 = 严格传染，**只借鉴模式不拷代码**。jesse MIT = OK 抄。godzilla Apache-2.0 = OK 抄。

---

## 5. 实现顺序（P0 → P1 → P2 → P3 串行）

| 阶段 | 范围 | 预计 | 验证 |
|------|------|------|------|
| **P0** | horizon.py + informative.py + strategy_pool/aggregator 改 + 前端 P0 卡片 | 3-4 天 | 单元测试 + 浏览器 e2e |
| **P1** | 中期 + 短期 + leverage.py 决策树 | 2-3 天 | 回测 + 单元测试 |
| **P2** | 超短期 (5m/15m) + 5x 杠杆 + 前端杠杆徽章 | 1-2 天 | 回测 + 单元测试 |
| **P3** | okx_futures.py + paper_trading.py + 100x delta-neutral + 4 周 paper | 2 周实现 + 4 周 paper + 复盘 | paper PnL 统计 |

> ⚠️ **关键约束**：P3 UHF 实盘门槛 = 4 周 paper 胜率 > 55% + 最大回撤 < 10%。**不达门槛不开实盘**。

---

## 6. 不在本 spec 范围（避免 scope creep）

- ❌ 用户 UI 自定义（多卡片拖拽、订阅推送）
- ❌ 策略权重自适应（ML 校准，规则 12 已锁 P3+ 才做）
- ❌ 跨交易所套利（Binance 限流，OKX 单一交易所）
- ❌ 期权 / DeFi / 永续外的合约类型

---

## 7. 关键决策点（需用户批准）

1. **架构（3.A 时间框架分级）** — 6 个 tier (P0/P1/P2/P3) + 杠杆上限 OK 吗？
2. **3.B 文件清单** — 16 个文件改动 OK 吗？是否要拆 PR？
3. **3.C 数据流** — UHF paper_trading.py 独立模块 OK 吗？
4. **3.D 风险闸门** — 100x delta-neutral + 6 个硬阈值 OK 吗？
5. **3.E 验证策略** — 4 周 paper 门槛（55% 胜率 / 10% 回撤）OK 吗？
6. **5. 实现顺序** — P0→P1→P2→P3 串行 4 周 + 4 周 paper 观察，**总 8 周**，OK 吗？
7. **4. License 借鉴** — freqtrade GPL-3.0 只借鉴模式不拷代码 OK 吗？

---

**下一步**：用户批准本 spec → agent 调 `writing-plans` skill 拆 bite-sized TDD 任务 → 用户逐 task 批准 → 子 agent 派单实施。
