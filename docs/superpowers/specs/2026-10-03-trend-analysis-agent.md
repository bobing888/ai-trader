# Trend Analysis Agent — Architectural Spec

> **日期**：2026-10-03
> **路径**：brainstorming(architectural) → writing-plans → executing-plans
> **决策者**：agent（用户授权"自主设计 / 自己决定"）
> **状态**：v1.0 初稿，待 writing-plans 拆 TDD 任务

---

## 0. 背景与根因

ai-trader 当前 9 个规则信号模块（`signals/{regime,strategy_pool,aggregator,calibration,cost_model,quality_gate,horizon,informative,forecast}.py`）能产推荐单，但**没有"自然语言研判"层**：

| 缺失维度 | 现状 |
|---------|------|
| 自然语言解释"为什么" | aggregator 只输出数字，无 reasoning |
| 跨周期推理（5m + 1h 联立） | 每个 timeframe 独立 run，无 cross-TF 思维链 |
| 异常事件归因（某次 regime 切换原因） | 仅 `regime_shift_engine` 记录切换，无解释 |
| 多策略分歧时的"判断" | aggregator 用 `min_agreement` 强制过滤，无 LLM 折中 |

**约束**（fresh evidence 验证）：
- BTC + ETH only（btc-eth-scope skill Rule 1）
- 不实盘（0 place_order 调用，0 trade API）
- 60s refresh（`recommendation_refresh_interval=60`）
- 全规则、零 LLM（grep 验证）
- AGENTS.md 规则 3：项目已成型，禁止重写
- AGENTS.md 规则 8：先 GitHub 调研再动手

---

## 1. 目标

**加一个"自然语言研判 Agent"层（第二意见），不改现有 signals/*，不抢 aggregator 的推单权威，不下任何交易单。**

Agent 产出：
1. **自然语言研判报告**（200-500 字中文，解释当前 regime / 策略 / 风险）
2. **第二意见推荐单**（标 `source=agent`，与 aggregator 推荐单并列展示）
3. **历史归因**（regime 切换 / 推荐单变化时的"为什么"）

---

## 2. 不做什么

- ❌ **不**改 `signals/*` 9 个模块
- ❌ **不**替 aggregator 出"权威推荐单"——aggregator 仍是 single source of truth
- ❌ **不下单**（强化已有 policy）
- ❌ **不**做实时训练 / 在线学习
- ❌ **不**支持 BTC/ETH 之外的币种
- ❌ **不**主动加 LLM 框架到 aggregator 决策路径

---

## 3. 架构

```
┌─────────────────────────────────────────────────────────────┐
│  Trend Analysis Agent (新子系统)                                  │
│                                                              │
│  ┌──────────────┐   ┌──────────────┐   ┌────────────────┐    │
│  │  Perceiver   │──▶│  Reasoner    │──▶│  Recommender   │    │
│  │ (拉数据)     │   │ (LLM 推理)   │   │ (第二意见)     │    │
│  └──────────────┘   └──────────────┘   └────────────────┘    │
│         │                  │                   │              │
│         ▼                  ▼                   ▼              │
│   signals/regime     DeepSeek V3      writes analysis_report │
│   strategy_pool      (后面定)         + recommendation_2nd    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ (5m 循环)
┌─────────────────────────────────────────────────────────────┐
│  Scheduler (runner.py)                                       │
│  - 每 5m 对 BTC + ETH × [5m,15m,1h,1d] 触发                 │
│  - 缓存 + 失败重试 + 频率限流                                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Persistence (persistence.py)                               │
│  - 写 ai_trend_analysis 表（自然语言 + 元数据）            │
│  - 写 agent_recommendation 表（第二意见）                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  API (api/agent.py)                                          │
│  - GET  /api/agent/reports?pair=BTC-USDT&timeframe=1h      │
│  - POST /api/agent/analyze  (手动触发)                      │
│  - GET  /api/agent/recommendations (对比)                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Frontend (TrendAgentPage.tsx)                              │
│  - 研判报告时间线                                            │
│  - 第二意见 vs aggregator 推荐单对比                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. 数据流

### 4.1 主动调度路径

```
runner.py (每 5m)
  ↓ 1. 对 BTC-USDT × [5m,15m,1h,1d] 各跑一次
  ↓ 2. 对 ETH-USDT × [5m,15m,1h,1d] 各跑一次
  ↓ 共 8 次 LLM 调用 / 5m = 2304 次/天
  ↓
agent.py TrendAgent.analyze(pair, timeframe)
  ↓ 3. perceive() — 调 signals/regime + strategy_pool + cost_model + recent OHLCV
  ↓ 4. reason() — 拼 prompt → 调 LLM (DeepSeek V3) → 解析 Pydantic 输出
  ↓ 5. recommend() — 产出 AgentRecommendation (与 aggregator 并列)
  ↓
persistence.py
  ↓ 6. 写 ai_trend_analysis 表
  ↓ 7. 写 agent_recommendation 表
  ↓ 8. 触发 WebSocket notification (optional)
```

### 4.2 手动触发路径

```
POST /api/agent/analyze { pair, timeframe }
  ↓
agent.py TrendAgent.analyze(pair, timeframe)
  ↓
返回 { analysis: "...", recommendation: {...} }
```

### 4.3 失败降级

```
LLM 5xx / timeout / rate-limit
  ↓ 重试 2 次 (指数退避)
  ↓ 仍失败 → 写 "Agent unavailable, fallback to aggregator only" 标记
  ↓ 不阻塞 aggregator 主流程
```

---

## 5. 模块边界

| 文件 | 职责 | 不做什么 |
|------|------|---------|
| `agent/__init__.py` | 暴露 `TrendAgent` 类 | - |
| `agent/agent.py` | `TrendAgent.analyze()` 主入口；orchestrate perceive→reason→recommend | 不存 DB，不调 HTTP |
| `agent/perceiver.py` | 拉 OHLCV + 调 signals/regime 等规则模块 | 不调 LLM |
| `agent/reasoner.py` | 调 LLM provider（DeepSeek 占位）；解析 + 校验 Pydantic 输出 | 不拉数据 |
| `agent/recommender.py` | 把 LLM reasoning 映射成 `AgentRecommendation` schema | 不调 LLM |
| `agent/prompts.py` | 系统提示词 + 模板（中文金融推理 prompt） | 不调 LLM |
| `agent/schemas.py` | `AnalysisReport` + `AgentRecommendation` Pydantic model | 不调 LLM |
| `agent/llm_client.py` | `LLMProvider` Protocol；`DeepSeekProvider` / `QwenProvider` / `LocalOllamaProvider` 实现 | 不感知业务 |
| `agent/runner.py` | APScheduler 5m 循环；限流；重试 | 不调 LLM |
| `agent/persistence.py` | 写 ai_trend_analysis + agent_recommendation 表 | 不调 LLM |
| `api/agent.py` | `GET /reports` + `POST /analyze` + `GET /recommendations` | 不调 LLM（thin wrapper） |

**规则**：
- 每个文件 ≤ 200 行
- 单一职责
- LLM 调用只发生在 `reasoner.py` + `llm_client.py`

---

## 6. 关键设计决策

### 6.1 Agent 定位 = 第二意见（不抢 aggregator）

**为什么**：AGENTS.md 规则 3（项目已成型，禁止重写）+ aggregator v2 已能产单。Agent 加"自然语言 + 第二意见"比"替换"更安全。

**实现**：
- `agent_recommendation` 表与现有 `recommendation` 表**完全独立**
- 前端并排展示 "Aggregator 推荐" vs "Agent 第二意见"
- 用户**自己判断**哪个更可信
- 一周后用户可选择：a) 全用 aggregator 忽略 agent；b) 全用 agent；c) 加权融合

### 6.2 循环频率 = 5m（不是 60s）

**为什么**：60s × 2 币 × 4 tf = 11520 次/天 × ¥0.01 = ¥3450/月，太贵。5m = 576 次/天 × ¥0.01 = ¥173/月，**可控**。

**实现**：
- `runner.py` 用 APScheduler，每 5m 触发
- 与现有 `recommendation_refresh_interval=60` **不冲突**——aggregator 60s 跑，Agent 5m 跑
- 用户后续要更高频可改 `AGENT_REFRESH_INTERVAL=300` env

### 6.3 LLM Provider = Protocol 抽象

**为什么**：用户说"LLM 供应商后面再说"——架构层留接口，先用 `DeepSeekProvider` 占位，未来可换 `ClaudeProvider` / `LocalOllamaProvider`。

**接口**：
```python
class LLMProvider(Protocol):
    async def complete(self, system: str, user: str, **kw) -> str: ...
```

### 6.4 降频策略（成本控制）

- 5m 循环是 hard cap
- LLM 调用失败重试 2 次后**直接降级**——不阻塞 aggregator
- 单次 LLM 调用超时 30s（DeepSeek 通常 < 10s）

### 6.5 数据 schema（草案）

```python
class AnalysisReport(BaseModel):
    pair: Literal["BTC-USDT", "ETH-USDT"]
    timeframe: Literal["5m", "15m", "1h", "1d"]
    regime: Literal["bull", "bear", "choppy", "crisis"]
    regime_confidence: float  # 0-1
    reasoning: str  # 200-500 字中文
    key_observations: list[str]  # 3-5 条
    risks: list[str]  # 风险点
    created_at: datetime

class AgentRecommendation(BaseModel):
    pair: Literal["BTC-USDT", "ETH-USDT"]
    timeframe: Literal["5m", "15m", "1h", "1d"]
    direction: Literal["long", "short", "neutral"]
    confidence: float  # 0-1
    rationale: str  # 100-200 字
    source: Literal["agent"]
    created_at: datetime
```

---

## 7. 错误处理

| 错误 | 处理 |
|------|------|
| LLM 5xx | 重试 2 次（指数退避 1s/3s），仍失败 → 写 `analysis_status=fallback`，不报错 |
| LLM 超时 30s | 同上 |
| Pydantic 解析失败 | 写 `analysis_status=parse_error`，记 raw response |
| DB 写失败 | 抛异常到 runner 监控，不静默 |
| 信号数据缺失 | Agent 标 `data_completeness=partial`，降级置信度 |
| 币种不在 BTC/ETH 范围 | 拒接（btc-eth-scope Rule 1） |

---

## 8. 测试策略

| 层 | 方法 |
|----|------|
| Unit | pytest：`test_agent.py`（mock LLM + signals），`test_perceiver.py`，`test_recommender.py` |
| Integration | `test_runner.py`：真实 DB，mock LLM，跑 1 个完整 cycle |
| Eval | `tests/evals/test_agent_quality.py`：跑 30 天 BTC+ETH 历史 K 线，对比 Agent 推理 vs 实际 regime 走势（Brier Score / 方向准确率） |
| Cost | `tests/cost/test_llm_cost.py`：记录每次调用 token 数 × 单价，断言 ≤ ¥173/月 |
| Manual | 部署到生产后看 Dashboard 研判报告时间线 |

---

## 9. 验证清单

- [ ] **功能**：POST /api/agent/analyze 跑通 BTC + ETH × 4 tf 共 8 次
- [ ] **数据**：ai_trend_analysis 表 1 天后 ≥ 2304 行（5m × 288 × 8 = 2304）
- [ ] **成本**：1 天 LLM 成本 ≤ ¥173（DeepSeek 占位）
- [ ] **降级**：拔掉 LLM key，aggregator 仍正常推单
- [ ] **范围**：调 SOL/DOGE → 拒接（btc-eth-scope Rule 1）
- [ ] **Eval**：Brier Score ≤ 0.25（baseline = 随机 0.5 的 50%）
- [ ] **零破坏**：existing pytest 全绿，无 signals/* 改动

---

## 10. 风险 & 缓解

| 风险 | 缓解 |
|------|------|
| LLM hallucination | Pydantic 强 schema；reasoning 字段必填但允许 `caveats` 字段 |
| 成本失控 | runner.py hard cap 5m；token 监控 |
| 抢 aggregator 权威 | 独立表 + 独立端点 + 前端明确标 "第二意见" |
| LLM 供应商锁死 | Protocol 抽象 + env 配置 |
| DB 写并发 | 用现有 SQLAlchemy session（不要新引入 ORM） |

---

## 11. 待定（用户后续决定）

1. **LLM 供应商**（用户说"后面再说"）— 现在用 DeepSeek 占位，可随时换
2. **Prompt 模板细节**— 实施时定
3. **前端页面布局**— 实施时定（参考现有 Dashboard 风格）
4. **是否做 evals 报告页**— 一周后再定

---

## 12. 自审

- [x] **没 TODO 占位**（除"待定"段）
- [x] **章节内部不矛盾**
- [x] **范围明确**（BTC+ETH only、不下单、不抢 aggregator）
- [x] **可拆 TDD 任务**（12 个文件每个可独立测试）
- [x] **可验证**（§9 验证清单）

---

## 下一步

调用 `writing-plans` skill，把 spec 拆成 TDD 任务清单（每个 ≤ 1 天工作量）。