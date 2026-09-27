---
name: deploy-dyddd
description: Deploy / monitor / restart the ai-trader stack on production servers. PRIMARY = `dyddd-prod` (156.225.31.18, dyddd.com, since 2026-09-25, OLD: 154.219.111.145 was blackholed). SECONDARY = `kbkkk-prod` (206.187.211.211, kbkkk.com, added 2026-09-26 as a backup/CI-front deployment). SSH alias `dyddd-prod` uses key auth; `kbkkk-prod` uses root password (no key yet). NEVER edits /etc on prod, NEVER runs destructive ops. **Auto-trigger: when any PR merges into ai-trader main (2026-09-27+), agent MUST auto-run `scripts/deploy.sh` to dyddd-prod per user directive — see §9.** Use when user says "deploy", "重启后端", "看线上日志", "publish", "上线", "VPN 挂了", "改 SS 密码", or after a PR is detected merged into main.
---

> **⚠️ IP 迁移备忘（2026-09-25 14:38 已生效）**：
> - **新服务器 / 当前生产** = `156.225.31.18`（Ubuntu 22.04, ai-trader + Shadowsocks + skill-registry 都在这台）
> - 老服务器 `154.219.111.145` = 已被 GFW 黑洞 / 已迁出，**别再 alias 它当生产**
> - SSH key alias `dyddd-prod` 当前仍指向老 IP（见 §0.A），下次正经重构前先用 root 密码绕开
>
> **🛡 VPN 备忘（2026-09-25 14:38 已加固）**：
> - Shadowsocks 跑在新服务器 `156.225.31.18:51888`（aes-256-gcm）
> - **systemd unit**: `/etc/systemd/system/ssserver.service`（enabled，开机自启 + 崩溃自启）
> - **密码 + 方法 + 端口 + 配置文件路径**：见 §8
> - 加固：`ProtectSystem=strict / NoNewPrivileges / MemoryDenyWriteExecute` 已开启

> **🛠 一次性修复（2026-09-19 18:56）**：历史的 5 个重复坑已全部消除，所有 deploy 操作请直接用：
> ```bash
> bash scripts/deploy.sh                  # 默认 deploy（原子 rsync + rebuild + 健康检查 + 自动回滚）
> bash scripts/deploy.sh --restart        # 只 restart（不改代码）
> bash scripts/deploy.sh --logs           # 看后端最近 200 行 logs
> bash scripts/deploy.sh --health         # 只做健康检查
> bash scripts/deploy.sh --rollback       # 回滚到上一次成功的版本
> ```
>
> **⚠️ 历史遗留标记（2026-09-25 15:46 已清）**：SKILL.md 之前多处引用黑洞老 IP `154.219.111.145`，现在 §0.A 已修。`scripts/deploy.sh` 本身**不写死 IP**（全部走 `SSH_TARGET=dyddd-prod` 别名），所以只需要 SSH config 一处修对就行。
>
> **🆕 2026-09-25 15:35 域名迁移补丁（DNS 切了但 CORS 没切）**：
> - 现象：把 `dyddd.com` 的 DNS A 记录从 `154.219.111.145` 切到 `156.225.31.18` 之后，`https://dyddd.com/api/health` 仍然 200，但**浏览器打开前端会被 CORS 拒绝**（`Disallowed CORS origin`），因为后端 `AI_TRADER_CORS_ORIGINS_RAW` 还停留在老 IP
> - 修复：在 `/opt/ai-trader/ai-trader/docker-compose.yml` 把 `http://154.219.111.145` 替换成 `https://dyddd.com,https://www.dyddd.com`，然后 `cd /opt/ai-trader/ai-trader && docker compose up -d backend`
> - 验证：`curl -H "Origin: https://dyddd.com" -X OPTIONS -i https://dyddd.com/api/health` → 返回 `access-control-allow-origin: https://dyddd.com`
> - **新坑 RC6**：未来 DNS / 域名变动时，**记得同步改 compose 的 `CORS_ORIGINS_RAW`**，否则用户看到的现象是"前端能打开但所有 API 调用 400"

## 0. 凭证（NEVER HARDCODE）

### 0.A. SSH key alias `dyddd-prod`（✅ 2026-09-25 15:46 已修复）

`~/.ssh/dyddd_prod_config` 当前正确状态：
```
Host dyddd-prod
    HostName 156.225.31.18         # ← 已修 (旧: 154.219.111.145 已黑洞)
    Port 22
    User root
    IdentityFile ~/.ssh/dyddd_prod_ed25519
    IdentitiesOnly yes
    ...
```

✅ `ssh dyddd-prod 'whoami'` → 直接返回 `root`（免密 key auth）

**修复过程（2026-09-25 15:44-15:46 实战）**：
1. 备份 `~/.ssh/dyddd_prod_config` → `~/.ssh/dyddd_prod_config.bak.20260925_1544`
2. sed 改 `HostName` → `156.225.31.18`
3. 把 `~/.ssh/dyddd_prod_ed25519.pub` 推到新服务器 `~/.ssh/authorized_keys`
4. **关键一步**：服务器 sshd 默认 `PubkeyAuthentication no`，需要新建 `/etc/ssh/sshd_config.d/99-pubkey.conf`（不动主配置，保留 PasswordAuthentication=yes 不锁死）
5. `sshd -t` 测语法 → `systemctl reload ssh`（不是 restart，新连接生效）
6. 立即测 `ssh dyddd-prod 'whoami'` → 返回 root = 切换完成

⚠️ **如果将来 sshd 出问题导致 key auth 失败**，可以临时退回 §0.B sshpass root 密码（密码仍可用，因为没关 PasswordAuthentication）

### 0.B. Root 密码（临时 fallback，仅 IP 迁移过渡期）

| 项 | 值 |
|---|---|
| Host | `156.225.31.18:22` |
| User | `root` |
| Password | `7698v3Zrn254`（**human-only, agent 也不要持久化**） |
| 用途 | 仅当 `ssh dyddd-prod` 不通时，agent 用 `sshpass -e` 临时连 |
| 期限 | 直到 §0.A 完成切换 |

agent 使用模式（**只读 + 短链路**，别持久化到磁盘）：
```bash
SSHPASS='7698v3Zrn254' sshpass -e ssh -o StrictHostKeyChecking=accept-new \
  -p 22 root@156.225.31.18 '<cmd>'
```

### 0.C. 服务器上有什么（最新 2026-09-25 现状）

```
OS:       Ubuntu 22.04 LTS x86_64
公网 IP:  156.225.31.18
Docker:   在跑（compose v2）
ai-trader: frontend (:80/:443 nginx) + backend (:8765 localhost) + redis (:6379 localhost)
Shadowsocks: 端口 51888，systemd 守护（详见 §8）
其他进程: 8088=Clash 订阅, 8080=未知 python3 (非 skill-registry, 启动时间 Sep 25)
          7890+9090=mihomo (科学上网)
```

如果 `ssh dyddd-prod 'whoami'` 不通：
1. 临时走 0.B 的 sshpass
2. **不要重新生成 key / 不要重新推送密码**（除非用户明确同意）
3. 之后立刻回头修 §0.A

### 0.E. 今次 (2026-09-25 15:35) 完整验证过的生产事实

| 项 | 实测值 |
|---|---|
| OS / Docker | Ubuntu 22.04.5 LTS / Docker 29.7.2 / Compose v5.5.0 |
| 容器运行中 | ai-trader-backend (502MB image, 25s 前 healthy), ai-trader-frontend (74.6MB image, nginx 1.27.5, Up 19min), ai-trader-redis (redis 7-alpine, Up ~1h) |
| 端口监听 | 80+443=frontend (公网), 8765=backend (127.0.0.1 only), 6379=redis (127.0.0.1 only) |
| API base path | `/api/*` （**不是** `/`，根路径会返回 `{"detail":"Not Found"}`） |
| 健康检查 endpoint | `GET /api/health` （**不是** `/health` 也不是 `/healthz`） |
| 健康响应体 | `{"status":"ok","app_name":"ai-trader","version":"0.1.0","debug":false,"freqtrade_db_configured":false}` |
| DNS (dyddd.com) | A 记录 → `156.225.31.18`（已切换，老 IP `154.219.111.145` 已下） |
| HTTPS | nginx 1.27.5 + acme.sh (`/root/.acme.sh/dyddd.com_ecc/`) + `/etc/nginx/ssl/dyddd.com.crt|.key|.chain.crt` |
| CORS 白名单 (当前生效) | `http://localhost, http://localhost:80, http://127.0.0.1, http://127.0.0.1:80, https://dyddd.com, https://www.dyddd.com` |
| 数据迁移 | **无迁移必要**：后端 v0.1.0 无 freqtrade DB、无 SQLite 挂载、无 user prefs 持久化；Redis 内存态重启即失，符合 W1 阶段定义 |

## 0.D. DNS 备忘

- 域名 `dyddd.com` 当前 A 记录指向 `156.225.31.18`（用户已手动改，2026-09-25）
- 老记录 `154.219.111.145` 已停

## 1. 历史踩坑（5 个 root cause，一次性修完）

| # | Root Cause | 现象 | 修复位置 |
|---|------------|------|---------|
| RC1 | SKILL 路径写 `/opt/ai-trader`，实际部署目录是 `/opt/ai-trader/ai-trader/` | `no configuration file provided: not found` | `scripts/deploy.sh` 用 `REMOTE_DIR=/opt/ai-trader/ai-trader` |
| RC2 | `rsync --exclude='.env'` 会让 docker compose 找不到 env_file，容器起不来 | `env file ... not found` | `scripts/deploy.sh` 单独 `scp` `.env`，不放在 rsync --exclude |
| RC3 | Cursor 沙盒下 `docker build` 没权限（permission denied on `.sock`） | 本地 build 必败 | `scripts/deploy.sh` 永远走 `ssh ... docker compose build`（服务器侧 build） |
| RC4 | 直接 `rsync` 到目标目录，中途断 → 目标被打成半新半旧 | 容器起不来 | `scripts/deploy.sh` 用 staging → `mv` 原子替换 |
| RC5 | 老容器 healthy 状态被误判成新容器 healthy | 假阳性 | `scripts/deploy.sh` 等 Docker `State.Health.Status == healthy`，再加 HTTP `/api/health` 真请求 + WS import 自检 |
| RC6 | DNS / 域名变更后忘了同步改 `AI_TRADER_CORS_ORIGINS_RAW` | 浏览器报 `Disallowed CORS origin`，但 `curl` 看 health 是 200 | 任何 DNS / 域名 / 端口变更都先在 `docker-compose.yml` 改 CORS → `docker compose up -d backend` → 用 `curl -H "Origin: <新域名>" -X OPTIONS -i https://<新域名>/api/health` 验 |

## 2. 推荐：直接跑 `scripts/deploy.sh`（BuildKit cached，~40s vs 3min）

```bash
bash scripts/deploy.sh
# 自动完成（v2 流程，2026-09-27+）：
#   Step 0/6: SSH 联通检查
#   Step 1/6: 本地预检 (frontend/package.json + # syntax=docker directive)
#   Step 2/6: rsync 本地 → /opt/ai-trader/ai-trader/ (排除 .env/.git/node_modules)
#   Step 3/6: 预拉基础镜像 (python:3.12-slim / node:20-alpine / nginx:1.27-alpine)
#   Step 4/6: BuildKit 增量 build (--cache-from/to type=local,mode=max) → ~40s
#   Step 5/6: docker compose up -d --force-recreate --no-deps
#   Step 6/6: 健康检查（最多 60s）+ HTTP `/api/health` 真请求
# 失败时：set -e 终止，留 staging 让用户 inspect（kbkkk 自动 rollback）
```

**关键技术（避免重复拉镜像的关键 §10.）**：
- **BuildKit cache mount** (Dockerfile 内 `RUN --mount=type=cache,target=/root/.cache/pip` 等) — 服务器本地 `~/.local/share/pnpm/store`、`/root/.cache/pip` 不被每次清空
- **`type=local,mode=max`** — docker buildx 把所有 build 层（含 intermediate）写到 `/var/lib/buildkit-cache/ai-trader/`
- **`preload-base-images.sh`** — deploy 前先 `docker pull` 三大基础镜像（python/node/nginx）到本地，deploy 中途不会卡 pull

退出码：
- `0` = 成功
- `1` = 通用错误（pytest 失败 / .env 缺失）
- `2` = 健康检查超时（kbkkk 已自动回滚；dyddd 留 staging）
- `3` = SSH 连不上

## 3. 手动排查模式（debug 用）

```bash
# 看容器状态
ssh dyddd-prod 'docker ps --format "table {{.Names}}\t{{.Status}}"'

# 看后端 logs
ssh dyddd-prod 'docker logs --tail 200 ai-trader-backend'

# 看 compose 文件内容
ssh dyddd-prod 'cat /opt/ai-trader/ai-trader/docker-compose.yml'

# 手动健康检查
ssh dyddd-prod 'docker inspect --format="{{.State.Health.Status}}" ai-trader-backend'

# 看历史备份
ssh dyddd-prod 'ls -la /opt/ai-trader-backup/ /tmp/ai-trader-compose-backups/'
```

## 4. 关键路径速查

| 路径 | 用途 |
|------|------|
| `/opt/ai-trader/ai-trader/` | **真部署目录**（注意是嵌套的 `ai-trader/ai-trader/`） |
| `/opt/ai-trader-staging/` | 临时 rsync 目标（deploy 时会被 mv 进来再清空） |
| `/opt/ai-trader-backup/` | 上一次成功版本的快照（rollback 用） |
| `/tmp/ai-trader-compose-backups/` | compose + .env 历史（`docker-compose.<ts>.yml` / `dotenv.<ts>`） |
| `~/.dyddd_prod_new_root_pw` | 人类专用 root 密码，agent 不读 |

## 5. 禁止操作（硬红线，违反必报）

- ❌ `rm -rf /`、`rm -rf /opt/ai-trader`（整个项目删）
- ❌ `dd / mkfs / fdisk / mount / umount`
- ❌ `docker system prune -a`（清所有镜像，会拖累下次构建）
- ❌ 改 `/etc/ssh/sshd_config` + `systemctl restart sshd`（要用户亲自做）
- ❌ `git push --force` 到 main / `git reset --hard` 在服务器
- ❌ 改 root 密码 / 创建新用户 / 改 sudoers（要用户亲自做）
- ❌ 跑 `--privileged` 容器
- ❌ `iptables` / `ufw` 改防火墙规则
- ❌ `mysql / psql / sqlite3` 跑 DELETE / DROP / UPDATE 写操作（只 SELECT）
- ❌ **不再手动拼 rsync / docker 命令**（用 `scripts/deploy.sh`，别再踩 RC1-5 的坑）

## 6. 完成报告格式

跑 `scripts/deploy.sh` 后会自动输出：

```
==========================================
  deploy-dyddd 报告
  时间: <ISO>
  操作: deploy (atomic swap + rebuild)
  影响容器: ai-trader-backend (重建), ai-trader-frontend (未动, 跑 nginx)
  备份位置: /opt/ai-trader-backup, /tmp/ai-trader-compose-backups
  健康检查: healthy (HTTP `/api/health` + WS import)
==========================================
```

## 7. 失败处理

`scripts/deploy.sh` 已经内置：
- pytest 失败 → 直接 exit 1，不推 staging
- SSH 不通 → exit 3，不动服务器
- 健康检查 60s 超时 → 自动 rollback + 输出 logs
- compose build 失败 → 不进入 up 步骤（rsync 已替换目录，rollback 会还原）
- 任何 step `set -e` 失败 → 立即终止，留下 staging 让用户 inspect

如果仍然卡住：
1. 看 `scripts/deploy.sh` 输出最后 30 行
2. `ssh dyddd-prod 'docker logs --tail 100 ai-trader-backend'`
3. `ssh dyddd-prod 'ls -la /opt/ai-trader-staging /opt/ai-trader-backup'`
4. 3 次自纠后失败 → 报用户，不要继续猜

## 8. Shadowsocks VPN 速查（VPN 挂了 → 看这里）

> 用户问"VPN 挂了"/"重连 VPN"/"改 SS 密码" → 第一跳就执行：

### 8.A. 当前 VPN 客户端配置（备份到这里以便一键给客户）

```
服务器:   156.225.31.18
端口:     51888
密码:     123.Chen
加密:     aes-256-gcm
模式:     tcp_and_udp (origin)
配置文件: /etc/shadowsocks/config.json
```

### 8.B. 状态查询

```bash
# 一条命令看 SS 是否健康
ssh dyddd-prod 'echo === 进程 === && systemctl is-active ssserver.service && \
  echo === 端口 === && (ss -tlnp 2>/dev/null | grep 51888) && \
  echo === 配置 === && cat /etc/shadowsocks/config.json && \
  echo === 最近 10 行日志 === && tail -10 /var/log/ssserver.log 2>/dev/null'
```

### 8.C. 重启 / 自愈

```bash
# 进程死掉 → 让 systemd 重启
ssh dyddd-prod 'systemctl restart ssserver.service && systemctl status ssserver.service --no-pager'

# 完全不响应 → 看 unit 还在不在
ssh dyddd-prod 'systemctl cat ssserver.service | head -5'
```

### 8.D. 改密码（用户明确说"改 SS 密码"时）

```bash
# agent 操作 SOP（已在 2026-09-25 实战过，遗留踩坑见 8.E）
SSHPASS='7698v3Zrn254' sshpass -e ssh -o StrictHostKeyChecking=accept-new \
  -p 22 root@156.225.31.18 bash -s << 'INNER'
set +e  # 关键：别用 set -e，否则 pkill 杀掉会触发子 shell 退出
NEW_PW="$1"

# 1. 改配置
python3 -c "
import json
c=json.load(open('/etc/shadowsocks/config.json'))
c['password']='$NEW_PW'
json.dump(c, open('/etc/shadowsocks/config.json','w'), indent=2)
"
chown root:shadowsocks /etc/shadowsocks/config.json
chmod 640 /etc/shadowsocks/config.json

# 2. 重启（systemd 会自动拉起）
systemctl restart ssserver.service
sleep 3

# 3. 验证
systemctl is-active ssserver.service
ss -tlnp 2>/dev/null | grep 51888
INNER

# 4. 端到端验证（从 agent 本机）
docker rm -f ss-verify 2>/dev/null
docker run -d --name ss-verify --entrypoint '' -p 11081:1080 \
  ghcr.io/shadowsocks/sslocal-rust:latest \
  /usr/bin/sslocal \
    -b 0.0.0.0:1080 \
    -s 156.225.31.18:51888 \
    -m aes-256-gcm \
    -k "$NEW_PW" \
    --tcp-no-delay > /dev/null
sleep 4
curl -s -x socks5h://127.0.0.1:11081 https://ifconfig.me ; echo
docker rm -f ss-verify > /dev/null
```

### 8.E. 踩坑历史（防复发）

| # | 坑 | 教训 |
|---|----|------|
| SS-1 | `kill ssserver` 后立刻启新进程，但 set -e + pkill 退出码 → sshpass exit 255，下面的重启命令不执行 → **VPN 中断** | **不要在多步 ssh 命令里用 `set -e`**；每步独立 `ssh` 调用，让每一步的失败都可观察 |
| SS-2 | sslocal docker 镜像 entrypoint 是 busybox sh，`-b` 触发 `illegal option` | 跑客户端用 `--entrypoint ''` 改写为 `/usr/bin/sslocal -b ... -s ...` |
| SS-3 | 用户报"VPN 挂了"时，agent **第一反应必须先查进程**——很可能根本不是 VPN 服务挂了，是客户端 IP / 密码配置老化 | 永远先 `systemctl is-active ssserver.service`，再决定动什么 |
| SS-4 | 老 IP `154.219.111.145` 黑洞后，客户端还在用老 IP → 误以为 VPN 死了 | DNS + 客户端都要随 IP 迁移 |

### 8.F. 严格禁止（agent 自主范围之外）

- ❌ 用 `apt install shadowsocks-libev`（**会覆盖**当前 `/usr/local/bin/ssserver` 这个 1.25.0 版本，导致加密方式可能不对）
- ❌ 用 `docker run` 起 ssserver（**会污染当前端口 + 双重 ssserver 监听 51888 会被 EINVAL**）
- ❌ 改 unit 文件里的 `ExecStart` 而不改配置——配置和 unit 耦合，改 unit 必须配套改配置
- ❌ 没经用户同意就**生成新密码自动替换**

---

## 9. 自动触发：PR 合入 main → 立刻部署（2026-09-27 起）

**授权来源**：用户明确要求「每次合入到主分支的代码，都自动部署到生产，因为我要查看最新的效果」（2026-09-27 16:31）。本条覆盖 AGENTS.md 规则 7 中的「deploy 必须问用户」红线（这是用户主动加的「不打断」授权）。

**适用范围**：仅 ai-trader 仓库（`bobing888/ai-trader`）的 main 分支。kbkkk-prod 不在自动触发范围内（用户没授权）。

**触发时机**：
- agent 通过 `gh pr view <N> --json state,mergedAt` 检测到 PR 状态变为 `MERGED`
- 或 git log 显示新 merge commit 出现在 `main` 上
- 或对话中用户明确说「合入 main 后立刻部署」（即使 PR 还没 merge）

**自动流程**（agent 必须自觉执行，**不打断用户**）：

```bash
# 1. 确认 PR 已合入 main
cd /Users/hahaha/Desktop/CODE/ai-trader
git checkout main && git pull --ff-only origin main
git log --oneline -3   # 应看到新 merge commit

# 2. 立刻部署（block_until_ms: 0 后台跑）
bash scripts/deploy.sh 2>&1 | tee /tmp/deploy-auto-$(date +%Y%m%d-%H%M).log &
DEPLOY_PID=$!

# 3. 轮询 + 等完成（不要问用户，事后报告）
for i in $(seq 1 30); do
  sleep 30
  if ! kill -0 $DEPLOY_PID 2>/dev/null; then break; fi
done

# 4. 验证（curl 至少 2 个 endpoint）
curl -s https://dyddd.com/api/health
curl -s 'https://dyddd.com/api/signals?symbol=BTC-USDT&timeframe=1h' | python3 -m json.tool 2>&1 | head -20

# 5. 报告：PR #N + commit + 部署结果 + 线上验证
```

**禁止**：
- ❌ 合入 PR 后只说「已合入」不部署
- ❌ 「要部署吗？」式询问
- ❌ 把部署步骤单列出来等用户点头
- ❌ 并发跑两次 deploy（rsync 会冲突）—— 等上一次跑完再跑

**特殊情况**：
- **deploy 失败自动 rollback** → 报告失败原因，但**不要自动 revert PR**（PR 合入是事实，rollback 已恢复线上版本）
- **用户明确说「不要自动部署」** → 当次跳过，但仍要报告「已合入 + 未部署 + 原因」
- **kbkkk-prod** → 用户没授权自动部署，仍走手动确认

**为什么没做 GitHub Action 自动化**：仓库目前没有 `.github/workflows/`，加 GitHub Action 需要：(1) 把 SSH key 存到 GitHub Secrets，(2) 写 action workflow，(3) 调试 first run。**当前用 agent 自觉触发**作为最小可行方案，未来如果 agent 经常忘记触发再升级到 GitHub Action。
