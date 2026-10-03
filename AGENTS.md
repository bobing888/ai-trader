# AGENTS.md

项目级 agent 协作规则。所有 assistant（包括 Cursor、Claude Code 等）必须遵守。

> **🚨 用户授权备忘 #1（2026-09-14 23:58）**：用户授权**所有非破坏性命令**自主执行，不许问、不许弹"需要 Run 吗？"、不许弹"重试吗？"、不许弹"继续吗？"。命令失败自己改路径/权限/参数继续，最多 3 次自纠后回报。详见**规则 7**。
>
> **🚨 用户授权备忘 #2（2026-09-23 21:11，最终强授权）**：用户再次明确表态——**「执行命令时，我都默认允许，不要再问我是否允许，因为我不能一直盯着给你点允许」**。这一条是**最高优先级**，覆盖下面规则 7 中"必须问用户"的有限例外，只要不属于下面"绝对红线"四类**破坏性 / 不可逆 / 付费副作用 / 阻塞他人**操作，**一律自主执行**。详见**规则 7**。
>
> **🚨 Cursor Shell 操作备忘（2026-09-15 00:06）**：跑耗时命令（npm install / build / docker pull 等）必须用 `block_until_ms: 0` 后台跑 + 自己轮询日志，**绝对不要**用 `block_until_ms > 0` 等命令结束，否则 Cursor 会弹"还在跑/要不要继续"的对话框骚扰用户。
>
> **🚨 多任务派单备忘（2026-09-26）**：用户授权「对话里提到多个 bug/新需求时，每个单独起一个子 agent，从主分支切一个干净分支来修，自己解决冲突后合入 main」。落地详见 `.cursor/skills/multi-task-dispatch/SKILL.md`；单任务流程仍走 `branch-management`。
>
> **🚨 合入即部署备忘（2026-09-27 16:31）**：用户要求**「每次合入到主分支的代码，都自动部署到生产，因为我要查看最新的效果」**。落地详见**规则 9**。

## 入口规则：任务分类器（强制第一跳）

**每个对话开始时，agent 必须先阅读并执行 `.cursor/skills/task-classifier/SKILL.md` 的分类流程。**

```
🔍 任务分类 → [Tier] — [Route]
- 任务：[一句话描述]
- 分类依据：[为什么是 Tier N]
- 路线：[具体 skill + 顺序]
```

不允许在分类完成前：
- 读文件
- 写代码
- 提出修复方案
- 说"我先看看"

---

## 规则 1：最小必要流程

每个 Tier 都有明确的最少步骤：

| Tier | 最少步骤 |
|------|---------|
| Tier 1（单文件改） | 直接改 + 自测（curl/截图） |
| Tier 2（3 文件内） | 根因分析 + 改 + 验证 |
| Tier 3（新功能/多组件） | 完整 brainstorming + plan + 验证 |

**禁止跳过步骤。**
- Tier 2 禁止"先改后测"（必须先有验证方式）
- Tier 3 禁止"跳过 brainstorming 直接开干"
- Bug 禁止"我知道原因"直接修（必须走 systematic-debugging）

---

## 规则 2：无测试不声称完成

**每个改动必须有验证方式，验证方式必须在改动之前想清楚。**

验证方式优先级：
1. **单元测试**（pytest / vitest）— 最可靠
2. **集成测试**（curl / API call）— API 改动必须用
3. **手动验证**（截图）— UI 改动必须用，且每场景一张新鲜截图
4. **DB 查询**（sqlite3）— 数据层改动必须用

**无验证方式的改动 = 不知道它是否工作 = 不完成**

---

## 规则 3：已成型的项目 — 在原代码上增量优化，不允许重写

**默认前提：** 本项目（ai-trader）已经成型、已经在产线上跑、已经有完整 happy path。**严禁把它当"半成品"重写。**

**正确做法：**
- 在现有代码上做**增量修改 / 增强 / 优化 / 自进化**
- 新功能 → 直接加在新文件或新模块里，**不删**已有代码（除非显式废弃）
- 旧的实现可以作为参考/兼容路径保留，但**不允许"新旧并存"导致同一概念两套实现**——需要让用户明确选择
- **优化策略**：借鉴 GitHub 上成熟参考实现的 feature / pattern（见规则 8），合并进现有代码

**禁止：**
- ❌ 把已成型项目当"半成品"重新搭骨架
- ❌ 删除正在使用的功能（除非用户明确说废弃）
- ❌ 用"重写"代替"演进"
- ❌ "新旧并存"——同一概念维护两套实现

**触发"重写"决策的**唯一**条件（必须先与用户确认）：**
- 项目无法跑通最小可用流程（启动 / 一次完整请求 / 端到端 happy path）
- 架构存在明显前后矛盾（如前端 `/app/` 前缀但后端没挂对应 mount）
- 代码中大量 TODO / 占位符 / 未对接的接口
- 同一概念存在两套以上并行实现

如果触发以上条件 → 先与用户确认意图 → 用户同意后才重写。

---

## 规则 4：场景覆盖验证（防"半成品"反复修）

**触发条件：** 任何改动影响 ≥ 2 个用户可见状态时（市场类型/时间周期/角色/路由/空/非空/桌面 等）

**强制流程：**

1. **改之前**：列出 `场景覆盖矩阵`
2. **改完之后**：每个场景必须有 fresh evidence
3. **声明完成前**：必须按以下格式报告：

```
场景覆盖完成：
- 总计 N 个场景
- M 个通过（每行带证据）
- K 个失败/跳过（原因）
```

**绝对禁止：**
- "应该都好了" / "应该没问题" / "剩下没测"
- 用同一张截图证明多个不同场景
- 只测期货就说"现货也一样"

---

## 规则 5：Bug 必须走 systematic-debugging

**禁止在根因不明时提出修复方案。**

路径：systematic-debugging → Phase 1（根因）→ Phase 2（模式）→ Phase 3（假设）→ Phase 4（修复）

3 次修复失败 → 停止并质疑架构。

---

## 规则 6：响应语言

- 默认使用简体中文
- 代码、命令、路径保持英文

---

## 规则 7：自主执行 Run，不打断用户

**用户已经授权（2026-09-14 23:58 + 2026-09-23 21:11 二次确认）：所有非破坏性的 build / run / install / test / deploy / ssh / docker / git / curl / grep / find / cat / ls / ps / kill / killall 类命令，由 agent 自主执行，不要每条都问，也不要每条都点击 Run/确认/重试。**

适用范围（**最大范围**——除"绝对红线"以外全部覆盖）：
- ✅ **可以自主执行（构建/部署/服务）**：build、test、run、install、deploy、ssh、rsync、git commit、git push（非 --force）、git pull、git fetch、docker compose、curl 自测、npm/yarn/pip/python 直接调用、npm install、pip install、apt-get install、brew install、make、cmake
- ✅ **可以自主执行（文件操作）**：ls、cat、head、tail、find、grep、rg、cp、mv、mkdir、touch、chmod、stat、du、df、tree、jq
- ✅ **可以自主执行（进程/网络）**：ps、top、kill、killall（普通进程）、lsof、netstat、ping、nslookup、curl、wget
- ✅ **可以自主执行（容器）**：docker ps、docker logs、docker exec、docker inspect、docker stats、docker restart、docker compose up/down/restart/logs、`docker stop`、`docker rm` 单容器（**非 `docker system prune` / `docker volume rm`**）
- ✅ **可以自主执行（GitHub 调研，用户已授权免确认）**：`gh search repos` / `gh search code` / `gh repo view` / `gh repo clone` / `WebFetch github.com` / `git clone github.com` / `WebSearch "github.com/..."` 等所有 GitHub 资源搜索与代码拉取操作
  - 触发条件：用户已明确授权「之后每次从 GitHub 拉取或获取项目代码，或在 GitHub 上进行资源搜索时，自动允许，不用每次都点允许」（2026-09-13）
  - 落地：见 `.cursor/skills/github-reference-research/SKILL.md` 的「Tool 授权 / 免确认」章节
  - **注意**：仍然不要 `gh repo delete` / `gh release delete` / `gh workflow disable` 等破坏性 GitHub 操作——这条只覆盖**只读 + 拉取**类
- ✅ **可以自主执行（破坏性单容器操作，已有授权）**：`rm -rf` 单一项目目录（如 `rm -rf ai-trader/`）、`docker stop` 单容器、`docker rm` 单容器、`pkill -f xxx`（杀指定进程）—— 2026-09-23 用户授权"清理干净"项目时已涵盖
- ✅ **可以自主执行（ai-trader 自提 PR 自动合入 main，2026-09-25 22:58 用户授权）**：在 ai-trader 仓库内，agent 自己提的、自己写代码 + 自测过的 PR，**可以自主** `gh pr create` + `gh pr merge --squash --delete-branch` 合入 main，避免用户没看到遗漏
 - **触发条件**：仅限 ai-trader 仓库（`bobing888/ai-trader`）；仅限 agent 自己写的 feature/fix 分支；本地测试 + 类型检查 + build 已通过
 - **明确不属于本授权**：合并**他人提的 PR**、合并跨 fork 的 PR、对 main 强制推送、对 main 直接 push（这些仍属下方红线 4）
 - **落地流程**：见 `.cursor/skills/branch-management/SKILL.md` 的「标准工作流 · 场景 A」（已升级为自动合并闭环）
 - **追加授权备忘 #3（2026-09-25 22:58）**：用户授权「之后新需求实现时，是从主分支，切出新分支，来实现，实现后，自动合并到主分支，避免我没看到遗漏」——本条覆盖规则 7 红线 4 中"合并 PR"对**自己提的** PR 的限制
- ⚠️ **绝对红线（仍然必须问用户，但只这 4 类）**：
 1. **跨租户破坏性操作**（`rm -rf /`、清空整个 `/opt`、`docker system prune -a` 清所有镜像、删数据库 DROP、删主分支、删 fork）
 2. **生产环境不可逆变更 + 影响其他项目**（`docker compose down` 停共享 caddy、强制推送 `git push --force` 到 main、回滚其他项目、动 `/etc`、改 root 密码、`ufw` 改防火墙、修改 sshd_config）
 3. **付费 / 外部副作用**（发邮件 / 短信 / webhook、扣款、发推特、调用付费 API、付费 npm 包订阅、真实下单交易、真实模拟盘开仓）
 4. **会阻塞其他人的操作**（强制推送共享 main、**合并他人 PR**、关闭他人 issue、停 community.dyddd.com / tg.dyddd.com 等无关项目）—— **ai-trader 自提 PR 自动合并不在此列（见上方授权第 5 条）**

**判断准则**：
> 如果命令失败可以重试/恢复，且不会对外产生副作用 → 直接执行，连问都不要问。
> 如果命令失败**无法撤销**或**对外有副作用** → 必须先问。

**禁止**（用户明确禁止的行为，对应 2026-09-23 21:11 二次确认）：
- ❌ **问"你能允许吗？" / "需要我执行吗？" / "需要 Run 吗？" / "需要部署吗？"** ——一律自主执行，结束后报告
- ❌ **问"我已经写好了，可以运行吗？"** ——自动跑，跑完报告
- ❌ **问"你要不要看一下再执行？"** ——直接执行，事后报告
- ❌ **把 build/test/deploy/install 的执行步骤单列出来等用户点头** —— 自主推进
- ❌ **命令失败重试时反复停下问"重试吗？" / "要不要继续？" / "用 cd 改路径继续？"** —— 改 3 次自纠后回报
- ❌ **用户已经给出"自主执行"授权后，又因为 sandbox 限制 / required_permissions / cwd 异常停下问** —— 改用 `required_permissions: ["all"]` 兜底，或报错后自主换路径
- ❌ **ssh 远端执行 docker / git / curl 命令时停下问"远程跑这条行不行"** —— 自主 ssh 执行，回报输出
- ❌ **部署（deploy / docker compose up）停下问用户** —— 跑测试通过后直接部署
- ❌ **执行测试（pytest / vitest / npm test）停下问** —— 直接跑，失败就修

**正确做法**：
- 写完代码 → 直接 build → 失败就修 → 修好再 build → 通过后直接 deploy
- deploy 完 → 直接 curl 验证 → 截图验证 → 报告结果
- 命令失败 → 看错误信息 → 修（cd / 路径 / 权限）→ 重试 → 最多 3 次自纠后回报，不要每修一次就问一次
- 全程不打断用户，只在最后报告「做了什么 + 结果怎样 + 是否需要用户做什么（极少数情况）」

**回报**：命令的输入/输出/退出码都要在最终汇报中给到，不要省略。

---

## 规则 8：动手前先 GitHub 调研，不要闭门造车

**任何「新增功能 / 新增子系统 / 引入新的技术领域」「优化准确性 / 引入新算法 / 新指标」类任务，必须先调 `.cursor/skills/github-reference-research/SKILL.md`，调研成熟参考实现。**

适用范围（满足任一即触发）：

| 类别 | 例子 |
|------|------|
| 新功能 / 新模块 | 通知系统、时间线、AI 分析、订单流、微观结构、Cortex 6 维分析、K 线指标、回测引擎、推送通知 |
| 新技术领域引入 | 跨交易所套利、资金费率、期权希腊值、做市策略、portfolio 优化 |
| 新算法/新指标 | 新的技术指标（OBV、Ichimoku、Wyckoff）、Kelly 变体、LightGBM/XGBoost 校准、异常检测 |
| 核心准确性增强 | 改进 confidence 分数、引入 ML 校准、强化 regime 识别、加新数据源 |
| 用户已经说过的关键词 | 「从 github 找」「参考实现」「成熟方案」「业内做法」|

**强制流程**（**写代码前**必走）：

1. **从需求/技术领域** 派生 2-4 个 GitHub search query
   - 例：`AI 推送通知 天文级` → `crypto trading signal notification server` / `zerodha kite telegram alert open source`
   - 例：`timeline 时间线 推荐单` → `trading dashboard timeline react` / `kline timeline visualization github`
2. **搜索并选 ≥2 个 credible repositories**
   - 优先：有 active commit / 文档齐全 / 兼容 license / star>300
3. **读源码 + 文档**，不要只看描述/star
   - 重点读：他们怎么解决「和你需求同样痛点」的代码段
4. **总结**到 proposal/spec/对话中：
   - Repo URL + license（MIT / Apache-2.0 / GPL）
   - 借鉴的具体 feature / pattern / 算法
   - **怎么适配**到本项目
   - **不能抄**：产品特定行为、品牌、资产、不兼容 license 的代码
5. **引用** repo URL 进 proposal/design/task 文档，让决策有据可查

**Skip 条件**（**全部满足**才能跳过）：
- 用户明确说「这次不用查 github」
- 任务 ≤ 3 行 trivial 改动（typo 修正、参数名改、bug 修复 ≤ 1 文件）

**禁止**：
- ❌ 跳过调研直接闭门造车
- ❌ 用「我知道」代替实际读代码
- ❌ 把 README/description 当作实施依据
- ❌ 借鉴代码不写 license/出处
- ❌ 「我看了几个 star 高的项目」式空泛调研

**正确做法**：
- 接到新功能 → 立刻 `gh search repos [query] --sort stars --limit 10`
- 对前 2-3 个 repo → `gh repo clone --depth 1 ...` 后读关键文件
- 读完后写一个简短的「调研笔记」段落：
  ```
  ## GitHub 调研笔记
  - Repo: xxx (license: MIT) → 借鉴了 xxx 实现
  - Repo: yyy (license: Apache-2.0) → 借用了 yyy 算法
  - 适配：不照搬 X，因为本项目是 Y；保留 Z 实现
  ```
- 然后才进入 brainstorming → plan → code

**WebFetch** + `gh search` + `gh repo view` 都可以用，**不要只靠 WebSearch**。

---

## 规则 9：PR 合入 main → 必须自动部署到生产

**触发条件（2026-09-27 16:31 用户明确授权）**：

> 「每次合入到主分支的代码，都自动部署到生产，因为我要查看最新的效果」

**适用范围**：仅 ai-trader 仓库（`bobing888/ai-trader`）的 main 分支。

**强制流程**（**PR 合入 main 那一刻起，agent 必须立刻自动执行**）：

1. **PR merge 完成** → agent 检测到「merged into main」（通过 `gh pr view --json state,mergedAt` 或 git log 显示新的 merge commit 在 main 上）
2. **拉取最新 main** → `git checkout main && git pull --ff-only origin main`
3. **立刻自动执行部署** → `bash scripts/deploy.sh`（用 `block_until_ms: 0` 后台跑，自己轮询）
4. **部署成功后验证** → curl `https://dyddd.com/api/health` + 至少一个 `https://dyddd.com/api/signals/recommend/BTC-USDT?timeframe=1h` 接口
5. **回报**：「PR #N 已合入 + 已部署 + 线上已可见新功能」

**禁止**：
- ❌ 合入 PR 后只回报「已合入」，不部署
- ❌ 「要部署吗？」/「要现在部署吗？」式询问
- ❌ 把「部署」单列出来等用户点头

**特殊情况**：
- **如果 main 上一次 deploy 还没跑完** → 等当前 deploy 完，再跑新一次（不要并发 deploy，会 rsync 冲突）
- **如果 deploy 失败自动 rollback** → 报告失败原因，但**不要自动回滚 PR**（PR 已合入是事实）
- **如果 deploy 失败且用户希望回滚代码** → 走 `deploy-dyddd` skill 的 `bash scripts/deploy.sh --rollback`

**与规则 7 的关系**：
- 规则 7 已经覆盖「deploy 自主执行不打断」
- 规则 9 是规则 7 的子规则，专门规定**触发时机** = PR merge to main

**详细部署流程**：见 `.cursor/skills/deploy-dyddd/SKILL.md` §2（`scripts/deploy.sh` 标准 6 步流程）

---

## OpenSpec 工作流（非默认）

OpenSpec 流程适用于**真正的架构性新项目**（全新子系统、全新前端框架、重大 API 变更）。

**日常迭代（修复 bug、样式调整、添加参数）不需要走 OpenSpec。**

如果判断需要走 OpenSpec，按 `openspec-propose` → `openspec-apply-change` → `openspec-verify-change` → `openspec-archive-change` 顺序执行。

---

## 配套 Skill 速查

| 场景 | Skill |
|------|-------|
| 不确定走哪个流程 | task-classifier |
| 发现 bug | systematic-debugging |
| **每日 GitHub 趋势吸收（自主迭代）** | **daily-github-absorption** |
| **写新功能/新模块前** | **github-reference-research**（规则 8 强制） |
| **一次对话多个 bug/需求（批量派单）** | **multi-task-dispatch** |
| **PR 合入 main → 自动部署生产** | **deploy-dyddd**（规则 9 强制，2026-09-27 起） |
| 新功能/新子系统 | brainstorming → writing-plans → executing-plans |
| 现有代码修改 | brainstorming(bounded) |
| 可行性调研 | brainstorming(spike) |
| UI/多状态改动 | scenario-coverage-checklist |
| 声称完成前 | verification-before-completion |
| 写代码前 | tdd-scaffold（自动触发，无需 `/tdd`） |
| 执行计划 | subagent-driven-development |
