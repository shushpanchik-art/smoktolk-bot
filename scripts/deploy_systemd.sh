#!/usr/bin/env bash
# deploy_systemd.sh — атомарный деплой systemd-юнитов из репозитория.
#
# Логика:
#   1) Делает timestamped-бэкапы текущих файлов в /etc/systemd/system/
#   2) Копирует все systemd/*.service, *.timer и drop-in'ы из репо
#   3) systemctl daemon-reload
#   4) Если указан --restart SERVICE — рестартует один сервис и ждёт активности
#   5) При ошибке рестарта — откат из бэкапа и exit 1
#
# Использование:
#   sudo ./scripts/deploy_systemd.sh                       # копирует + daemon-reload, без рестартов
#   sudo ./scripts/deploy_systemd.sh --restart smoktolk-bot.service
#   sudo ./scripts/deploy_systemd.sh --dry-run             # показать diff, ничего не менять

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SYSTEMD_SRC="$REPO_ROOT/systemd"
SYSTEMD_DST="/etc/systemd/system"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="/var/backups/smoktolk-systemd/$TIMESTAMP"

DRY_RUN=0
RESTART_UNIT=""

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run)  DRY_RUN=1; shift;;
        --restart)  RESTART_UNIT="$2"; shift 2;;
        *)          echo "Unknown arg: $1"; exit 2;;
    esac
done

if [ "$(id -u)" -ne 0 ]; then
    echo -e "${RED}❌ Скрипт должен запускаться от root (sudo)${NC}"
    exit 1
fi

echo -e "${BLUE}═══ deploy_systemd.sh ═══${NC}"
echo "Source: $SYSTEMD_SRC"
echo "Target: $SYSTEMD_DST"
echo "Backup: $BACKUP_DIR"
echo "Dry-run: $DRY_RUN"
echo "Restart: ${RESTART_UNIT:-<none>}"
echo ""

# Список файлов для деплоя: всё, что лежит в systemd/ (рекурсивно)
mapfile -t FILES < <(find "$SYSTEMD_SRC" -type f \( -name '*.service' -o -name '*.timer' -o -name '*.conf' \) | sort)

if [ ${#FILES[@]} -eq 0 ]; then
    echo -e "${RED}❌ В $SYSTEMD_SRC нет файлов для деплоя${NC}"
    exit 1
fi

# Подсчёт изменений
CHANGED=()
for src in "${FILES[@]}"; do
    rel="${src#$SYSTEMD_SRC/}"
    dst="$SYSTEMD_DST/$rel"
    if [ ! -f "$dst" ] || ! diff -q "$src" "$dst" >/dev/null 2>&1; then
        CHANGED+=("$rel")
    fi
done

if [ ${#CHANGED[@]} -eq 0 ]; then
    echo -e "${GREEN}✅ Изменений нет, деплой не требуется${NC}"
    exit 0
fi

echo -e "${YELLOW}Изменены/новые файлы (${#CHANGED[@]}):${NC}"
for f in "${CHANGED[@]}"; do echo "  - $f"; done
echo ""

if [ "$DRY_RUN" -eq 1 ]; then
    echo -e "${BLUE}── DIFF ──${NC}"
    for rel in "${CHANGED[@]}"; do
        src="$SYSTEMD_SRC/$rel"
        dst="$SYSTEMD_DST/$rel"
        echo -e "${BLUE}=== $rel ===${NC}"
        diff -u "$dst" "$src" 2>/dev/null || echo "(новый файл)"
    done
    echo ""
    echo -e "${YELLOW}DRY-RUN — изменения не применены${NC}"
    exit 0
fi

# Бэкап
mkdir -p "$BACKUP_DIR"
echo -e "${BLUE}── BACKUP в $BACKUP_DIR ──${NC}"
for rel in "${CHANGED[@]}"; do
    dst="$SYSTEMD_DST/$rel"
    if [ -f "$dst" ]; then
        mkdir -p "$BACKUP_DIR/$(dirname "$rel")"
        cp -a "$dst" "$BACKUP_DIR/$rel"
        echo "  backup: $rel"
    fi
done

# Копирование
echo -e "${BLUE}── DEPLOY ──${NC}"
for rel in "${CHANGED[@]}"; do
    src="$SYSTEMD_SRC/$rel"
    dst="$SYSTEMD_DST/$rel"
    mkdir -p "$(dirname "$dst")"
    install -m 0644 -o root -g root "$src" "$dst"
    echo "  copied: $rel"
done

# daemon-reload
systemctl daemon-reload
echo -e "${GREEN}✅ systemctl daemon-reload${NC}"

# Рестарт если указано
if [ -n "$RESTART_UNIT" ]; then
    echo ""
    echo -e "${BLUE}── RESTART $RESTART_UNIT ──${NC}"

    # Берём PID до рестарта (для сравнения)
    OLD_PID=$(systemctl show "$RESTART_UNIT" -p MainPID --value || echo "0")

    if ! systemctl restart "$RESTART_UNIT"; then
        echo -e "${RED}❌ systemctl restart упал, откат...${NC}"
        for rel in "${CHANGED[@]}"; do
            if [ -f "$BACKUP_DIR/$rel" ]; then
                cp -a "$BACKUP_DIR/$rel" "$SYSTEMD_DST/$rel"
                echo "  restored: $rel"
            fi
        done
        systemctl daemon-reload
        systemctl restart "$RESTART_UNIT" || true
        exit 1
    fi

    # Ждём 5 сек, проверяем active
    sleep 5
    if ! systemctl is-active --quiet "$RESTART_UNIT"; then
        echo -e "${RED}❌ Сервис не active после рестарта, откат...${NC}"
        journalctl -u "$RESTART_UNIT" -n 30 --no-pager
        for rel in "${CHANGED[@]}"; do
            if [ -f "$BACKUP_DIR/$rel" ]; then
                cp -a "$BACKUP_DIR/$rel" "$SYSTEMD_DST/$rel"
                echo "  restored: $rel"
            fi
        done
        systemctl daemon-reload
        systemctl restart "$RESTART_UNIT" || true
        exit 1
    fi

    NEW_PID=$(systemctl show "$RESTART_UNIT" -p MainPID --value)
    echo -e "${GREEN}✅ $RESTART_UNIT active, MainPID: $OLD_PID → $NEW_PID${NC}"
fi

echo ""
echo -e "${GREEN}═══ Деплой завершён успешно ═══${NC}"
echo "Откат: sudo cp -a $BACKUP_DIR/* $SYSTEMD_DST/ && systemctl daemon-reload"
