#!/usr/bin/env bash
# Установка git-hooks из scripts/git-hooks в .git/hooks
# Запускать один раз после git clone

set -e

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_SRC="$REPO_ROOT/scripts/git-hooks"
HOOKS_DST="$REPO_ROOT/.git/hooks"

echo "🔧 Установка git-hooks..."

if ! command -v gitleaks &> /dev/null; then
    echo "⚠️  gitleaks не найден в PATH"
    echo "   Установи его: https://github.com/gitleaks/gitleaks#getting-started"
    echo "   Без него pre-commit hook будет падать"
fi

for hook in "$HOOKS_SRC"/*; do
    [ -f "$hook" ] || continue
    name=$(basename "$hook")
    cp "$hook" "$HOOKS_DST/$name"
    chmod +x "$HOOKS_DST/$name"
    echo "   ✅ Установлен: $name"
done

echo ""
echo "🎉 Готово. Hook'и активны при следующем git commit."
