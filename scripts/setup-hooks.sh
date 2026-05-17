#!/usr/bin/env bash
# Установка git-hooks из scripts/git-hooks в .git/hooks.
# Запускать после `git clone` или после изменения файлов в scripts/git-hooks/.

set -e

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_SRC="$REPO_ROOT/scripts/git-hooks"
HOOKS_DST="$REPO_ROOT/.git/hooks"

echo "🔧 Установка git-hooks..."

# ── Проверка обязательных утилит ────────────────────────────────────────
MISSING=0

if ! command -v gitleaks &> /dev/null; then
    echo "⚠️  gitleaks не найден в PATH"
    echo "   Установка: https://github.com/gitleaks/gitleaks#getting-started"
    echo "   Без него pre-commit hook будет падать"
    MISSING=1
fi

if [ -x "$REPO_ROOT/venv/bin/ruff" ]; then
    echo "✅ ruff найден: $REPO_ROOT/venv/bin/ruff ($("$REPO_ROOT/venv/bin/ruff" --version))"
elif command -v ruff &> /dev/null; then
    echo "✅ ruff найден в PATH: $(command -v ruff) ($(ruff --version))"
else
    echo "⚠️  ruff не найден (ни в venv/bin/ruff, ни в PATH)"
    echo "   Установка: pip install ruff==0.15.12"
    echo "   Без него pre-commit hook будет падать на staged *.py"
    MISSING=1
fi

# ── Копирование hooks ────────────────────────────────────────────────────
for hook in "$HOOKS_SRC"/*; do
    [ -f "$hook" ] || continue
    name=$(basename "$hook")
    cp "$hook" "$HOOKS_DST/$name"
    chmod +x "$HOOKS_DST/$name"
    echo "   ✅ Установлен: $name"
done

echo ""
if [ "$MISSING" -eq 1 ]; then
    echo "⚠️  Hook'и установлены, но часть утилит отсутствует — установи их до коммитов."
    exit 0
fi
echo "🎉 Готово. Hook'и активны при следующем git commit / git push."

echo ""
echo "📖 См. CONTRIBUTING.md для полного гайда по workflow разработки."
