#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────
# ai-trader 一键部署脚本 (ssh dyddd-prod)
# 用法:
#   bash scripts/deploy.sh                # 默认 deploy (rebuild + up)
#   bash scripts/deploy.sh --restart      # 只 restart backend/frontend
#   bash scripts/deploy.sh --logs         # 看后端最近 200 行 logs
#   bash scripts/deploy.sh --health       # 只做健康检查
#   bash scripts/deploy.sh --frontend     # 只 rebuild + up 前端
#
# SSH 别名: dyddd-prod (需要 ~/.ssh/config 配好)
# 部署路径: /opt/ai-trader/ai-trader/
# ──────────────────────────────────────────────────────────────────────────
set -e

SSH_TARGET="${SSH_TARGET:-dyddd-prod}"
REMOTE_DIR="/opt/ai-trader/ai-trader"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE="${PROFILE:-default}"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

log()  { echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} $1"; }
ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
err()  { echo -e "${RED}✗${NC} $1"; }

# ── Step 0: SSH 联通检查 ──────────────────────────────────────────────────
log "Step 0/5: SSH 联通检查 ${SSH_TARGET}..."
if ! ssh -o ConnectTimeout=10 -o BatchMode=yes "$SSH_TARGET" "echo ok" >/dev/null 2>&1; then
  err "SSH 连不上 $SSH_TARGET，请检查 ~/.ssh/config"
  exit 3
fi
ok "SSH 通"

# ── 决定操作模式 ───────────────────────────────────────────────────────────
ACTION="${1:-deploy}"

case "$ACTION" in
  --logs)
    log "Tail 后端 logs..."
    ssh "$SSH_TARGET" "docker logs --tail 200 ai-trader-backend"
    exit 0
    ;;
  --health)
    log "健康检查..."
    ssh "$SSH_TARGET" "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep ai-trader"
    ssh "$SSH_TARGET" "docker inspect --format='{{.State.Health.Status}}' ai-trader-backend 2>/dev/null || echo 'no healthcheck'"
    ssh "$SSH_TARGET" "curl -fsS http://127.0.0.1:8765/api/health || echo 'BACKEND UNREACHABLE'"
    exit 0
    ;;
  --restart)
    log "重启 backend + frontend..."
    ssh "$SSH_TARGET" "cd ${REMOTE_DIR} && docker compose restart backend frontend"
    ssh "$SSH_TARGET" "sleep 5 && cd ${REMOTE_DIR} && docker ps --format 'table {{.Names}}\t{{.Status}}'"
    exit 0
    ;;
  --frontend)
    log "只 rebuild + up 前端..."
    ssh "$SSH_TARGET" "cd ${REMOTE_DIR} && docker compose build --no-cache frontend && docker compose up -d --force-recreate --no-deps frontend"
    ssh "$SSH_TARGET" "sleep 5 && cd ${REMOTE_DIR} && docker ps --format 'table {{.Names}}\t{{.Status}}'"
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
ssh "$SSH_TARGET" "mkdir -p ${REMOTE_DIR}"
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
ssh "$SSH_TARGET" "cd ${REMOTE_DIR} && docker compose build --no-cache backend frontend"
ok "build 完成"

log "Step 4/5: docker compose up -d..."
ssh "$SSH_TARGET" "cd ${REMOTE_DIR} && docker compose up -d --force-recreate --no-deps backend frontend"
ok "up 完成"

log "Step 5/5: 健康检查 (max 60s)..."
for i in $(seq 1 12); do
  STATUS=$(ssh "$SSH_TARGET" "docker inspect --format='{{.State.Health.Status}}' ai-trader-backend 2>/dev/null || echo starting")
  if [ "$STATUS" = "healthy" ]; then
    ok "backend healthy"
    break
  fi
  log "  attempt $i/12: backend status = $STATUS"
  sleep 5
done

HTTP_CODE=$(ssh "$SSH_TARGET" "curl -sS -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8765/api/health || echo 000")
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
