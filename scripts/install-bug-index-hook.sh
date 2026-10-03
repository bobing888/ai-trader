#!/usr/bin/env bash
# scripts/install-bug-index-hook.sh — opt-in 安装 bug-case-index pre-commit 提醒
#
# 用法:
#   ./scripts/install-bug-index-hook.sh install   # 软模式（30s 倒计时，可放行）
#   BUG_INDEX_HARD_BLOCK=1 ./scripts/install-bug-index-hook.sh install  # 硬模式（CI 严格）
#   ./scripts/install-bug-index-hook.sh uninstall
#   ./scripts/install-bug-index-hook.sh status
#
# 工作原理:
#   - 在 .git/hooks/pre-commit 末尾追加 bug-index reminder 段（protect-main 段保留）
#   - 触发时: 改 backend/frontend/scripts/Dockerfile 关键路径但没改 bug-case-index.md
#     → 30s 倒计时 + 提示按 4-Step SOP 更新
#   - 软模式默认: 倒计时结束自动放行（不打扰开发节奏）
#   - 硬模式 (CI): BUG_INDEX_HARD_BLOCK=1 直接 exit 1 阻断
#   - 紧急跳过: git commit 时 SKIP_BUG_INDEX=1
#
# 设计原则: 默认 opt-in，避免 agent/开发者被突然的 hook 卡住。
#           AGENTS.md 规则 13 强制要求"每次改文件后报告效果"，
#           这个 hook 是它的执行机制（防止漏报）。

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"
HOOKS_DIR="$REPO_ROOT/.git/hooks"
BUG_HOOK_SRC="/Users/hahaha/.cursor/skills/scripts/hook-pre-commit-bug-index.sh"
MARKER_BEGIN="# >>> bug-index-reminder BEGIN >>>"
MARKER_END="# <<< bug-index-reminder END <<<"
MODE="${1:-status}"
MODE_HARD="${BUG_INDEX_HARD_BLOCK:-0}"

uninstall_block() {
  local f="$HOOKS_DIR/pre-commit"
  [[ -f "$f" ]] || return 0
  local tmp
  tmp="$(mktemp)"
  awk -v begin="$MARKER_BEGIN" -v end="$MARKER_END" '
    $0 ~ begin { skip=1 }
    skip==1 && $0 ~ end { skip=0; next }
    skip==1 { next }
    { print }
  ' "$f" > "$tmp"
  if [[ ! -s "$tmp" ]] || ! grep -q '[^[:space:]]' "$tmp"; then
    rm -f "$f"
  else
    mv "$tmp" "$f"
    chmod +x "$f" 2>/dev/null || true
  fi
}

case "$MODE" in
  install)
    if [[ ! -f "$BUG_HOOK_SRC" ]]; then
      echo "✗ 未找到 $BUG_HOOK_SRC" >&2
      exit 1
    fi
    mkdir -p "$HOOKS_DIR"
    # 先清掉旧 block
    uninstall_block
    # 根据 MODE_HARD 决定写哪种模式
    if [[ "$MODE_HARD" = "1" ]]; then
      MODE_TAG="hard"
    else
      MODE_TAG="soft"
    fi
    # 追加新 block（在 protect-main 段之后）
    # 硬模式: hook 段自带 export，绕过外部 env 设置
    if [[ "$MODE_HARD" = "1" ]]; then
      cat >> "$HOOKS_DIR/pre-commit" <<EOF

$MARKER_BEGIN
# bug-case-index 提醒: 改 backend/frontend/scripts 但没改
# /Users/hahaha/.cursor/skills/experience-refinement/reference/bug-case-index.md
# 时,触发 30s 倒计时 + 4-Step SOP 提示。
# 模式: hard (CI 严格 — 缺更新直接 exit 1)
# 单次跳过: SKIP_BUG_INDEX=1 git commit ...
# 卸载: ./scripts/install-bug-index-hook.sh uninstall
# 详见: /Users/hahaha/.cursor/skills/scripts/hook-pre-commit-bug-index.sh
export BUG_INDEX_HARD_BLOCK=1
bash "$BUG_HOOK_SRC"
$MARKER_END
EOF
    else
      cat >> "$HOOKS_DIR/pre-commit" <<EOF

$MARKER_BEGIN
# bug-case-index 提醒: 改 backend/frontend/scripts 但没改
# /Users/hahaha/.cursor/skills/experience-refinement/reference/bug-case-index.md
# 时,触发 30s 倒计时 + 4-Step SOP 提示。
# 模式: soft (默认 — 30s 倒计时 + 可放行)
# 单次跳过: SKIP_BUG_INDEX=1 git commit ...
# 临时切硬:   BUG_INDEX_HARD_BLOCK=1 git commit ...
# 卸载:       ./scripts/install-bug-index-hook.sh uninstall
# 详见: /Users/hahaha/.cursor/skills/scripts/hook-pre-commit-bug-index.sh
bash "$BUG_HOOK_SRC"
$MARKER_END
EOF
    fi
    chmod +x "$HOOKS_DIR/pre-commit"
    if [[ "$MODE_HARD" = "1" ]]; then
      echo "✓ 已安装 bug-index hook（硬模式: 缺更新时直接 exit 1）"
      echo "  注意: 硬模式需要 export BUG_INDEX_HARD_BLOCK=1 才能生效,例如:"
      echo "    BUG_INDEX_HARD_BLOCK=1 git commit ..."
    else
      echo "✓ 已安装 bug-index hook（软模式: 30s 倒计时 + 可放行）"
      echo "  跳过单次 commit: SKIP_BUG_INDEX=1 git commit ..."
      echo "  临时切硬模式:   BUG_INDEX_HARD_BLOCK=1 git commit ..."
    fi
    echo "  卸载: ./scripts/install-bug-index-hook.sh uninstall"
    ;;

  uninstall)
    uninstall_block
    echo "✓ 已卸载 bug-index hook"
    ;;

  status)
    f="$HOOKS_DIR/pre-commit"
    if [[ -f "$f" ]] && grep -q "bug-index-reminder BEGIN" "$f"; then
      echo "bug-index hook: ✓ 已安装"
      # 读注释里的模式标记
      mode_line=$(grep -E "^# 模式: " "$f" 2>/dev/null | head -1)
      mode=$(echo "$mode_line" | awk -F': ' '{print $2}')
      if [[ "$mode" = "hard" ]]; then
        echo "  模式: 硬模式（BUG_INDEX_HARD_BLOCK=1 时直接 exit 1）"
      else
        echo "  模式: 软模式（默认: 30s 倒计时 + 可放行）"
      fi
    else
      echo "bug-index hook: ✗ 未安装"
      echo "  安装: ./scripts/install-bug-index-hook.sh install"
    fi
    ;;

  *)
    echo "用法: $0 {install|uninstall|status}" >&2
    echo "  硬模式安装: BUG_INDEX_HARD_BLOCK=1 $0 install" >&2
    exit 1
    ;;
esac
