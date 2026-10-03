# Trend Analysis Agent Implementation Plan

> **For implementers:** REQUIRED SUB-SKILL: Use subagent-driven-development (推荐) 或 executing-plans 来逐 task 实施本 plan。Step 用 checkbox (`- [ ]`) 标记。

**Goal:** 在 ai-trader 加"自然语言研判 Agent"层（第二意见），不改 signals/*，不下单。

**Architecture:** 新模块 `backend/app/agent/` (10 文件) + 新 API 端点 `/api/agent/*` + 新前端页 `TrendAgentPage.tsx`。Agent = 拉 signals 数据 + 调 LLM (DeepSeek 占位) + 写 ai_trend_analysis 表 + 写 agent_recommendation 表。**5m 循环**。

**Tech Stack:** Python 3.14 / FastAPI / Pydantic v2 / SQLAlchemy / APScheduler / httpx (调 DeepSeek) / pytest

**Spec:** `docs/superpowers/specs/2026-10-03-trend-analysis-agent.md`

## Global Constraints

- 币种限制：只 BTC-USDT + ETH-USDT（btc-eth-scope Rule 1）
- 不下任何交易单（0 place_order）
- 5m 循环（不要 60s）
- 不改 `signals/*` 9 个模块
- 项目已成型（AGENTS.md 规则 3），禁止重写已有逻辑
- LLM provider 用 Protocol 抽象（DeepSeek 占位，可换）
- 中文 prompt（金融推理）
- pytest 必须全绿
- 仅 production-safe 操作（不删数据 / 不动生产配置）

## Review Focus

| 输入类 | 预期行为 | Owning task |
|--------|----------|-------------|
| LLM 5xx / timeout | 重试 2 次后降级，不阻塞 aggregator | Task 6 (error handling) |
| 币种不在 BTC/ETH | 拒接（btc-eth-scope Rule 1） | Task 2 (schemas) |
| LLM 返回非 Pydantic 合规 | 标 `analysis_status=parse_error` 记 raw | Task 4 (scripts schemas) |
| signals 数据缺失 | 标 `data_completeness=partial` | Task 3 (perceiver) |
| DB 写并发冲突 | 用现有 SQLAlchemy session，不新引入 ORM | Task 5 (persistence) |

---

## Task 1: 项目骨架 + 目录

**Files:**
- Create: `backend/app/agent/__init__.py`
- Create: `backend/app/agent/schemas.py`（先建空 schema，给后续 task）
- Test: `tests/agent/__init__.py`
- Test: `tests/agent/test_schemas.py`

**Interfaces:**
- Consumes: 无
- Produces: 空 `agent/` 包 + `agent_recommendation` Pydantic 占位 + `AnalysisReport` 占位

- [ ] **Step 1: 写 failing test** — `tests/agent/test_schemas.py::test_analysis_report_importable`
- [ ] **Step 2: 跑测试看 fail** — `pytest tests/agent/test_schemas.py -v` → 预期 FAIL（`agent` 模块不存在）
- [ ] **Step 3: 实现** — 建 `backend/app/agent/__init__.py`（空），建 `schemas.py` 写 `AnalysisReport` + `AgentRecommendation`（先 only the type + class definitions，按 spec §6.5 草案）
- [ ] **Step 4: 跑测试看 pass** — `pytest tests/agent/test_schemas.py -v` → 预期 PASS
- [ ] **Step 5: Commit** — `git add backend/app/agent/ tests/agent/ && git commit -m "feat(agent): scaffold agent module + schemas"`

## Task 2: 强化 schemas（加 btc-eth-scope 校验 + Literal 限制）

**Files:**
- Modify: `backend/app/agent/schemas.py`
- Test: `tests/agent/test_schemas.py`（加新 test）

**Interfaces:**
- Consumes: Task 1 schemas
- Produces: 强化版 schemas（`pair` 必须是 BTC-USDT 或 ETH-USDT；`timeframe` 必须是 5m/15m/1h/1d）

- [ ] **Step 1: 写 failing test** — `test_pair_must_be_btc_or_eth`（传 SOL 应抛 ValidationError）
- [ ] **Step 2: 跑测试看 fail** — 预期 FAIL（schema 暂未限制）
- [ ] **Step 3: 实现** — `schemas.py` 用 `Literal["BTC-USDT", "ETH-USDT"]` + `Literal["5m", "15m", "1h", "1d"]`，加 `field_validator` 强制
- [ ] **Step 4: 跑测试看 pass** — 预期 PASS
- [ ] **Step 5: Commit** — `git commit -m "feat(agent): enforce BTC/ETH scope + timeframe Literal"`

## Task 3: Perceiver（拉数据）

**Files:**
- Create: `backend/app/agent/perceiver.py`
- Test: `tests/agent/test_perceiver.py`

**Interfaces:**
- Consumes: `AnalysisReport` 字段（pair, timeframe）
- Produces: `PerceivedContext` dataclass：含 `ohlcv_last_100`, `regime_state`, `strategy_signals`, `cost_model_output`, `data_completeness`（0-1）

- [ ] **Step 1: 写 failing test** — `test_perceive_returns_ohlcv_for_btc_1h`（mock signals/regime）
- [ ] **Step 2: 跑测试看 fail** — 预期 FAIL
- [ ] **Step 3: 实现** — `perceiver.py` 写 `Perceiver` 类，调 `signals/regime.py` + `signals/strategy_pool.py` + `signals/cost_model.py` + 调 `data/okx.py` 拉最近 100 根 K 线。**只读** signals/*，**不改**。
- [ ] **Step 4: 跑测试看 pass** — 预期 PASS
- [ ] **Step 5: Commit** — `git commit -m "feat(agent): perceiver module"`

## Task 4: Reasoner（调 LLM + 解析）

**Files:**
- Create: `backend/app/agent/llm_client.py`
- Create: `backend/app/agent/prompts.py`
- Create: `backend/app/agent/reasoner.py`
- Test: `tests/agent/test_reasoner.py`（mock httpx）

**Interfaces:**
- Consumes: `PerceivedContext`（来自 Task 3）
- Produces: `AnalysisReport`（来自 Task 1/2）

- [ ] **Step 1: 写 failing test** — `test_reasoner_returns_analysis_report_with_mocked_llm`
- [ ] **Step 2: 跑测试看 fail** — 预期 FAIL
- [ ] **Step 3: 实现** — `llm_client.py` 写 `LLMProvider` Protocol + `DeepSeekProvider`（占位，API key 从 env `DEEPSEEK_API_KEY` 读）；`prompts.py` 写中文金融推理系统提示词模板；`reasoner.py` 写 `Reasoner` 类，组装 prompt → 调 DeepSeek → 解析为 `AnalysisReport`
- [ ] **Step 4: 跑测试看 pass** — 预期 PASS（mock 返回的 Pydantic 合规响应）
- [ ] **Step 5: Commit** — `git commit -m "feat(agent): reasoner with DeepSeek provider"`

## Task 5: Persistence（写 DB）

**Files:**
- Create: `backend/app/agent/persistence.py`
- Create: 新 Alembic migration：`backend/alembic/versions/XXXX_add_agent_tables.py`
- Test: `tests/agent/test_persistence.py`

**Interfaces:**
- Consumes: `AnalysisReport` + `AgentRecommendation`
- Produces: 写 `ai_trend_analysis` 表 + `agent_recommendation` 表（用现有 SQLAlchemy session）

- [ ] **Step 1: 写 failing test** — `test_persistence_writes_analysis_to_db`
- [ ] **Step 2: 跑测试看 fail** — 预期 FAIL
- [ ] **Step 3: 实现** — `persistence.py` 写 `AnalysisRepository` + `RecommendationRepository`；Alembic migration 加 `ai_trend_analysis` (id, pair, timeframe, regime, regime_confidence, reasoning, key_observations_json, risks_json, analysis_status, created_at) + `agent_recommendation` (id, pair, timeframe, direction, confidence, rationale, source, created_at)
- [ ] **Step 4: 跑测试看 pass** — 预期 PASS（用 in-memory SQLite）
- [ ] **Step 5: Commit** — `git commit -m "feat(agent): persistence + migration"`

## Task 6: Agent 主类 + 错误处理

**Files:**
- Create: `backend/app/agent/agent.py`
- Test: `tests/agent/test_agent.py`

**Interfaces:**
- Consumes: `Perceiver` + `Reasoner` + `Persistence`（来自 Task 3/4/5）
- Produces: `TrendAgent.analyze(pair, timeframe) → AnalysisReport`

- [ ] **Step 1: 写 failing test** — `test_agent_analyze_succeeds_with_mocked_deps` + `test_agent_fallback_when_llm_fails`
- [ ] **Step 2: 跑测试看 fail** — 预期 FAIL
- [ ] **Step 3: 实现** — `agent.py` 写 `TrendAgent.analyze()` orchestrate perceive→reason→persist；LLM 失败时重试 2 次（指数退避）后标 `analysis_status=fallback`；用 `asyncio.TimeoutError` 处理 30s 超时
- [ ] **Step 4: 跑测试看 pass** — 预期 PASS
- [ ] **Step 5: Commit** — `git commit -m "feat(agent): TrendAgent with retry + fallback"`

## Task 7: Runner（5m 循环调度）

**Files:**
- Create: `backend/app/agent/runner.py`
- Test: `tests/agent/test_runner.py`

**Interfaces:**
- Consumes: `TrendAgent`（来自 Task 6）
- Produces: 后台调度器，每 5m 触发 BTC + ETH × 4 timeframe 共 8 次

- [ ] **Step 1: 写 failing test** — `test_runner_schedules_8_calls_per_5m_cycle`（用 mock agent）
- [ ] **Step 2: 跑测试看 fail** — 预期 FAIL
- [ ] **Step 3: 实现** — `runner.py` 用 APScheduler `AsyncIOScheduler`，每 5m 触发 `_run_cycle()`；cycle 内 `asyncio.gather()` 跑 8 个 analyze；不阻塞 aggregator 主循环
- [ ] **Step 4: 跑测试看 pass** — 预期 PASS
- [ ] **Step 5: Commit** — `git commit -m "feat(agent): APScheduler runner with 5m cycle"`

## Task 8: API 端点

**Files:**
- Create: `backend/app/api/agent.py`
- Modify: `backend/app/main.py`（注册 router）
- Test: `tests/api/test_agent_api.py`

**Interfaces:**
- Consumes: HTTP 请求
- Produces:
  - `GET /api/agent/reports?pair=BTC-USDT&timeframe=1h&limit=20` → `list[AnalysisReport]`
  - `POST /api/agent/analyze { pair, timeframe }` → `AnalysisReport`
  - `GET /api/agent/recommendations?pair=BTC-USDT&timeframe=1h` → `list[AgentRecommendation]`

- [ ] **Step 1: 写 failing test** — `test_api_get_reports_returns_200` + `test_api_post_analyze_runs_agent`
- [ ] **Step 2: 跑测试看 fail** — 预期 FAIL
- [ ] **Step 3: 实现** — `api/agent.py` 写 3 个端点；`main.py` 加 `app.include_router(agent.router, prefix="/api/agent", tags=["agent"])`
- [ ] **Step 4: 跑测试看 pass** — 预期 PASS（用 TestClient + mock agent）
- [ ] **Step 5: Commit** — `git commit -m "feat(api): agent endpoints"`

## Task 9: Runner 接入主程序

**Files:**
- Modify: `backend/app/main.py`（启动时启动 scheduler）
- Test: `tests/integration/test_app_starts_with_agent_runner.py`

**Interfaces:**
- Consumes: FastAPI lifespan
- Produces: 应用启动时启动 APScheduler，关闭时停止

- [ ] **Step 1: 写 failing test** — `test_lifespan_starts_agent_scheduler`
- [ ] **Step 2: 跑测试看 fail** — 预期 FAIL
- [ ] **Step 3: 实现** — `main.py` lifespan 上下文里 `runner.start()` + `runner.shutdown()`
- [ ] **Step 4: 跑测试看 pass** — 预期 PASS
- [ ] **Step 5: Commit** — `git commit -m "feat: wire agent runner into FastAPI lifespan"`

## Task 10: 前端页面

**Files:**
- Create: `frontend/src/pages/TrendAgentPage.tsx`
- Modify: `frontend/src/App.tsx`（加路由）
- Modify: `frontend/src/api/client.ts`（加 agent API）
- Test: `frontend/src/pages/__tests__/TrendAgentPage.test.tsx`（如果项目有 vitest）

**Interfaces:**
- Consumes: `GET /api/agent/reports` + `GET /api/agent/recommendations`
- Produces: 研判报告时间线 + 第二意见 vs aggregator 对比

- [ ] **Step 1: 写 failing test** — `test_trend_agent_page_renders_reports`
- [ ] **Step 2: 跑测试看 fail** — 预期 FAIL
- [ ] **Step 3: 实现** — `TrendAgentPage.tsx` 用现有 React + Tailwind 风格，调 API；App.tsx 加 `/agent` 路由；client.ts 加 `getAgentReports` + `getAgentRecommendations`
- [ ] **Step 4: 跑测试看 pass** — 预期 PASS
- [ ] **Step 5: Commit** — `git commit -m "feat(frontend): trend agent page"`

## Task 11: 集成测试 + 评估

**Files:**
- Create: `tests/integration/test_agent_e2e.py`
- Create: `tests/evals/test_agent_quality.py`
- Create: `tests/cost/test_llm_cost.py`

**Interfaces:**
- Consumes: 整个 agent 子系统
- Produces: 端到端测试 + 质量评估 + 成本监控

- [ ] **Step 1: 写 failing test** — 跑完整 cycle（mock LLM） → 验证 DB 写入 + API 响应
- [ ] **Step 2: 跑测试看 fail** — 预期 FAIL（首次跑）
- [ ] **Step 3: 实现** — `test_agent_e2e.py` 跑真实 main.py + 真实 DB（test fixture）+ mock LLM；`test_agent_quality.py` 跑 BTC/ETH 30 天历史 K 线（用 fixtures/btc_eth_30d.csv），断言 Brier Score ≤ 0.25 + direction accuracy ≥ 60%；`test_llm_cost.py` mock token count，断言 1 天 ≤ ¥173
- [ ] **Step 4: 跑测试看 pass** — 预期 PASS
- [ ] **Step 5: Commit** — `git commit -m "test(agent): e2e + quality + cost"`

## Task 12: 部署 + 监控

**Files:**
- Modify: `backend/app/config.py`（加 `DEEPSEEK_API_KEY` + `AGENT_REFRESH_INTERVAL`）
- Create: `docs/runbooks/agent-fallback.md`

**Interfaces:**
- Consumes: 环境变量
- Produces: 部署文档 + 故障排查手册

- [ ] **Step 1: 写 failing test** — `test_config_loads_deepseek_api_key_from_env`
- [ ] **Step 2: 跑测试看 fail** — 预期 FAIL
- [ ] **Step 3: 实现** — `config.py` 加 `deepseek_api_key: str = ""` + `agent_refresh_interval: int = 300`；`runbook` 写 fallback / retry / parse_error 排查步骤
- [ ] **Step 4: 跑测试看 pass** — 预期 PASS
- [ ] **Step 5: Commit** — `git commit -m "feat(agent): config + runbook"`

---

## Self-Review（写完 plan 后跑）

### 1. Spec coverage
- [x] 目标（spec §1）→ Task 6 (Agent 主类)
- [x] 不做什么（spec §2）→ Task 2 schemas Literal 限制 + Task 6 fallback
- [x] 架构（spec §3）→ Task 1-10 每个模块
- [x] 数据流（spec §4）→ Task 7 runner
- [x] 模块边界（spec §5）→ Task 3/4/5
- [x] 关键设计（spec §6）→ Task 2 (BTC/ETH) + Task 4 (LLM Protocol) + Task 7 (5m 循环)
- [x] 错误处理（spec §7）→ Task 6 (LLM retry/fallback)
- [x] 测试策略（spec §8）→ Task 11
- [x] 验证清单（spec §9）→ Task 11

### 2. Step scan
- 每个 step 实施员只能写出一个合理实现 ✓

### 3. Type consistency
- `AnalysisReport` 全 plan 用同一个名 ✓
- `AgentRecommendation` 全 plan 用同一个名 ✓
- `TrendAgent.analyze()` Task 6 → Task 7 → Task 8 ✓

### 4. Review Focus
- LLM 5xx / timeout → Task 6 ✓
- 币种不在 BTC/ETH → Task 2 ✓
- LLM 返回非 Pydantic 合规 → Task 6 (PydanticValidationError 捕获) ✓
- signals 数据缺失 → Task 3 (`data_completeness` 字段) ✓
- DB 写并发 → Task 5（用现有 SQLAlchemy session）✓

### 5. Proportion
- Plan 12 tasks，spec 12 章节，1:1 合理 ✓

---

## 实施方式选哪个

按 writing-plans skill 要求：
- **Subagent-driven**：每个 task 派一个新 subagent + 新 review 在 task 间，最彻底
- **Native**：本会话我直接实施所有 task，最快最便宜

**我推荐 Native**——因为：
1. 12 个 task 中前 7 个是连贯的 Python 模块（agent 内部强类型依赖），subagent 间切会丢上下文
2. 你已授权"自主执行 + 自己决定"，Native 最快
3. Task 8/9 是集成点（API + main.py 接入），必须看到前 7 个跑起来才能接

如果你要 subagent-driven（最彻底），告诉我——我改成每个 task 派一个 subagent。

---

**Plan 完成，保存在 `docs/superpowers/plans/2026-10-03-trend-analysis-agent.md`。**