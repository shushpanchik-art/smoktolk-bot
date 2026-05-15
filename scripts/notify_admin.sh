#!/bin/bash
# notify_admin.sh — отправка алертов админу.
#
# Использование:
#   notify_admin.sh down                  # 🚨 SMOKTOLK_bot DOWN
#   notify_admin.sh backup-failed         # 🚨 SMOKTOLK backup FAILED
#   notify_admin.sh backup-recovered      # ✅ SMOKTOLK backup восстановлен
#   notify_admin.sh offsite-failed        # 🚨 SMOKTOLK offsite backup FAILED
#   notify_admin.sh offsite-recovered     # ✅ SMOKTOLK offsite backup восстановлен
#   notify_admin.sh offsite-full-failed   # 🚨 SMOKTOLK full-offsite backup FAILED
#   notify_admin.sh offsite-full-recovered # ✅ SMOKTOLK full-offsite backup восстановлен
#
# RECOVERED для бота отправляет сам Python через crash_alert.py.
# RECOVERED для backup/offsite отправляет соответствующий .sh через этот скрипт.
#
# Анти-дубликат через state-файлы:
#   /run/smoktolk-bot/crashed              — для бота (создаётся ботовым юнитом)
#   /var/lib/smoktolk-backup/failed        — для локального бэкапа
#   /var/lib/smoktolk-backup/offsite-failed — для offsite-бэкапа БД (PR #ops-offsite-yandex-disk)
#   /var/lib/smoktolk-backup/offsite-full-failed — для full-tar offsite (PR #ops-offsite-full-tar)

set -euo pipefail

EVENT="${1:-}"
ENV_FILE="/opt/smoktolk/bot/.env"
LOG_TAG="notify_admin"

# State-каталоги/файлы
BOT_STATE_DIR="/run/smoktolk-bot"
BOT_STATE_FILE="${BOT_STATE_DIR}/crashed"
BACKUP_STATE_DIR="/var/lib/smoktolk-backup"
BACKUP_STATE_FILE="${BACKUP_STATE_DIR}/failed"
OFFSITE_STATE_FILE="${BACKUP_STATE_DIR}/offsite-failed"
OFFSITE_FULL_STATE_FILE="${BACKUP_STATE_DIR}/offsite-full-failed"

log() { logger -t "$LOG_TAG" -- "$*"; echo "[$LOG_TAG] $*"; }

# Читаем токен/админа из .env
read_credentials() {
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
}

# Отправка в Telegram. $1 = текст (Markdown)
send_telegram() {
    local text="$1"
    local resp_file="/tmp/notify_admin_resp.$$"
    local http_code
    http_code="$(curl -s -o "$resp_file" -w '%{http_code}' \
        -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d chat_id="${ADMIN_ID}" \
        -d parse_mode=Markdown \
        --data-urlencode "text=${text}" || echo "000")"
    if [ "$http_code" = "200" ]; then
        log "OK: alert '$EVENT' sent (HTTP 200)"
        rm -f "$resp_file"
        return 0
    else
        local body
        body="$(cat "$resp_file" 2>/dev/null || echo '')"
        log "ERROR: alert '$EVENT' failed (HTTP $http_code): $body"
        rm -f "$resp_file"
        return 5
    fi
}

# Утилита: гарантирует существование BACKUP_STATE_DIR с правильными правами.
# Используется и для backup-*, и для offsite-* событий.
ensure_backup_state_dir() {
    if [ ! -d "$BACKUP_STATE_DIR" ]; then
        mkdir -p "$BACKUP_STATE_DIR"
        chown smoktolk:smoktolk "$BACKUP_STATE_DIR" 2>/dev/null || true
        chmod 0775 "$BACKUP_STATE_DIR"
    fi
}

case "$EVENT" in
    down)
        # === DOWN-уведомление о крэше бота ===
        if [ ! -d "$BOT_STATE_DIR" ]; then
            mkdir -p "$BOT_STATE_DIR"
            chown smoktolk:smoktolk "$BOT_STATE_DIR" 2>/dev/null || true
            chmod 0775 "$BOT_STATE_DIR"
        fi
        if [ -e "$BOT_STATE_FILE" ]; then
            log "INFO: bot state-файл уже есть — DOWN уже было отправлено, пропускаем"
            exit 0
        fi
        read_credentials
        touch "$BOT_STATE_FILE"
        chown smoktolk:smoktolk "$BOT_STATE_FILE" 2>/dev/null || true
        TEXT="🚨 *SMOKTOLK_bot DOWN*
Сервис не активен, выполняю перезапуск..."
        send_telegram "$TEXT" || exit $?
        ;;

    backup-failed)
        # === Алерт о падении локального бэкапа ===
        ensure_backup_state_dir
        if [ -e "$BACKUP_STATE_FILE" ]; then
            log "INFO: backup state-файл уже есть — backup-failed уже было отправлено, пропускаем"
            exit 0
        fi
        read_credentials
        touch "$BACKUP_STATE_FILE"
        chown smoktolk:smoktolk "$BACKUP_STATE_FILE" 2>/dev/null || true
        TEXT="🚨 *SMOKTOLK backup FAILED*
Бэкап БД упал. Лог: \`/opt/smoktolk/bot/logs/backup.log\`
Проверь: \`systemctl status smoktolk-backup\`"
        send_telegram "$TEXT" || exit $?
        ;;

    backup-recovered)
        # === Сообщение о восстановлении локального бэкапа ===
        if [ ! -e "$BACKUP_STATE_FILE" ]; then
            log "INFO: backup state-файл отсутствует — нет необходимости в RECOVERED"
            exit 0
        fi
        read_credentials
        TEXT="✅ *SMOKTOLK backup восстановлен*
Очередной бэкап прошёл успешно."
        if send_telegram "$TEXT"; then
            rm -f "$BACKUP_STATE_FILE"
            log "OK: backup state-файл удалён"
        else
            exit $?
        fi
        ;;

    offsite-failed)
        # === Алерт о падении offsite-бэкапа (Я.Диск) ===
        ensure_backup_state_dir
        if [ -e "$OFFSITE_STATE_FILE" ]; then
            log "INFO: offsite state-файл уже есть — offsite-failed уже было отправлено, пропускаем"
            exit 0
        fi
        read_credentials
        touch "$OFFSITE_STATE_FILE"
        chown smoktolk:smoktolk "$OFFSITE_STATE_FILE" 2>/dev/null || true
        TEXT="🚨 *SMOKTOLK offsite backup FAILED*
Отправка бэкапа на Я.Диск упала.
Лог: \`/opt/smoktolk/bot/logs/backup_offsite.log\`
Проверь: \`systemctl status smoktolk-backup-offsite\`"
        send_telegram "$TEXT" || exit $?
        ;;

    offsite-recovered)
        # === Сообщение о восстановлении offsite-бэкапа ===
        if [ ! -e "$OFFSITE_STATE_FILE" ]; then
            log "INFO: offsite state-файл отсутствует — нет необходимости в RECOVERED"
            exit 0
        fi
        read_credentials
        TEXT="✅ *SMOKTOLK offsite backup восстановлен*
Очередная отправка на Я.Диск прошла успешно."
        if send_telegram "$TEXT"; then
            rm -f "$OFFSITE_STATE_FILE"
            log "OK: offsite state-файл удалён"
        else
            exit $?
        fi
        ;;

    offsite-full-failed)
        # === Алерт о падении full-tar offsite-бэкапа (Я.Диск) ===
        ensure_backup_state_dir
        if [ -e "$OFFSITE_FULL_STATE_FILE" ]; then
            log "INFO: offsite-full state-файл уже есть — offsite-full-failed уже было отправлено, пропускаем"
            exit 0
        fi
        read_credentials
        touch "$OFFSITE_FULL_STATE_FILE"
        chown smoktolk:smoktolk "$OFFSITE_FULL_STATE_FILE" 2>/dev/null || true
        TEXT="🚨 *SMOKTOLK full-offsite backup FAILED*
Полный архив /opt/smoktolk/ не загружен на Я.Диск.
Лог: \`/opt/smoktolk/bot/logs/backup-full-offsite.log\`
Проверь: \`systemctl status smoktolk-backup-full-offsite\`"
        send_telegram "$TEXT" || exit $?
        ;;

    offsite-full-recovered)
        # === Сообщение о восстановлении full-tar offsite-бэкапа ===
        if [ ! -e "$OFFSITE_FULL_STATE_FILE" ]; then
            log "INFO: offsite-full state-файл отсутствует — нет необходимости в RECOVERED"
            exit 0
        fi
        read_credentials
        TEXT="✅ *SMOKTOLK full-offsite backup восстановлен*
Очередная отправка полного архива на Я.Диск прошла успешно."
        if send_telegram "$TEXT"; then
            rm -f "$OFFSITE_FULL_STATE_FILE"
            log "OK: offsite-full state-файл удалён"
        else
            exit $?
        fi
        ;;

    *)
        log "ERROR: неизвестное событие: '$EVENT'. Допустимо: down, backup-failed, backup-recovered, offsite-failed, offsite-recovered, offsite-full-failed, offsite-full-recovered"
        exit 2
        ;;
esac

exit 0
