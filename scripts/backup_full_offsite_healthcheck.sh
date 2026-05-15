#!/usr/bin/env bash
# ============================================================================
# backup_full_offsite_healthcheck.sh — проверка свежести full-tar offsite на Я.Диске.
#
# Запускается systemd-таймером smoktolk-backup-full-offsite-healthcheck.timer
# ежедневно в 09:00 UTC (= 12:00 MSK).
#
# Логика: запрашиваем mtime smoktolk-full-latest.tar.gz.
# Если файла нет или он старше MAX_AGE_HOURS — шлём offsite-full-failed.
#
# Расписание full-offsite: 23:45 UTC. Healthcheck: 09:00 UTC = через ~9ч.
# MAX_AGE_HOURS=30: после одного пропущенного дня возраст ~33ч → alert
# сработает в самый первый день сбоя.
#
# ВАЖНО про TZ: rclone WebDAV → mtime в локальной TZ сервера, см.
# подробности в backup_offsite_healthcheck.sh.
# ============================================================================

set -euo pipefail

RCLONE_CONFIG="${RCLONE_CONFIG:-/var/lib/smoktolk-rclone/rclone.conf}"
RCLONE_REMOTE="${RCLONE_REMOTE:-yandex:smoktolk-backup-full}"
LATEST_NAME="${LATEST_NAME:-smoktolk-full-latest.tar.gz}"
MAX_AGE_HOURS="${MAX_AGE_HOURS:-30}"
NOTIFY_SCRIPT="${NOTIFY_SCRIPT:-/opt/smoktolk/bot/scripts/notify_admin.sh}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] full-offsite-healthcheck: $*"; }

fail() {
    log "FAIL: $*"
    if [ -x "$NOTIFY_SCRIPT" ]; then
        "$NOTIFY_SCRIPT" offsite-full-failed || log "WARN: notify_admin.sh упал (rc=$?)"
    else
        log "WARN: $NOTIFY_SCRIPT не исполняем, алерт не отправлен"
    fi
    exit 1
}

command -v rclone >/dev/null 2>&1 || fail "rclone не установлен"
[ -r "$RCLONE_CONFIG" ] || fail "rclone config не читается: $RCLONE_CONFIG"

LSL_OUT="$(rclone --config "$RCLONE_CONFIG" --timeout 60s lsl "$RCLONE_REMOTE/$LATEST_NAME" 2>&1 || true)"

if [ -z "$LSL_OUT" ] || echo "$LSL_OUT" | grep -qiE 'not found|directory not found|404|error'; then
    fail "файл $RCLONE_REMOTE/$LATEST_NAME не найден или ошибка rclone. Output: $LSL_OUT"
fi

MTIME_STR="$(echo "$LSL_OUT" | head -1 | awk '{print $2" "$3}' | cut -d. -f1)"
if [ -z "$MTIME_STR" ]; then
    fail "не удалось распарсить mtime из rclone lsl: $LSL_OUT"
fi

MTIME_EPOCH="$(date -d "$MTIME_STR" +%s 2>/dev/null || echo 0)"
[ "$MTIME_EPOCH" -gt 0 ] || fail "невалидный mtime: '$MTIME_STR'"

NOW_EPOCH="$(date +%s)"
AGE_SEC=$(( NOW_EPOCH - MTIME_EPOCH ))
AGE_HOURS=$(( AGE_SEC / 3600 ))

if [ "$AGE_SEC" -lt -3600 ]; then
    fail "mtime в будущем: ${AGE_HOURS}ч (mtime=$MTIME_STR, NOW=$(date)). Проверь TZ и NTP."
fi

if [ "$AGE_HOURS" -gt "$MAX_AGE_HOURS" ]; then
    fail "$LATEST_NAME слишком старый: ${AGE_HOURS}ч (limit=${MAX_AGE_HOURS}ч, mtime=$MTIME_STR)"
fi

log "OK: $LATEST_NAME age=${AGE_HOURS}ч (limit=${MAX_AGE_HOURS}ч, mtime=$MTIME_STR)"
exit 0
