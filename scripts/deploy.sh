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
set -e

SSH_TARGET="${SSH_TARGET:-kbkkk-prod}"
REMOTE_DIR="/opt/ai-trader/ai-trader"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE="${PROFILE:-default}"

# ── ssh wrapper: kbkkk-prod 走 sshpass (skill ssh-prod-credentials §1.B) ──
# 用户提供 SSHPASS 或 KBKKK_PASS 环境变量时,自动用 sshpass 包装 ssh 调用.
# 这样 deploy.sh 在 PRIMARY (kbkkk-prod) 上也能用,无需 ~/.ssh/config.
SSH_CMD="ssh"
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
if [[ "$SSH_TARGET" == "kbkkk-prod" ]] && command -v sshpass >/dev/null 2>&1; then
  if [[ -n "${SSHPASS:-}${KBKKK_PASS:-}" ]]; then
    # 用临时文件方式喂密码(避免 -e 在 ssh 子进程里丢失 env)
    _sshpass_pw_file="$(mktemp -t kbkkk-sshpass.XXXXXX)"
    chmod 600 "$_sshpass_pw_file"
    printf '%s' "${SSHPASS:-${KBKKK_PASS}}" > "$_sshpass_pw_file"
    SSH_CMD="sshpass -f $_sshpass_pw_file ssh"
    trap 'rm -f "$_sshpass_pw_file"' EXIT
    export SSHPASS="${SSHPASS:-${KBKKK_PASS}}"  # 让 sshpass -e 也可用
    log "kbkkk-prod: 走 sshpass 路径 (密码从 env 读, 不落盘, password-only)"
  fi
fi

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

log()  { echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} $1"; }
ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
err()  { echo -e "${RED}✗${NC} $1"; }

# ── Step 0: SSH 联通检查 ──────────────────────────────────────────────────
log "Step 0/5: SSH 联通检查 ${SSH_TARGET}..."
if ! "$SSH_CMD" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "echo ok" >/dev/null 2>&1; then
  err "SSH 连不上 $SSH_TARGET，请检查 ~/.ssh/config 或 SSHPASS env"
  exit 3
fi
ok "SSH 通"

# ── 决定操作模式 ───────────────────────────────────────────────────────────
ACTION="${1:-deploy}"

case "$ACTION" in
  --logs)
    log "Tail 后端 logs..."
    "$SSH_CMD" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "docker logs --tail 200 ai-trader-backend"
    exit 0
    ;;
  --health)
    log "健康检查..."
    "$SSH_CMD" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep ai-trader"
    "$SSH_CMD" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "docker inspect --format='{{.State.Health.Status}}' ai-trader-backend 2>/dev/null || echo 'no healthcheck'"
    "$SSH_CMD" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "curl -fsS http://127.0.0.1:8765/api/health || echo 'BACKEND UNREACHABLE'"
    exit 0
    ;;
  --restart)
    log "重启 backend + frontend..."
    "$SSH_CMD" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "cd ${REMOTE_DIR} && docker compose restart backend frontend"
    "$SSH_CMD" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "sleep 5 && cd ${REMOTE_DIR} && docker ps --format 'table {{.Names}}\t{{.Status}}'"
    exit 0
    ;;
  --frontend)
    log "只 rebuild + up 前端..."
    "$SSH_CMD" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "cd ${REMOTE_DIR} && docker compose build --no-cache frontend && docker compose up -d --force-recreate --no-deps frontend"
    "$SSH_CMD" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "sleep 5 && cd ${REMOTE_DIR} && docker ps --format 'table {{.Names}}\t{{.Status}}'"
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
"$SSH_CMD" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "mkdir -p ${REMOTE_DIR}"
# 用 --exclude 排除 .env（docker compose 要用 server 上的 .env）
rsync -avz --delete \
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
  --exclude='.idea/' \
  --exclude='*.log' \
  "$LOCAL_DIR/" "${SSH_TARGET}:${REMOTE_DIR}/"
ok "rsync 完成"

log "Step 3/5: 服务器侧 docker compose build..."
"$SSH_CMD" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "cd ${REMOTE_DIR} && docker compose build --no-cache backend frontend"
ok "build 完成"

log "Step 4/5: docker compose up -d..."
"$SSH_CMD" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "cd ${REMOTE_DIR} && docker compose up -d --force-recreate --no-deps backend frontend"
ok "up 完成"

log "Step 5/5: 健康检查 (max 60s)..."
for i in $(seq 1 12); do
  STATUS=$("$SSH_CMD" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "docker inspect --format='{{.State.Health.Status}}' ai-trader-backend 2>/dev/null || echo starting")
  if [ "$STATUS" = "healthy" ]; then
    ok "backend healthy"
    break
  fi
  log "  attempt $i/12: backend status = $STATUS"
  sleep 5
done

HTTP_CODE=$("$SSH_CMD" "${SSH_COMMON_OPTS[@]}" "$SSH_TARGET" "curl -sS -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8765/api/health || echo 000")
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
