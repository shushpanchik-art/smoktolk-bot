#!/usr/bin/env bash
# Ежедневный бэкап БД и каталога. Хранит 30 копий.
set -euo pipefail

BOT_DIR="/opt/smoktolk/bot"
BACKUP_DIR="$BOT_DIR/backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

# SQLite-дамп через .backup — безопасно при работающем боте
sqlite3 "$BOT_DIR/data/smoktolk.db" ".backup '$BACKUP_DIR/smoktolk_$DATE.db'"

# каталог как есть
if [ -f "$BOT_DIR/data/catalog.xlsx" ]; then
    cp "$BOT_DIR/data/catalog.xlsx" "$BACKUP_DIR/catalog_$DATE.xlsx"
fi

# чистим старьё (оставляем последние 30 БД и 30 каталогов)
ls -1t "$BACKUP_DIR"/smoktolk_*.db 2>/dev/null | tail -n +31 | xargs -r rm -f
ls -1t "$BACKUP_DIR"/catalog_*.xlsx 2>/dev/null | tail -n +31 | xargs -r rm -f

echo "[$(date)] backup ok: smoktolk_$DATE.db"
