#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────
# preload-base-images.sh
#
# 预拉/检查 ai-trader 用到的所有基础镜像到服务器本地，避免 deploy 时
# docker pull 卡住/被 GFW 拦截。
#
# 触发场景:
#   1. deploy.sh 默认 deploy 时会自动调用（在 rsync 之后、build 之前）
#   2. 手动可独立调用：
#        ssh dyddd-prod 'bash /opt/ai-trader/ai-trader/scripts/preload-base-images.sh'
#
# 镜像清单（与 backend/Dockerfile + frontend/Dockerfile FROM 行对齐）:
#   - python:3.12-slim        (backend runtime)
#   - node:20-alpine          (frontend builder)
#   - nginx:1.27-alpine       (frontend runtime)
#
# 现实约束 (2026-09-27 验证):
#   - 服务器 docker.io 直连经常 timeout（GFW）
#   - BuildKit cache 已累积 ~17 GB 的历史 build 层（包含旧 base image）
#   - 默认 registry-mirrors 是空，没配镜像源
#   - 本脚本不能动 /etc/docker/daemon.json（红线 2，权限外）
# ──────────────────────────────────────────────────────────────────────────
set -e

# 镜像清单 — 同步修改方式: 改 Dockerfile 后必须同步这里
IMAGES=(
    "python:3.12-slim"
    "node:20-alpine"
    "nginx:1.27-alpine"
)

# BuildKit cache 路径（与 docker 默认一致，复用现有 ~17 GB 层）
BUILDKIT_CACHE_DIR="${BUILDKIT_CACHE_DIR:-/var/lib/docker/buildkit}"

log()  { echo -e "\033[0;34m[$(date +%H:%M:%S)]\033[0m $1"; }
ok()   { echo -e "\033[0;32m✓\033[0m $1"; }
warn() { echo -e "\033[0;33m⚠\033[0m $1"; }
err()  { echo -e "\033[0;31m✗\033[0m $1"; }

# ── Step 1: 检查 BuildKit cache 状态 ─────────────────────────────────────
log "Step 1/3: 检查 BuildKit cache 目录 $BUILDKIT_CACHE_DIR ..."
if [ -d "$BUILDKIT_CACHE_DIR" ]; then
    USAGE=$(du -sh "$BUILDKIT_CACHE_DIR" 2>/dev/null | cut -f1)
    ok "BuildKit cache 就绪，累积 $USAGE — 后续 deploy 会复用历史层"
else
    warn "BuildKit cache 目录不存在（首次 deploy 会拉基础镜像）"
fi

# ── Step 2: 检查每个基础镜像 tag ─────────────────────────────────────────
log "Step 2/3: 检查基础镜像 tag..."
PULLED=0
SKIPPED=0
for img in "${IMAGES[@]}"; do
    if docker image inspect "$img" >/dev/null 2>&1; then
        SIZE=$(docker image inspect --format '{{.Size}}' "$img" 2>/dev/null)
        ok "  $img — named tag 存在 ($(numfmt --to=iec $SIZE))"
        SKIPPED=$((SKIPPED+1))
    else
        warn "  $img — named tag 缺失（BuildKit cache 里可能有 cached layer）"
        # 不主动 pull，因为 docker.io 在服务器直连不通
        # 让 docker buildx 自己从 BuildKit cache 复用，找不到再 fail
        warn "  BuildKit cache 命中即可，跳过 pull（避免 timeout）"
    fi
done

# ── Step 3: 报告 ─────────────────────────────────────────────────────────
log "Step 3/3: 摘要"
ok "基础镜像 named tag: $SKIPPED/${#IMAGES[@]} (cached layer 由 BuildKit 自动复用)"

# docker.io 可达性检查（仅警告，不阻塞）
echo ""
if timeout 5 docker pull hello-world >/dev/null 2>&1; then
    ok "docker.io 可达 — 后续需要新基础镜像时能正常 pull"
else
    warn "docker.io 不可达（GFW 拦截）— 只能靠 BuildKit cache 复用旧层"
    warn "  fallback: 让用户配 /etc/docker/daemon.json 的 registry-mirrors"
fi

# 镜像列表
echo ""
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}" \
    | grep -E "REPOSITORY|^(python|node|nginx|ai-trader|redis)" | head -10
