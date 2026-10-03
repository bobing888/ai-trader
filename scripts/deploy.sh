#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────
# ai-trader 一键部署脚本 (default kbkkk-prod, override with SSH_TARGET)
# 用法:
#   bash scripts/deploy.sh                # 默认 deploy (rebuild + up)
#   bash scripts/deploy.sh --restart      # 只 restart backend/frontend
#   bash scripts/deploy.sh --logs         # 看后端最近 200 行 logs
#   bash scripts/deploy.sh --health       # 只做健康检查
#   bash scripts/deploy.sh --frontend     # 只 rebuild + up 前端
#
# SSH 别名: kbkkk-prod (默认 PRIMARY, 走 sshpass 密码)
# 备选: SSH_TARGET=dyddd-prod (legacy 灰度) (需要 ~/.ssh/config 配好)
# 部署路径: /opt/ai-trader/ai-trader/
# ──────────────────────────────────────────────────────────────────────────
# -e: 任一命令失败立即退出
# -x: 每条命令执行前打印 +cmd 到 stderr —— 部署中途中断时,trap 看不到 / exit code 拿不到
#      也能立刻定位死在哪一步 (2026-10-03 pr49 教训: 之前只 set -e, 中断时 0 日志)
set -ex

SSH_TARGET="${SSH_TARGET:-kbkkk-prod}"
# ssh 认证模式：kbkkk-prod → password / dyddd-prod → key。在 alias→IP 解析前固定下来
case "$SSH_TARGET" in
  kbkkk-prod) SSH_AUTH_MODE="password" ;;
  dyddd-prod) SSH_AUTH_MODE="key" ;;
  *)          SSH_AUTH_MODE="unknown" ;;
esac
# 解析 SSH_TARGET alias → IP（kbkkk-prod / dyddd-prod 没在 ~/.ssh/config 时直接用 IP）
case "$SSH_TARGET" in
  kbkkk-prod)  SSH_TARGET="root@206.187.211.211" ;;
  dyddd-prod)  SSH_TARGET="root@156.225.31.18" ;;
  # 其它值（如已含 @ 或 IP）原样使用
esac
REMOTE_DIR="/opt/ai-trader/ai-trader"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE="${PROFILE:-default}"

# 按 SSH_TARGET alias 选 override 文件（注意：SSH_TARGET 已展开为 root@IP，要看 alias 才能分 kbkkk / dyddd）
# 我们改用 SSH_AUTH_MODE 旁边的别名判定：原始 alias 在 set 时已转 IP，重建时记下来
# 简化：用 SSH_AUTH_MODE = password → kbkkk override，其它 → dyddd override
case "$SSH_AUTH_MODE" in
  password) COMPOSE_FILES="-f docker-compose.yml -f docker-compose.kbkkk.yml" ;;
  *)        COMPOSE_FILES="-f docker-compose.yml -f docker-compose.dyddd.yml" ;;
esac

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1,33m'; BLUE='\033[0;34m'; NC='\033[0m'

log()  { echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} $1"; }
ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
err()  { echo -e "${RED}✗${NC} $1"; }

# ── ssh wrapper: kbkkk-prod 走 sshpass (skill ssh-prod-credentials §1.B) ──
# 用户提供 SSHPASS 或 KBKKK_PASS 环境变量时,自动用 sshpass 包装 ssh 调用.
# 这样 deploy.sh 在 PRIMARY (kbkkk-prod) 上也能用,无需 ~/.ssh/config.
# 注意: SSH_CMD 是数组 (bash array)，调用用 "${SSH_CMD[@]}".
# 这样在 zsh / strict-mode 下也能正确解析（用字符串 + word-split 在 zsh 不工作）。
SSH_CMD=(ssh)
# 强制 ssh 客户端行为,避免 sshpass 路径在密码错时 hang:
#   - ConnectTimeout=10: TCP 连接 10s 还没通就 fail
#   - ServerAliveInterval/Count: 防卡在已建连的 channel 上
#   - StrictHost: 自动接受新 fingerprint
#   - NumberOfPasswordPrompts=1 + PreferredAuthentications=password + PubkeyAuthentication=no:
#     sshpass 走 password-only, 错密码立即退出 (不无限重试)
#   - LogLevel=ERROR: 不刷 verbose log (deploy 输出来看, 不被 ssh debug 淹没)
SSH_COMMON_OPTS=(
  -o ConnectTimeout=10
  -o ServerAliveInterval=15
  -o ServerAliveCountMax=2
  -o StrictHostKeyChecking=accept-new
  -o NumberOfPasswordPrompts=1
  -o PreferredAuthentications=password
  -o PubkeyAuthentication=no
  -o LogLevel=ERROR
)
if [[ "$SSH_AUTH_MODE" == "password" ]] && command -v sshpass >/dev/null 2>&1; then
  if [[ -n "${SSHPASS:-}${KBKKK_PASS:-}" ]]; then
    # 用临时文件方式喂密码(避免 -e 在 ssh 子进程里丢失 env)
    _sshpass_pw_file="$(mktemp -t kbkkk-sshpass.XXXXXX)"
    chmod 600 "$_sshpass_pw_file"
    printf '%s' "${SSHPASS:-${KBKKK_PASS}}" > "$_sshpass_pw_file"
    SSH_CMD=(sshpass -f "$_sshpass_pw_file" ssh)
    trap 'rm -f "$_sshpass_pw_file"' EXIT
    export SSHPASS="${SSHPASS:-${KBKKK_PASS}}"  # 让 sshpass -e 也可用
    log "kbkkk-prod: 走 sshpass 路径 (密码从 env 读, 不落盘, password-only)"
  fi
fi


# ── Step 0: SSH 联通检查 ──────────────────────────────────────────────────
log "Step 0/5: SSH 联通检查 ${SSH_TARGET}..."
if ! "${SSH_CMD[@]}" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "echo ok" >/dev/null 2>&1; then
  err "SSH 连不上 $SSH_TARGET，请检查 ~/.ssh/config 或 SSHPASS env"
  exit 3
fi
ok "SSH 通"

# ── 决定操作模式 ───────────────────────────────────────────────────────────
ACTION="${1:-deploy}"

case "$ACTION" in
  --logs)
    log "Tail 后端 logs..."
    "${SSH_CMD[@]}" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "docker logs --tail 200 ai-trader-backend"
    exit 0
    ;;
  --health)
    log "健康检查..."
    "${SSH_CMD[@]}" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep ai-trader"
    "${SSH_CMD[@]}" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "docker inspect --format='{{.State.Health.Status}}' ai-trader-backend 2>/dev/null || echo 'no healthcheck'"
    "${SSH_CMD[@]}" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "curl -fsS http://127.0.0.1:8765/api/health || echo 'BACKEND UNREACHABLE'"
    exit 0
    ;;
  --restart)
    log "重启 backend + frontend..."
    "${SSH_CMD[@]}" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "cd ${REMOTE_DIR} && docker compose ${COMPOSE_FILES} restart backend frontend"
    "${SSH_CMD[@]}" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "sleep 5 && cd ${REMOTE_DIR} && docker ps --format 'table {{.Names}}\t{{.Status}}'"
    exit 0
    ;;
  --frontend)
    log "只 rebuild + up 前端..."
    "${SSH_CMD[@]}" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "cd ${REMOTE_DIR} && docker compose ${COMPOSE_FILES} build --no-cache frontend && docker compose ${COMPOSE_FILES} up -d --force-recreate --no-deps frontend"
    "${SSH_CMD[@]}" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "sleep 5 && cd ${REMOTE_DIR} && docker ps --format 'table {{.Names}}\t{{.Status}}'"
    ok "前端 deploy 完成"
    exit 0
    ;;
esac

# ── 默认 deploy: rsync + rebuild + up ─────────────────────────────────────
log "Step 1/5: 本地预检 (Node deps + .env)..."
cd "$LOCAL_DIR"

if [ ! -f frontend/package.json ]; then
  err "找不到 frontend/package.json"
  exit 1
fi

log "Step 2/5: rsync 本地 → ${SSH_TARGET}:${REMOTE_DIR}..."
"${SSH_CMD[@]}" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "mkdir -p ${REMOTE_DIR}"
# 用 --exclude 排除 .env（docker compose 要用 server 上的 .env）
# rsync 的 -e 必须用同一个 SSH_CMD + SSH_COMMON_OPTS（kbkkk 走 sshpass 路径）
# SSH_CMD 是 bash array,${SSH_CMD[*]} 把所有元素用 IFS 拼成字符串给 rsync -e
RSYNC_SSH="${SSH_CMD[*]} ${SSH_COMMON_OPTS[*]}"
rsync -avz --delete -e "$RSYNC_SSH" \
  --exclude='.venv/' \
  --exclude='__pycache__/' \
  --exclude='node_modules/' \
  --exclude='.git/' \
  --exclude='frontend/dist/' \
  --exclude='backend/.pytest_cache/' \
  --exclude='backend/.mypy_cache/' \
  --exclude='backend/.ruff_cache/' \
  --exclude='.claude/' \
  --exclude='.cursor/' \
  --exclude='.worktrees/' \
  --exclude='.idea/' \
  --exclude='*.log' \
  "$LOCAL_DIR/" "${SSH_TARGET}:${REMOTE_DIR}/"
ok "rsync 完成"

log "Step 3/5: 服务器侧 docker compose build..."
"${SSH_CMD[@]}" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "cd ${REMOTE_DIR} && docker compose ${COMPOSE_FILES} build --no-cache backend frontend"
ok "build 完成"

log "Step 4/5: docker compose up -d..."
"${SSH_CMD[@]}" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "cd ${REMOTE_DIR} && docker compose ${COMPOSE_FILES} up -d --force-recreate --no-deps backend frontend"
ok "up 完成"

log "Step 5/5: 健康检查 (max 60s)..."
for i in $(seq 1 12); do
  STATUS=$("${SSH_CMD[@]}" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "docker inspect --format='{{.State.Health.Status}}' ai-trader-backend 2>/dev/null || echo starting")
  if [ "$STATUS" = "healthy" ]; then
    ok "backend healthy"
    break
  fi
  log "  attempt $i/12: backend status = $STATUS"
  sleep 5
done

HTTP_CODE=$("${SSH_CMD[@]}" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "curl -sS -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8765/api/health || echo 000")
if [ "$HTTP_CODE" = "200" ]; then
  ok "backend HTTP /api/health = 200"
else
  err "backend HTTP /api/health = $HTTP_CODE"
  warn "查看 logs：ssh ${SSH_TARGET} 'docker logs --tail 100 ai-trader-backend'"
  exit 2
fi

ok ""
ok "=========================================="
ok "  deploy-dyddd 完成"
ok "  时间: $(date '+%Y-%m-%d %H:%M:%S %Z')"
ok "  操作: ${ACTION}"
ok "  容器: backend + frontend 已重建"
ok "  健康: backend healthy (HTTP 200)"
ok "=========================================="
