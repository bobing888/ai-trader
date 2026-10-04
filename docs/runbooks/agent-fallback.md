# Agent 降级 / 故障 Runbook

> 适用: Trend Analysis Agent 后台推理服务（5m 循环、BTC + ETH × 4 tf）
> 触发: 监控告警 / 用户反馈 / API 返回异常

## 1. 快速诊断

### 1.1 查最近 5 条 LLM 报告（看状态分布）

```bash
sqlite3 backend/dev.db "
SELECT pair, timeframe, analysis_status, created_at
FROM ai_trend_analysis
ORDER BY created_at DESC
LIMIT 10;"
```

**正常**: SUCCESS / FALLBACK 混合，5m cycle 平均 1 行
**异常**: 全 PARSE_ERROR 或全 DATA_INCOMPLETE

### 1.2 查当前后端日志

```bash
ssh kbkkk-prod 'tail -500 /opt/ai-trader-backend.log | grep -E "agent_runner|FALLBACK" | tail -30'
```

### 1.3 查 LLM 调用统计

```bash
sqlite3 backend/dev.db "
SELECT
  analysis_status,
  COUNT(*) as n,
  MAX(created_at) as last
FROM ai_trend_analysis
WHERE created_at > datetime('now', '-1 day')
GROUP BY analysis_status;"
```

## 2. 常见故障 & 处理

### 2.1 全部 FALLBACK（LLM 调不通）

**症状**: 最近 30 条全是 `FALLBACK`

**原因**:
- DEEPSEEK_API_KEY 未配置 / 过期
- DeepSeek 服务宕机
- 网络问题（kbkkk-prod → DeepSeek API）

**处理**:
1. 查配置: `ssh kbkkk-prod 'grep DEEPSEEK_API_KEY /opt/ai-trader/.env'`
2. 测连通: `ssh kbkkk-prod 'curl -H "Authorization: Bearer $AI_TRADER_DEEPSEEK_API_KEY" https://api.deepseek.com/v1/models'`
3. 重启服务: `ssh kbkkk-prod 'systemctl restart ai-trader-backend'`

**降级策略**: Agent 全 FALLBACK 不影响 rule-based `aggregator.py`，系统照常跑。

### 2.2 大量 PARSE_ERROR（LLM 返回非 JSON）

**症状**: `analysis_status = 'parse_error'`

**原因**: LLM 返回了非 JSON 文本 / 截断 / 缺字段

**处理**:
1. 抽样: `sqlite3 dev.db "SELECT raw_llm_response FROM ai_trend_analysis WHERE analysis_status='parse_error' LIMIT 3" | head -100`
2. 改 prompt: `backend/app/agent/prompts.py` 加强 JSON schema 说明
3. 跑 reasoner tests: `cd backend && ./.venv/bin/python -m pytest tests/agent/test_reasoner.py`

### 2.3 DATA_INCOMPLETE（OKX / 缺数据）

**症状**: `analysis_status = 'data_incomplete'`

**原因**: OKX 限流 / 网络 / 异常 K 线

**处理**:
1. 查 Perceiver 日志: `grep "data_completeness" /opt/ai-trader-backend.log | tail -20`
2. 手动跑 OKX health check: `curl -s "https://www.okx.com/api/v5/market/candles?instId=BTC-USDT&bar=1h&limit=5" | head -50`

### 2.4 后台循环挂掉

**症状**: `last_analyze_at` > 10 min 之前

**处理**:
1. `ssh kbkkk-prod 'systemctl status ai-trader-backend'`
2. `ssh kbkkk-prod 'journalctl -u ai-trader-backend --since "1 hour ago" | grep -E "agent_runner" | tail -20'`
3. 重启: `systemctl restart ai-trader-backend`
4. 验证: `curl -s http://kbkkk.com/api/agent/reports?pair=BTC-USDT | jq '.items[0].created_at'`

## 3. 配置调整

### 3.1 关掉 Agent（不推荐，但紧急时可用）

```bash
ssh kbkkk-prod '
  # 在 .env 加 AGENT_ENABLED=false（需后端支持）
  # 或者直接停服务
  systemctl stop ai-trader-backend
'
```

注: 当前的 settings 没有 AGENT_ENABLED 开关 — 必须 hotpatch 或重启。

### 3.2 调小 cycle（省钱 / 限流期）

```bash
# .env 加: AI_TRADER_AGENT_REFRESH_INTERVAL=900  (15m)
ssh kbkkk-prod 'echo "AI_TRADER_AGENT_REFRESH_INTERVAL=900" >> /opt/ai-trader/.env && systemctl restart ai-trader-backend'
```

### 3.3 调大 timeout（慢 LLM 响应）

```bash
# .env: AI_TRADER_AGENT_REASONING_TIMEOUT=60
```

## 4. Quality 评估

### 4.1 跑 Brier Score 测试

```bash
cd backend
./.venv/bin/python -m pytest tests/agent/test_agent_quality.py -v
```

### 4.2 真实 30 天回测（需历史数据 + DEEPSEEK_API_KEY）

```python
# scripts/agent_backtest_30d.py (待写)
# 1. 拉 BTC/ETH 30 天 1h K 线
# 2. 对每根 K 线调 Reasoner.predict()（模拟当时信息）
# 3. 比对 24h 后实际方向
# 4. 算 Brier Score + direction accuracy
# 5. 报告 quality 是否达 spec §9 目标（Brier ≤ 0.25, acc ≥ 60%）
```

## 5. 紧急回滚

如果 Agent 改动导致生产不可用:

1. `git revert <bad-commit-sha>`
2. `git push origin main` → 触发自动部署
3. 验证: `curl -s http://kbkkk.com/api/health`

**注**: 自动部署仅 ai-trader 仓库（bobing888/ai-trader）。详见 `deploy-dyddd/SKILL.md`。

## 6. 联系 / 升级

| 级别 | 症状 | 处理 |
|------|------|------|
| P3 | 部分 FALLBACK，rule-based 工作 | 观察 30 min，自动恢复 |
| P2 | 30 min 内全 FALLBACK | 检查 DEEPSEEK_API_KEY + 网络 |
| P1 | 后台循环挂 / DB 写入失败 | 重启服务 + 查日志 |
| P0 | 服务整个不可用 | 停 agent、查后端 crash 日志、回滚 PR |
