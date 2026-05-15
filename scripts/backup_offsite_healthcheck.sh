#!/usr/bin/env bash
# ============================================================================
# backup_offsite_healthcheck.sh — проверка свежести offsite-бэкапа на Я.Диске.
#
# Запускается systemd-таймером smoktolk-backup-offsite-healthcheck.timer
# ежедневно в 08:00 UTC (= 11:00 MSK).
#
# Логика: запрашиваем у Я.Диска mtime файла smoktolk-latest.db.gz.
# Если файла нет или он старше MAX_AGE_HOURS — шлём offsite-failed.
#
# Защищает от сценариев, которые НЕ покрывает OnFailure= в основном offsite-юните:
#   - timer вообще не сработал (юнит выключен/disabled, jobs stuck);
#   - Я.Диск молча принял upload, но файл повредился/исчез/был ротирован;
#   - smoktolk-backup-offsite.service был случайно отключён.
#
# Расписание offsite: 23:50 UTC (= 02:50 MSK).
# Healthcheck: 08:00 UTC (= 11:00 MSK) — через 8ч 10мин после offsite.
# MAX_AGE_HOURS=30: после одного пропущенного offsite возраст файла
# к моменту следующего healthcheck составит ~32ч → alert сработает
# на самом первом несработавшем дне.
#
# ВАЖНО про TZ: `rclone lsl` для WebDAV-бэкенда Я.Диска возвращает mtime
# в локальной таймзоне сервера (а не в UTC). Передаём строку в `date -d`
# БЕЗ суффикса UTC — пусть date интерпретирует её в текущей системной TZ.
# Проверено эмпирически: rclone 1.62, Я.Диск WebDAV, TZ=MSK.
# ============================================================================

set -euo pipefail

RCLONE_CONFIG="${RCLONE_CONFIG:-/var/lib/smoktolk-rclone/rclone.conf}"
RCLONE_REMOTE="${RCLONE_REMOTE:-yandex:smoktolk-backup}"
LATEST_NAME="${LATEST_NAME:-smoktolk-latest.db.gz}"
MAX_AGE_HOURS="${MAX_AGE_HOURS:-30}"
NOTIFY_SCRIPT="${NOTIFY_SCRIPT:-/opt/smoktolk/bot/scripts/notify_admin.sh}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] offsite-healthcheck: $*"; }

fail() {
    log "FAIL: $*"
    if [ -x "$NOTIFY_SCRIPT" ]; then
        "$NOTIFY_SCRIPT" offsite-failed || log "WARN: notify_admin.sh упал (rc=$?)"
    else
        log "WARN: $NOTIFY_SCRIPT не исполняем, алерт не отправлен"
    fi
    exit 1
}

command -v rclone >/dev/null 2>&1 || fail "rclone не установлен"
[ -r "$RCLONE_CONFIG" ] || fail "rclone config не читается: $RCLONE_CONFIG"

# rclone lsl выдаёт строки вида:
#   "    SIZE  YYYY-MM-DD HH:MM:SS.NNNNNNNNN NAME"
LSL_OUT="$(rclone --config "$RCLONE_CONFIG" --timeout 60s lsl "$RCLONE_REMOTE/$LATEST_NAME" 2>&1 || true)"

if [ -z "$LSL_OUT" ] || echo "$LSL_OUT" | grep -qiE 'not found|directory not found|404|error'; then
    fail "файл $RCLONE_REMOTE/$LATEST_NAME не найден или ошибка rclone. Output: $LSL_OUT"
fi

# Парсим: "    SIZE YYYY-MM-DD HH:MM:SS.NNN... NAME" → "YYYY-MM-DD HH:MM:SS"
MTIME_STR="$(echo "$LSL_OUT" | head -1 | awk '{print $2" "$3}' | cut -d. -f1)"
if [ -z "$MTIME_STR" ]; then
    fail "не удалось распарсить mtime из rclone lsl: $LSL_OUT"
fi

# КРИТИЧНО: НЕ добавляем ' UTC' — rclone отдаёт время в локальной TZ сервера.
MTIME_EPOCH="$(date -d "$MTIME_STR" +%s 2>/dev/null || echo 0)"
[ "$MTIME_EPOCH" -gt 0 ] || fail "невалидный mtime: '$MTIME_STR'"

NOW_EPOCH="$(date +%s)"
AGE_SEC=$(( NOW_EPOCH - MTIME_EPOCH ))
AGE_HOURS=$(( AGE_SEC / 3600 ))

# Защита от отрицательного возраста (расхождение часов сервер vs Я.Диск).
# Допускаем небольшую вилку: до -1ч считаем нормой (clock skew),
# глубже — это реальная проблема (TZ misconfig, NTP сломан).
if [ "$AGE_SEC" -lt -3600 ]; then
    fail "mtime в будущем: ${AGE_HOURS}ч (mtime=$MTIME_STR, NOW=$(date)). Проверь TZ и NTP."
fi

if [ "$AGE_HOURS" -gt "$MAX_AGE_HOURS" ]; then
    fail "$LATEST_NAME слишком старый: ${AGE_HOURS}ч (limit=${MAX_AGE_HOURS}ч, mtime=$MTIME_STR)"
fi

log "OK: $LATEST_NAME age=${AGE_HOURS}ч (limit=${MAX_AGE_HOURS}ч, mtime=$MTIME_STR)"
exit 0
