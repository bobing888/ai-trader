#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────
# ai-trader 一键部署脚本 (ssh dyddd-prod)
# 用法:
#   bash scripts/deploy.sh                # 默认 deploy (rebuild + up)
#   bash scripts/deploy.sh --restart      # 只 restart backend/frontend
#   bash scripts/deploy.sh --logs         # 看后端最近 200 行 logs
#   bash scripts/deploy.sh --health       # 只做健康检查
#   bash scripts/deploy.sh --frontend     # 只 rebuild + up 前端
#   bash scripts/deploy.sh --preload      # 只预拉基础镜像
#
# SSH 别名: dyddd-prod (需要 ~/.ssh/config 配好)
# 部署路径: /opt/ai-trader/ai-trader/
#
# 性能优化 (2026-09-27+):
#   - BuildKit type=local cache mount (target ~40s vs 3min)
#   - 基础镜像 preloaded 到服务器本地，避免 deploy 中途 pull 卡死
#   - Dockerfile 多阶段 + .dockerignore，避免 .pytest_cache 等垃圾进 context
# ──────────────────────────────────────────────────────────────────────────
set -e

SSH_TARGET="${SSH_TARGET:-dyddd-prod}"
REMOTE_DIR="/opt/ai-trader/ai-trader"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE="${PROFILE:-default}"

# BuildKit 缓存目录 — 默认就是 /var/lib/docker/buildkit
# 我们明确指定是因为镜像自动 GC 可能清掉（2026-09-27 决策）
REMOTE_BUILDKIT_CACHE="${REMOTE_BUILDKIT_CACHE:-/var/lib/docker/buildkit}"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

log()  { echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} $1"; }
ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
err()  { echo -e "${RED}✗${NC} $1"; }

# ── Step 0: SSH 联通检查 ──────────────────────────────────────────────────
log "Step 0/6: SSH 联通检查 ${SSH_TARGET}..."
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
    ssh "$SSH_TARGET" "cd ${REMOTE_DIR} && BUILDKIT_CACHE_DIR=${REMOTE_BUILDKIT_CACHE} docker buildx build --target runtime \
      --cache-from type=local,src=${REMOTE_BUILDKIT_CACHE} \
      --cache-to type=local,dest=${REMOTE_BUILDKIT_CACHE},mode=max \
      --build-arg BUILDKIT_INLINE_CACHE=1 \
      -f frontend/Dockerfile frontend/ \
      -t ai-trader-frontend:latest --load"
    ssh "$SSH_TARGET" "cd ${REMOTE_DIR} && docker compose up -d --force-recreate --no-deps frontend"
    ssh "$SSH_TARGET" "sleep 5 && cd ${REMOTE_DIR} && docker ps --format 'table {{.Names}}\t{{.Status}}'"
    ok "前端 deploy 完成"
    exit 0
    ;;
  --preload)
    log "预拉基础镜像..."
    ssh "$SSH_TARGET" "cd ${REMOTE_DIR} && bash scripts/preload-base-images.sh"
    exit 0
    ;;
esac

# ── 默认 deploy: rsync + preload + cached build + up ──────────────────────

log "Step 1/6: 本地预检 (Dockerfile + .dockerignore + .env)..."
cd "$LOCAL_DIR"

if [ ! -f frontend/package.json ]; then
  err "找不到 frontend/package.json"
  exit 1
fi

# 验证 Dockerfile 用了 BuildKit cache mount（不需要 # syntax 指令）
if ! grep -q "type=cache" backend/Dockerfile frontend/Dockerfile 2>/dev/null; then
  warn "Dockerfile 缺 RUN --mount=type=cache — 不会启用 BuildKit cache 复用"
fi

# 把 preload 脚本也 rsync 过去
log "Step 2/6: rsync 本地 → ${SSH_TARGET}:${REMOTE_DIR}..."
ssh "$SSH_TARGET" "mkdir -p ${REMOTE_DIR}"
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

# 预拉基础镜像 — 必须在 build 之前
log "Step 3/6: 预拉基础镜像..."
ssh "$SSH_TARGET" "cd ${REMOTE_DIR} && bash scripts/preload-base-images.sh" || {
  err "预拉基础镜像失败 — 检查 docker.io 访问"
  exit 1
}

# BuildKit 默认就复用 docker cache（~17 GB 已累积）
# 注意：保留 --no-cache 暂时不动！原因 (2026-09-27 验证):
#   1. nginx:1.27-alpine / node:20-alpine 在 server 没有 named tag
#   2. docker.io HEAD 总是 timeout（GFW），build 会 fail
#   3. --no-cache 是「确保 build 100% 成功」的保险策略
# 下一版 (用户配 registry-mirrors 后)：drop --no-cache 启用 cache 复用
log "Step 4/6: docker compose build (--no-cache 保守策略)..."
ssh "$SSH_TARGET" "cd ${REMOTE_DIR} && docker compose build --no-cache backend frontend"
ok "build 完成"

log "Step 5/6: docker compose up -d..."
ssh "$SSH_TARGET" "cd ${REMOTE_DIR} && docker compose up -d --force-recreate --no-deps backend frontend"
ok "up 完成"

log "Step 6/6: 健康检查 (max 60s)..."
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
  warn "查看 logs: ssh ${SSH_TARGET} 'docker logs --tail 100 ai-trader-backend'"
  exit 2
fi

# 看 build cache 占用
CACHE_USAGE=$(ssh "$SSH_TARGET" "du -sh ${REMOTE_BUILDKIT_CACHE} 2>/dev/null | cut -f1")

ok ""
ok "=========================================="
ok "  deploy-dyddd 完成"
ok "  时间: $(date '+%Y-%m-%d %H:%M:%S %Z')"
ok "  操作: ${ACTION}"
ok "  容器: backend + frontend 已重建"
ok "  健康: backend healthy (HTTP 200)"
ok "  BuildKit cache: ${CACHE_USAGE:-未启用}"
ok "=========================================="
