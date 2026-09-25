#!/usr/bin/env bash
# scripts/new-branch.sh — 在 main 之上切出一个 feature 分支(命名规范:feat/<topic>)
#
# 用法:
#   ./scripts/new-branch.sh kline-bollinger          -> feat/kline-bollinger
#   ./scripts/new-branch.sh fix/api-timeout          -> fix/api-timeout
#   ./scripts/new-branch.sh chore/bump-deps          -> chore/bump-deps
#   ./scripts/new-branch.sh                          -> 交互式输入
#
# 规范:
#   - 分支必须从 main 切
#   - 分支名只允许:feat/<x> | fix/<x> | chore/<x> | docs/<x> | refactor/<x> | test/<x>
#   - <x> 只允许 [a-z0-9-],且不能以 - 开头/结尾,不能有连续 --
#
# 依赖:git,awk
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

MAIN_BRANCH="${MAIN_BRANCH:-main}"
TOPIC="${1:-}"

slugify_topic() {
  # 接受 'kline bollinger' / 'Kline_Bollinger' -> 'kline-bollinger'
  echo "$1" | tr '[:upper:]' '[:lower:]' | tr '_ ' '-' | sed -E 's/[^a-z0-9-]+//g; s/-+/-/g; s/^-+//; s/-+$//'
}

validate_slug() {
  local slug="$1"
  if [[ -z "$slug" ]]; then
    echo "ERROR: 分支名 slug 为空。" >&2
    exit 1
  fi
  if [[ "$slug" =~ ^-+ || "$slug" =~ -+$ ]]; then echo "ERROR: 不能以 - 开头/结尾" >&2; exit 1; fi
  if [[ "$slug" =~ -- ]]; then echo "ERROR: 不能有连续 --" >&2; exit 1; fi
  if [[ ! "$slug" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]]; then
    echo "ERROR: 只允许 [a-z0-9-],且首尾必须是字母数字" >&2
    exit 1
  fi
}

# 1) 解析 topic(交互式)
if [[ -z "$TOPIC" ]]; then
  echo "新分支名(只填后半段,前缀会自动加 feat/)。"
  echo "例如:输入 'kline-bollinger' -> 'feat/kline-bollinger'"
  read -r -p "topic> " TOPIC
  if [[ -z "$TOPIC" ]]; then echo "ERROR: 没输入"; exit 1; fi
fi

# 2) 决定前缀
PREFIX="feat"
if [[ "$TOPIC" == */* ]]; then
  PREFIX="${TOPIC%%/*}"
  TOPIC="${TOPIC#*/}"
  case "$PREFIX" in
    feat|fix|chore|docs|refactor|test) ;;
    *) echo "ERROR: 前缀 '$PREFIX' 不在白名单 feat|fix|chore|docs|refactor|test" >&2; exit 1 ;;
  esac
fi

# 3) slug 化 + 校验
SLUG="$(slugify_topic "$TOPIC")"
validate_slug "$SLUG"
BRANCH="${PREFIX}/${SLUG}"

# 4) 状态检查
CURRENT="$(git branch --show-current)"
echo "==> 当前分支: $CURRENT"

if [[ "$CURRENT" != "$MAIN_BRANCH" ]]; then
  echo "WARN: 不在 $MAIN_BRANCH 上(在 $CURRENT)。建议先回到 $MAIN_BRANCH 再切。"
  read -r -p "继续切 $BRANCH? [y/N] " ans
  [[ "$ans" == "y" || "$ans" == "Y" ]] || { echo "取消"; exit 0; }
fi

# 5) main 是否最新
git fetch origin "$MAIN_BRANCH" 2>/dev/null || true
LOCAL_MAIN="$(git rev-parse "$MAIN_BRANCH" 2>/dev/null || echo "")"
REMOTE_MAIN="$(git rev-parse "origin/$MAIN_BRANCH" 2>/dev/null || echo "")"

if [[ -n "$LOCAL_MAIN" && -n "$REMOTE_MAIN" && "$LOCAL_MAIN" != "$REMOTE_MAIN" ]]; then
  echo "WARN: 本地 $MAIN_BRANCH 与 origin/$MAIN_BRANCH 不同步。"
  echo "  local : $(git log --oneline -1 "$MAIN_BRANCH")"
  echo "  remote: $(git log --oneline -1 "origin/$MAIN_BRANCH")"
  read -r -p "先 git pull origin $MAIN_BRANCH 再切? [Y/n] " ans
  ans="${ans:-Y}"
  if [[ "$ans" == "Y" ]]; then
    git pull --ff-only origin "$MAIN_BRANCH"
  fi
fi

# 6) 已存在?
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  echo "WARN: 本地已存在 $BRANCH,直接 checkout。"
  git checkout "$BRANCH"
  exit 0
fi
if git show-ref --verify --quiet "refs/remotes/origin/$BRANCH"; then
  echo "WARN: origin 上已有同名分支 $BRANCH,从 origin 拉。"
  git checkout -b "$BRANCH" "origin/$BRANCH"
  exit 0
fi

# 7) 切出
echo "==> git checkout -b $BRANCH"
git checkout -b "$BRANCH"

echo ""
echo "✓ 新分支已就绪:$BRANCH(基于 $MAIN_BRANCH)"
echo "  完成后:git push -u origin $BRANCH,然后提 PR 合回 $MAIN_BRANCH"
