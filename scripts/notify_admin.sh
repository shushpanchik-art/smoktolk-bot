#!/bin/bash
# notify_admin.sh — отправка DOWN-уведомления админу при крэше systemd-сервиса.
#
# Использование: notify_admin.sh down
# RECOVERED отправляет сам Python-бот при старте через crash_alert.py.
#
# Анти-дубликат: state-файл /run/smoktolk-bot/crashed. Директория создаётся
# systemd-юнитом (RuntimeDirectory=smoktolk-bot) с владельцем smoktolk:smoktolk,
# благодаря чему бот (под юзером smoktolk) может удалить файл при RECOVERED.

set -euo pipefail

EVENT="${1:-}"
STATE_DIR="/run/smoktolk-bot"
STATE_FILE="${STATE_DIR}/crashed"
ENV_FILE="/opt/smoktolk/bot/.env"
LOG_TAG="notify_admin"

log() { logger -t "$LOG_TAG" -- "$*"; echo "[$LOG_TAG] $*"; }

if [ "$EVENT" != "down" ]; then
    log "ERROR: ожидался аргумент 'down', получено: '$EVENT'"
    exit 2
fi

# Если систему-юнит не создал директорию (например, юнит остановлен), создаём сами
if [ ! -d "$STATE_DIR" ]; then
    mkdir -p "$STATE_DIR"
    chown smoktolk:smoktolk "$STATE_DIR" 2>/dev/null || true
    chmod 0775 "$STATE_DIR"
fi

# Анти-дубликат
if [ -e "$STATE_FILE" ]; then
    log "INFO: state-файл уже есть — DOWN-уведомление уже было отправлено, пропускаем"
    exit 0
fi

# Читаем токен/админа
if [ ! -r "$ENV_FILE" ]; then
    log "ERROR: не могу прочитать $ENV_FILE"
    exit 3
fi

BOT_TOKEN="$(grep -E '^BOT_TOKEN=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
ADMIN_ID="$(grep -E '^ADMIN_ID=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"

if [ -z "$BOT_TOKEN" ] || [ -z "$ADMIN_ID" ]; then
    log "ERROR: BOT_TOKEN или ADMIN_ID пустые в .env"
    exit 4
fi

# Создаём state-файл с владельцем smoktolk, чтобы бот мог его удалить
touch "$STATE_FILE"
chown smoktolk:smoktolk "$STATE_FILE" 2>/dev/null || true

TEXT="🚨 *SMOKTOLK_bot DOWN*
Сервис не активен, выполняю перезапуск..."

HTTP_CODE="$(curl -s -o /tmp/notify_admin_resp.$$ -w '%{http_code}' \
    -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
    -d chat_id="${ADMIN_ID}" \
    -d parse_mode=Markdown \
    --data-urlencode "text=${TEXT}" || echo "000")"

if [ "$HTTP_CODE" = "200" ]; then
    log "OK: alert 'down' sent (HTTP 200)"
    rm -f /tmp/notify_admin_resp.$$
    exit 0
else
    BODY="$(cat /tmp/notify_admin_resp.$$ 2>/dev/null || echo '')"
    log "ERROR: alert 'down' failed (HTTP $HTTP_CODE): $BODY"
    rm -f /tmp/notify_admin_resp.$$
    exit 5
fi
