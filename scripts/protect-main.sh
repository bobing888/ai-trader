#!/usr/bin/env bash
# scripts/protect-main.sh — 安装/卸载本地 main 分支保护 hook
#
# 用法:
#   ./scripts/protect-main.sh install   # 安装 pre-commit + pre-push + commit-msg + post-checkout hook
#   ./scripts/protect-main.sh uninstall # 卸载(只清掉本脚本写入的 hook)
#   ./scripts/protect-main.sh status    # 当前保护状态
#
# 实现的功能:
#   - main 上直接 git commit → 拒绝(强制走 feature 分支)
#   - main 上 git push --force-with-lease / --force / +main:* → 拒绝
#   - main 上直接 git push(非 PR 流程)→ 警告(可选,默认 warn-only)
#
# 受保护分支(可通过环境变量覆盖):
#   MAIN_BRANCH=main ./scripts/protect-main.sh install
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

MAIN_BRANCH="${MAIN_BRANCH:-main}"
HOOKS_DIR="$REPO_ROOT/.git/hooks"
MARKER_BEGIN="# >>> protect-main.sh BEGIN >>>"
MARKER_END="# <<< protect-main.sh END <<<"

cmd="${1:-status}"

uninstall_hook() {
  local hook="$1"
  local f="$HOOKS_DIR/$hook"
  [[ -f "$f" ]] || return 0
  # 删除 MARKER_BEGIN 到 MARKER_END 之间的所有行(含两端),简单可靠
  local tmp
  tmp="$(mktemp)"
  awk -v begin="$MARKER_BEGIN" -v end="$MARKER_END" '
    $0 ~ begin { skip=1 }
    skip==1 && $0 ~ end { skip=0; next }
    skip==1 { next }
    { print }
  ' "$f" > "$tmp"
  # 如果文件剩下来只有空白行,直接删;否则覆盖
  if [[ ! -s "$tmp" ]] || ! grep -q '[^[:space:]]' "$tmp"; then
    rm -f "$f"
  else
    mv "$tmp" "$f"
    chmod +x "$f" 2>/dev/null || true
  fi
}

write_pre_commit() {
  local f="$HOOKS_DIR/pre-commit"
  uninstall_hook "pre-commit"
  cat >> "$f" <<EOF

$MARKER_BEGIN
# 分支保护:禁止在 $MAIN_BRANCH 上直接 commit。
# 请先 ./scripts/new-branch.sh <topic> 切出 feature 分支。
PROTECTED_BRANCHES="$MAIN_BRANCH" "\$(dirname "\$0")/../../.githooks/pre-commit-block"
$MARKER_END
EOF
  chmod +x "$f"
}

write_pre_push() {
  local f="$HOOKS_DIR/pre-push"
  uninstall_hook "pre-push"
  cat >> "$f" <<EOF

$MARKER_BEGIN
# 分支保护:禁止 force push 到 $MAIN_BRANCH,也禁止直接 push $MAIN_BRANCH。
# 合入请走 PR 流程(git push -u origin feat/<topic> → 提 PR → 合入 $MAIN_BRANCH)。
PROTECTED_BRANCHES="$MAIN_BRANCH" "\$(dirname "\$0")/../../.githooks/pre-push-block"
$MARKER_END
EOF
  chmod +x "$f"
}

write_commit_msg() {
  local f="$HOOKS_DIR/commit-msg"
  uninstall_hook "commit-msg"
  cat >> "$f" <<EOF

$MARKER_BEGIN
# (空块,主规则已在 pre-commit 中拦截。保留此 hook 以便后续加 commit message 规范。)
$MARKER_END
EOF
  chmod +x "$f"
}

case "$cmd" in
  install)
    mkdir -p "$HOOKS_DIR"
    # 写真正的 hook 逻辑到 .githooks/ 下(随仓库追踪),hook 文件只做 dispatch
    mkdir -p "$REPO_ROOT/.githooks"
    cat > "$REPO_ROOT/.githooks/pre-commit-block" <<'HOOKEOF'
#!/usr/bin/env bash
# pre-commit hook body — 阻止在受保护分支上 commit
set -e
PROTECTED_BRANCHES="${PROTECTED_BRANCHES:-main}"
current="$(git symbolic-ref --short HEAD 2>/dev/null || true)"
for b in $PROTECTED_BRANCHES; do
  if [[ "$current" == "$b" ]]; then
    echo ""
    echo "✗ 拒绝 commit:分支 '$current' 是受保护主线。"
    echo "  请先切到 feature 分支:"
    echo "    ./scripts/new-branch.sh <topic>"
    echo ""
    exit 1
  fi
done
HOOKEOF
    cat > "$REPO_ROOT/.githooks/pre-push-block" <<'HOOKEOF'
#!/usr/bin/env bash
# pre-push hook body — 阻止 force push + 阻止直接 push 受保护分支
set -e
PROTECTED_BRANCHES="${PROTECTED_BRANCHES:-main}"

while read local_ref local_sha remote_ref remote_sha; do
  # 跳过删除
  [[ "$local_sha" == "0000000000000000000000000000000000000000" ]] && continue
  branch="${remote_ref#refs/heads/}"

  # force push 检测:remote_sha 不是 0000 且不是 local_sha 的祖先
  if [[ "$remote_sha" != "0000000000000000000000000000000000000000" ]]; then
    if ! git merge-base --is-ancestor "$remote_sha" "$local_sha" 2>/dev/null; then
      # local 不是 remote 的祖先 = force push
      for b in $PROTECTED_BRANCHES; do
        if [[ "$branch" == "$b" ]]; then
          echo ""
          echo "✗ 拒绝 force push 到受保护分支 '$branch'。"
          echo "  如果是误操作,改用:"
          echo "    git push --force-with-lease origin <feature-branch>"
          echo ""
          exit 1
        fi
      done
    fi
  fi

  # 直接 push 受保护分支 = 警告(默认不阻止,鼓励走 PR;想严格可改成 exit 1)
  for b in $PROTECTED_BRANCHES; do
    if [[ "$branch" == "$b" ]]; then
      echo ""
      echo "⚠ 警告:正在直接 push 受保护分支 '$branch'。"
      echo "  推荐流程:从 feat/<topic> 推,然后通过 PR 合入 $branch。"
      echo "  如确需直接 push,设置 ALLOW_MAIN_PUSH=1 再重试。"
      if [[ "${ALLOW_MAIN_PUSH:-0}" != "1" ]]; then
        exit 1
      fi
    fi
  done
done
HOOKEOF
    chmod +x "$REPO_ROOT/.githooks/pre-commit-block" "$REPO_ROOT/.githooks/pre-push-block"

    write_pre_commit
    write_pre_push
    write_commit_msg
    echo "✓ 已安装本地分支保护 hook(保护:$MAIN_BRANCH)"
    echo "  hook 逻辑:.githooks/*-block"
    echo "  hook 入口:.git/hooks/{pre-commit,pre-push,commit-msg}"
    ;;

  uninstall)
    for h in pre-commit pre-push commit-msg; do uninstall_hook "$h"; done
    echo "✓ 已卸载分支保护 hook"
    ;;

  status)
    echo "受保护分支:$MAIN_BRANCH"
    for h in pre-commit pre-push; do
      f="$HOOKS_DIR/$h"
      if [[ -f "$f" ]] && grep -q "protect-main.sh BEGIN" "$f"; then
        echo "  $h: ✓ 已安装"
      else
        echo "  $h: ✗ 未安装(运行 ./scripts/protect-main.sh install)"
      fi
    done
    ;;

  *)
    echo "用法:$0 {install|uninstall|status}" >&2
    exit 1
    ;;
esac
