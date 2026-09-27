#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────
# ai-trader 一键部署到 kbkkk-prod (206.187.211.211) — sshpass 密码模式
# 复用 scripts/deploy.sh 的步骤，但 SSH_TARGET=kbkkk-prod + 走 sshpass
# 部署目录：/opt/ai-trader/ai-trader/
# ──────────────────────────────────────────────────────────────────────────
set -e

SSH_TARGET="kbkkk-prod"
REMOTE_DIR="/opt/ai-trader/ai-trader"
STAGING_DIR="/opt/ai-trader-staging"
BACKUP_DIR="/opt/ai-trader-backup"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
KBKKK_PASS='9Q35cnE2s7DX"

# BuildKit 缓存目录（kbkkk 服务器本地，默认 docker buildkit 路径）
REMOTE_BUILDKIT_CACHE="${REMOTE_BUILDKIT_CACHE:-/var/lib/docker/buildkit}"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1,33m'; BLUE='\033[0,34m'; NC='\033[0m'
log()  { echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} $1"; }
ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
err()  { echo -e "${RED}✗${NC} $1"; }

# ── sshpass wrapper ────────────────────────────────────────────────────────
ssh_k() {
  sshpass -p "$KBKKK_PASS" ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 \
    -o NumberOfPasswordPrompts=1 "$SSH_TARGET" "$@"
}
rsync_k() {
  sshpass -p "$KBKKK_PASS" rsync -avz --delete \
    -e "ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -o NumberOfPasswordPrompts=1" \
    "$@"
}

# ── Step 0: SSH 联通检查 ──────────────────────────────────────────────────
log "Step 0/6: SSH 联通检查 ${SSH_TARGET}..."
if ! ssh_k "echo ok" >/dev/null 2>&1; then
  err "SSH 连不上 $SSH_TARGET，请检查 ~/.ssh/dyddd_host211_config 或密码"
  exit 3
fi
ok "SSH 通"

# ── Step 1: 本地预检 ──────────────────────────────────────────────────────
log "Step 1/6: 本地预检..."
cd "$LOCAL_DIR"
[ -f frontend/package.json ] || { err "找不到 frontend/package.json"; exit 1; }
ok "本地代码 OK"

# ── Step 2: rsync 本地 → staging ─────────────────────────────────────────
log "Step 2/6: rsync 本地 → ${SSH_TARGET}:${STAGING_DIR}..."
ssh_k "rm -rf ${STAGING_DIR} && mkdir -p ${STAGING_DIR}"
rsync_k \
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
  "$LOCAL_DIR/" "${SSH_TARGET}:${STAGING_DIR}/" >/dev/null
ok "rsync 完成"

# ── Step 3: 原子 swap (mv 老的到 backup, mv staging → 目标) ──────────────
log "Step 3/6: 原子 swap..."
ssh_k "
  set -e
  if [ -d ${REMOTE_DIR} ]; then
    rm -rf ${BACKUP_DIR}
    mv ${REMOTE_DIR} ${BACKUP_DIR}
    echo 'old moved to backup'
  fi
  mv ${STAGING_DIR} ${REMOTE_DIR}
  echo 'swap done'
"
ok "swap 完成 (backup=${BACKUP_DIR})"

# ── Step 4: 预拉基础镜像 + BuildKit 增量 build ────────────────────────────
log "Step 4/7: 预拉基础镜像..."
ssh_k "cd ${REMOTE_DIR} && bash scripts/preload-base-images.sh" || {
  err "预拉基础镜像失败 — 检查 docker.io 访问"
  exit 1
}

# BuildKit 默认走 docker cache. 2026-09-27 决定: 暂时保留 plain docker compose build (--no-cache 见下)
# 因为 nginx:1.27-alpine 在 server 没有 named tag, docker.io HEAD timeout 会 fail.
# preload step (上一行) 是 warm-up 备用, 当 named tag 配齐后下次 PR 可 drop --no-cache
log "Step 5/7: docker compose build (保守 --no-cache)..."
ssh_k "cd ${REMOTE_DIR} && docker compose -f docker-compose.yml -f docker-compose.kbkkk.yml build --no-cache backend frontend" 2>&1 | tail -5
ok "build 完成"

# ── Step 6: kbkkk 端额外 patch（compose ports/volumes 是 additive merge）────
#    override 不能删主 compose 里的 80:80 + 443:443 + ssl volume, 必须 sed
#    但 ports 字段不能为空 (yaml 验证会拒), 改成 127.0.0.1:8123:80
log "Step 6/7: kbkkk 端 sed 改主 compose frontend ports/volumes (override merge 是 additive)..."
ssh_k "bash -s" << 'KBKKK_PATCH'
set -e
F=/opt/ai-trader/ai-trader/docker-compose.yml
cp -a "$F" "$F.kbkkk.original"

# 1) frontend ports: "80:80" + "443:443" → "127.0.0.1:8123:80" (kbkkk 外部 nginx 反代 80→8123)
#    只在 frontend 块内改
python3 << 'PYEOF'
import re
p='/opt/ai-trader/ai-trader/docker-compose.yml'
s=open(p).read()
def repl(m):
    block=m.group(0)
    # 80:80 + 443:443 → 替换为 127.0.0.1:8123:80 一行
    block=re.sub(
        r'    ports:\n      - "80:80"\n      - "443:443"',
        '    ports:\n      - "127.0.0.1:8123:80"  # kbkkk-prod: 外部 nginx 反代 80→8123',
        block
    )
    return block
new=re.sub(r'  frontend:.*?(?=\nvolumes:|\Z)', repl, s, flags=re.DOTALL)
print('ports patched' if new!=s else 'ports NO MATCH')
open(p,'w').write(new)
PYEOF

# 2) frontend volumes: 删整个 volumes: 字段 (kbkkk 不挂 ssl)
python3 << 'PYEOF'
import re
p='/opt/ai-trader/ai-trader/docker-compose.yml'
s=open(p).read()
def repl(m):
    block=m.group(0)
    # 删整个 volumes: 字段 + 子项 (只对 frontend 块, 因为只剩这一处)
    block=re.sub(r'\n    volumes:\n      - /etc/nginx/ssl:/etc/nginx/ssl:ro','',block)
    return block
new=re.sub(r'  frontend:.*?(?=\nvolumes:|\Z)', repl, s, flags=re.DOTALL)
print('volumes patched' if new!=s else 'volumes NO MATCH')
open(p,'w').write(new)
PYEOF

echo "--- patch 后 frontend 块 ---"
sed -n '/^  frontend:/,/^volumes:/p' "$F" | head -20
KBKKK_PATCH
ok "kbkkk 端 compose patch 完成"

# ── Step 7: docker compose up ────────────────────────────────────────────
log "Step 7/7: docker compose up -d (kbkkk override)..."
ssh_k "cd ${REMOTE_DIR} && docker compose -f docker-compose.yml -f docker-compose.kbkkk.yml up -d --force-recreate --no-deps backend frontend" 2>&1 | tail -15
ok "up 完成"

# ── 健康检查（不计入步骤编号）────────────────────────────────────────────
log "[health] 健康检查 (max 90s)..."
HEALTHY=false
for i in $(seq 1 18); do
  STATUS=$(ssh_k "docker inspect --format='{{.State.Health.Status}}' ai-trader-backend 2>/dev/null || echo starting")
  if [ "$STATUS" = "healthy" ]; then
    ok "backend healthy (attempt $i/18)"
    HEALTHY=true
    break
  fi
  log "  attempt $i/18: backend status = $STATUS"
  sleep 5
done

if [ "$HEALTHY" = "false" ]; then
  err "backend 未在 90s 内 healthy，自动 rollback"
  ssh_k "cd ${BACKUP_DIR} && docker compose up -d --force-recreate --no-deps backend frontend" 2>&1 | tail -5
  ssh_k "docker logs --tail 100 ai-trader-backend" 2>&1 | tail -40
  exit 2
fi

HTTP_CODE=$(ssh_k "curl -sS -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8765/api/health || echo 000")
if [ "$HTTP_CODE" = "200" ]; then
  ok "backend HTTP /api/health = 200"
else
  err "backend HTTP /api/health = $HTTP_CODE"
  exit 2
fi

ok ""
ok "=========================================="
ok "  deploy-kbkkk 完成"
ok "  时间: $(date '+%Y-%m-%d %H:%M:%S %Z')"
ok "  操作: deploy (atomic swap + rebuild)"
ok "  容器: backend + frontend 已重建"
ok "  健康: backend healthy (HTTP 200)"
ok "  备份: ${BACKUP_DIR} (可手动 rollback)"
ok "=========================================="