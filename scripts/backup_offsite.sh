#!/usr/bin/env bash
# ============================================================================
# backup_offsite.sh — отправка последнего локального бэкапа SMOKTOLK
# на Яндекс.Диск (WebDAV) через rclone.
#
# Запускается systemd-таймером smoktolk-backup-offsite.timer ежедневно в 23:50 UTC
# (за ~1ч до следующего локального backup.sh; копирует бэкап,
# сделанный текущей ночью в 04:00 MSK = 01:00 UTC).
#
# Алертовая семантика — зеркало backup.sh:
#   - При любой ошибке (die / non-zero exit) trap ERR вызывает
#     notify_admin.sh offsite-failed → создаёт state-файл и шлёт алерт.
#   - При успехе — notify_admin.sh offsite-recovered, которая отправит
#     RECOVERED только если state-файл существует (анти-дубликат).
#   - systemd-юнит smoktolk-backup-offsite-alert.service (через OnFailure=) —
#     страховка на случай OOM / kill -9 / ошибки до trap ERR.
#
# ENV-override (для тестов):
#   BACKUP_DIR        каталог локальных бэкапов (default: /var/backups/smoktolk)
#   STAGING_DIR       где готовим .gz перед заливкой (default: /var/backups/smoktolk-offsite/staging)
#   RCLONE_CONFIG     путь к rclone.conf (default: /var/lib/smoktolk-rclone/rclone.conf)
#   RCLONE_REMOTE     имя remote:path (default: yandex_native:smoktolk-backup)
#   OFFSITE_RETENTION_DAYS  ротация на стороне Я.Диска (default: 30)
#   NOTIFY_SCRIPT     путь к notify_admin.sh
# ============================================================================

set -euo pipefail

# --- Конфигурация ---
BOT_DIR="${BOT_DIR:-/opt/smoktolk/bot}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/smoktolk}"
STAGING_DIR="${STAGING_DIR:-/var/backups/smoktolk-offsite/staging}"
RCLONE_CONFIG="${RCLONE_CONFIG:-/var/lib/smoktolk-rclone/rclone.conf}"
RCLONE_REMOTE="${RCLONE_REMOTE:-yandex_native:smoktolk-backup}"
OFFSITE_RETENTION_DAYS="${OFFSITE_RETENTION_DAYS:-30}"
NOTIFY_SCRIPT="${NOTIFY_SCRIPT:-$BOT_DIR/scripts/notify_admin.sh}"

BACKUP_GLOB='smoktolk_*.db'
LOCK_FILE="${LOCK_FILE:-$STAGING_DIR/.offsite.lock}"

# rclone-флаги: тихий вывод, разумные таймауты, лимит bandwidth.
RCLONE_FLAGS=(
    --config "$RCLONE_CONFIG"
    --timeout 5m
    --contimeout 30s
    --low-level-retries 3
    --retries 3
    --bwlimit 5M
    --stats 0
)

# --- Utility ---
log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$*"
}

die() {
    log "ERROR: $*"
    notify_failure_explicit 1
    exit 1
}

# Explicit вариант notify_failure для вызова из die() —
# trap ERR НЕ срабатывает на явный exit N, поэтому при die()
# алерт нужно отправлять руками. Guard-флаг защищает от
# двойной отправки, если потом всё-таки сработает trap ERR
# (например, при «голом» failing command без || die).
_NOTIFY_SENT=0
notify_failure_explicit() {
    [ "$_NOTIFY_SENT" = "1" ] && return 0
    _NOTIFY_SENT=1
    local rc="${1:-1}"
    set +e
    log "ERROR: offsite-backup завершился с кодом $rc, отправляю алерт"
    if [ -x "$NOTIFY_SCRIPT" ]; then
        "$NOTIFY_SCRIPT" offsite-failed || log "WARN: notify_admin.sh offsite-failed сам упал (rc=$?)"
    else
        log "WARN: $NOTIFY_SCRIPT не исполняем или отсутствует — алерт не отправлен"
    fi
}

# --- Alert trap ---
notify_failure() {
    local rc=$?
    notify_failure_explicit "$rc"
    exit "$rc"
}
trap notify_failure ERR

# --- Проверки окружения ---
command -v rclone >/dev/null || die "rclone не установлен"
command -v gzip   >/dev/null || die "gzip не установлен"
command -v sha256sum >/dev/null || die "sha256sum не установлен"
[ -r "$RCLONE_CONFIG" ] || die "не могу прочитать $RCLONE_CONFIG"
[ -d "$BACKUP_DIR" ]    || die "BACKUP_DIR не существует: $BACKUP_DIR"

mkdir -p "$STAGING_DIR"

# --- Lock ---
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    log "WARN: предыдущий запуск offsite ещё работает (lock=$LOCK_FILE), выхожу"
    exit 0
fi

# --- Шаг 1: находим последний локальный бэкап ---
LATEST_BACKUP="$(find "$BACKUP_DIR" -maxdepth 1 -name "$BACKUP_GLOB" -type f \
    -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | awk '{print $2}')"

[ -n "$LATEST_BACKUP" ] || die "в $BACKUP_DIR нет файлов $BACKUP_GLOB"
[ -s "$LATEST_BACKUP" ] || die "последний бэкап пустой: $LATEST_BACKUP"

BACKUP_NAME="$(basename "$LATEST_BACKUP")"           # smoktolk_YYYYMMDD_HHMMSS.db
GZ_NAME="${BACKUP_NAME}.gz"                          # smoktolk_YYYYMMDD_HHMMSS.db.gz
STAGED_GZ="$STAGING_DIR/$GZ_NAME"

log "source: $LATEST_BACKUP ($(stat -c %s "$LATEST_BACKUP") bytes)"

# --- Шаг 2: gzip в staging ---
# Cleanup-trap — чтобы временные файлы исчезли при любом исходе.
cleanup_staging() {
    rm -f "$STAGED_GZ" "$STAGED_GZ.tmp"
}
trap cleanup_staging EXIT

gzip -c -9 "$LATEST_BACKUP" > "$STAGED_GZ.tmp" \
    || die "gzip упал"
mv "$STAGED_GZ.tmp" "$STAGED_GZ"

GZ_SIZE="$(stat -c %s "$STAGED_GZ")"
GZ_SHA="$(sha256sum "$STAGED_GZ" | awk '{print $1}')"
log "staged: $GZ_NAME ($GZ_SIZE bytes, sha256=${GZ_SHA:0:12})"

# --- Шаг 3: загружаем 2 копии (history + latest) ---
# 3a. История: smoktolk_YYYYMMDD_HHMMSS.db.gz — для retention по дате
rclone "${RCLONE_FLAGS[@]}" copyto "$STAGED_GZ" "$RCLONE_REMOTE/$GZ_NAME" \
    || die "rclone copyto (history) упал"
log "uploaded history: $RCLONE_REMOTE/$GZ_NAME"

# 3b. Latest: фиксированное имя — для быстрого recovery без поиска
rclone "${RCLONE_FLAGS[@]}" copyto "$STAGED_GZ" "$RCLONE_REMOTE/smoktolk-latest.db.gz" \
    || die "rclone copyto (latest) упал"
log "uploaded latest:  $RCLONE_REMOTE/smoktolk-latest.db.gz"

# --- Шаг 4: проверка целостности через hashsum ---
# rclone hashsum SHA256 возвращает хэш файла на стороне remote.
# WebDAV-провайдер Яндекс.Диска может не поддерживать хэши — это OK,
# просто пропустим проверку, если возвращает пустую строку.
REMOTE_HASH="$(rclone "${RCLONE_FLAGS[@]}" hashsum sha256 "$RCLONE_REMOTE/$GZ_NAME" 2>/dev/null | awk '{print $1}' || true)"
if [ -n "$REMOTE_HASH" ] && [ "$REMOTE_HASH" != "UNSUPPORTED" ]; then
    if [ "$REMOTE_HASH" = "$GZ_SHA" ]; then
        log "integrity: remote sha256 matches local"
    else
        die "integrity FAIL: local=$GZ_SHA remote=$REMOTE_HASH"
    fi
else
    log "integrity: remote hash not provided by WebDAV — sverka skipped (OK для Я.Диска)"
fi

# --- Шаг 5: retention на стороне Я.Диска ---
# Удаляем все smoktolk_*.db.gz старше OFFSITE_RETENTION_DAYS дней.
# smoktolk-latest.db.gz НЕ затрагиваем (паттерн не совпадает).
DELETE_OUTPUT="$(rclone "${RCLONE_FLAGS[@]}" delete \
    --include 'smoktolk_*.db.gz' \
    --min-age "${OFFSITE_RETENTION_DAYS}d" \
    "$RCLONE_REMOTE" 2>&1 || true)"
log "retention output: ${DELETE_OUTPUT:-(nothing deleted)}"

# --- Шаг 6: статистика remote ---
REMOTE_FILES="$(rclone "${RCLONE_FLAGS[@]}" lsf --include 'smoktolk_*.db.gz' "$RCLONE_REMOTE" 2>/dev/null | wc -l || echo 0)"
log "stats: remote history files = $REMOTE_FILES (retention=${OFFSITE_RETENTION_DAYS}d)"

# --- Recovery-уведомление ---
trap - ERR
if [ -x "$NOTIFY_SCRIPT" ]; then
    "$NOTIFY_SCRIPT" offsite-recovered || log "WARN: notify_admin.sh offsite-recovered упал (rc=$?), но offsite успешен"
fi

log "OK: offsite backup complete"
exit 0
