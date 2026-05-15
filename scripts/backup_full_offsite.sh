#!/usr/bin/env bash
# ============================================================================
# backup_full_offsite.sh — full-project tar.gz всего /opt/smoktolk/
# на Яндекс.Диск (WebDAV) через rclone.
#
# Дополняет (а не заменяет!) backup_offsite.sh из PR #48:
#   - backup_offsite.sh:      только SQLite-БД (~МБ),        23:50 UTC ежедневно,
#                             retention 30 файлов  → яндекс:smoktolk-backup/
#   - backup_full_offsite.sh: всё /opt/smoktolk/  (~100 МБ), 20:00 UTC ежедневно,
#                             retention 30 файлов  → яндекс:smoktolk-backup-full/
#
# Зачем full-tar, если есть БД-only:
#   - .env с BOT_TOKEN / ADMIN_ID (без него бот не стартует)
#   - rclone.conf (без него восстановить offsite-цепочку нечем)
#   - systemd-юниты в /etc/ (можно вытащить и из репо, но в архиве — ровно те,
#     что были в проде на момент бэкапа)
#   - data/avatr*.mp4 и прочие медиа
#   - WIP-ветки в .git/, которые могли не успеть в GitHub
#
# Расписание: 20:00 UTC (= 23:00 MSK). На 3ч 50мин РАНЬШЕ БД-offsite (23:50 UTC),
# чтобы НЕ конкурировать за bandwidth и не падать в TimeoutStartSec.
# Я.Диск WebDAV тротлит загрузку: после ~40 MB скорость падает с пика 3-4 MiB/s
# до десятков KiB/s на десятки минут. 100 МБ в худшем случае заливается до 60-90
# минут. С запасом ≥3ч в окне 20:00→23:50 UTC мы гарантируем 100% уложиться
# в сутки даже при максимальном тротлинге.
#
# Оптимизация bandwidth: вместо двух full-upload'ов (history + latest) делаем
# 1) upload history (медленный, по сети), 2) server-side copyto history→latest
# на стороне WebDAV (быстрый, без передачи тела). Я.Диск поддерживает WebDAV COPY.
#
# Алертовая семантика — зеркало backup_offsite.sh:
#   - trap ERR → notify_admin.sh offsite-full-failed (+ state-файл)
#   - success  → notify_admin.sh offsite-full-recovered (если был state-файл)
#   - systemd OnFailure= → smoktolk-backup-full-offsite-alert.service
#
# ENV-override (для тестов и DR):
#   SOURCE_DIR             что архивируем (default: /opt/smoktolk)
#   STAGING_DIR            где готовим tar.gz (default: /var/backups/smoktolk-full-offsite/staging)
#   RCLONE_CONFIG          путь к rclone.conf
#   RCLONE_REMOTE          remote:path (default: yandex:smoktolk-backup-full)
#   FULL_RETENTION_DAYS    ротация на Я.Диске (default: 30)
#   NOTIFY_SCRIPT          путь к notify_admin.sh
#   LOCK_FILE              путь к flock-файлу
#   TAR_EXTRA_FLAGS        дополнительные флаги к tar (для тестов)
# ============================================================================

set -euo pipefail

# --- Конфигурация ---
BOT_DIR="${BOT_DIR:-/opt/smoktolk/bot}"
SOURCE_DIR="${SOURCE_DIR:-/opt/smoktolk}"
STAGING_DIR="${STAGING_DIR:-/var/backups/smoktolk-full-offsite/staging}"
RCLONE_CONFIG="${RCLONE_CONFIG:-/var/lib/smoktolk-rclone/rclone.conf}"
RCLONE_REMOTE="${RCLONE_REMOTE:-yandex:smoktolk-backup-full}"
FULL_RETENTION_DAYS="${FULL_RETENTION_DAYS:-30}"
NOTIFY_SCRIPT="${NOTIFY_SCRIPT:-$BOT_DIR/scripts/notify_admin.sh}"
LOCK_FILE="${LOCK_FILE:-$STAGING_DIR/.full-offsite.lock}"
TAR_EXTRA_FLAGS="${TAR_EXTRA_FLAGS:-}"

LATEST_NAME="smoktolk-full-latest.tar.gz"
ARCHIVE_GLOB='smoktolk-full_*.tar.gz'

# rclone-флаги. Оптимизированы под медленный/тротлящий канал Я.Диска WebDAV:
#   --timeout 2h            : Я.Диск может "замереть" stream'ом на 10-30 мин при
#                             тротлинге; короткий timeout вызывал бы --retries
#                             с перезаливкой с НУЛЯ → бесконечный цикл.
#   --low-level-retries 20  : при кратковременном обрыве/HTTP 5xx ретраим
#                             chunk без перезапуска всего файла.
#   --retries 3             : общее число попыток всей операции.
#   --contimeout 30s        : быстрый connect-timeout (TCP).
#   --bwlimit               : УБРАН. Канал и так слабый, искусственный лимит
#                             вреден; БД-offsite в 23:50 UTC к этому моменту
#                             ещё не стартует (3ч 50мин запаса).
RCLONE_FLAGS=(
    --config "$RCLONE_CONFIG"
    --timeout 2h
    --contimeout 30s
    --low-level-retries 20
    --retries 3
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

# Explicit notify для вызова из die() — trap ERR не срабатывает на явный exit.
_NOTIFY_SENT=0
notify_failure_explicit() {
    [ "$_NOTIFY_SENT" = "1" ] && return 0
    _NOTIFY_SENT=1
    local rc="${1:-1}"
    set +e
    log "ERROR: full-offsite-backup завершился с кодом $rc, отправляю алерт"
    if [ -x "$NOTIFY_SCRIPT" ]; then
        "$NOTIFY_SCRIPT" offsite-full-failed || log "WARN: notify_admin.sh offsite-full-failed сам упал (rc=$?)"
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
command -v tar    >/dev/null || die "tar не установлен"
command -v gzip   >/dev/null || die "gzip не установлен"
command -v sha256sum >/dev/null || die "sha256sum не установлен"
[ -r "$RCLONE_CONFIG" ] || die "не могу прочитать $RCLONE_CONFIG"
[ -d "$SOURCE_DIR" ]    || die "SOURCE_DIR не существует: $SOURCE_DIR"

mkdir -p "$STAGING_DIR"

# --- Lock ---
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    log "WARN: предыдущий запуск full-offsite ещё работает (lock=$LOCK_FILE), выхожу"
    exit 0
fi

# --- Шаг 1: имя и пути ---
TS="$(date -u '+%Y%m%d_%H%M%S')"
ARCHIVE_NAME="smoktolk-full_${TS}.tar.gz"
STAGED_TGZ="$STAGING_DIR/$ARCHIVE_NAME"

log "source: $SOURCE_DIR"
log "target: $RCLONE_REMOTE/$ARCHIVE_NAME (+ $LATEST_NAME via server-side copy)"

# --- Шаг 2: tar + gzip в staging ---
cleanup_staging() {
    rm -f "$STAGED_TGZ" "$STAGED_TGZ.tmp"
}
trap cleanup_staging EXIT

# tar c:
#   -C "$(dirname SOURCE_DIR)" "$(basename SOURCE_DIR)" — архивируем по относительному пути
#     "smoktolk/..." (а не "/opt/smoktolk/..."), чтобы tar xf работал из любой директории.
#   --warning=no-file-changed --warning=no-file-removed — sqlite/логи могут меняться во время
#     архивации; tar выдаст warning и rc=1. Считаем это OK (rc=1 это warning, rc=2 — ошибка).
#   gzip -1 — быстрое сжатие (важнее скорость, чем 5% экономии: и так ~100 МБ).
SRC_PARENT="$(dirname "$SOURCE_DIR")"
SRC_NAME="$(basename "$SOURCE_DIR")"

set +e
# shellcheck disable=SC2086
tar \
    --warning=no-file-changed \
    --warning=no-file-removed \
    ${TAR_EXTRA_FLAGS:-} \
    -C "$SRC_PARENT" \
    -cf - "$SRC_NAME" 2>"$STAGED_TGZ.tar.stderr" \
    | gzip -1 > "$STAGED_TGZ.tmp"
# КРИТИЧНО: захват PIPESTATUS первой же командой после pipe, иначе массив затрётся.
PIPE_RCS=( "${PIPESTATUS[@]}" )
set -e
TAR_RC="${PIPE_RCS[0]:-0}"
GZIP_RC="${PIPE_RCS[1]:-0}"

# tar rc=0 OK, rc=1 warning (file changed/removed during read) — допустимо для live-системы.
if [ "$TAR_RC" -gt 1 ]; then
    log "ERROR tar stderr: $(cat "$STAGED_TGZ.tar.stderr" 2>/dev/null | tr '\n' ' ')"
    die "tar упал (rc=$TAR_RC)"
fi
if [ "$GZIP_RC" -ne 0 ]; then
    die "gzip упал (rc=$GZIP_RC)"
fi
rm -f "$STAGED_TGZ.tar.stderr"

mv "$STAGED_TGZ.tmp" "$STAGED_TGZ"

TGZ_SIZE="$(stat -c %s "$STAGED_TGZ")"
TGZ_SHA="$(sha256sum "$STAGED_TGZ" | awk '{print $1}')"
log "staged: $ARCHIVE_NAME ($TGZ_SIZE bytes, sha256=${TGZ_SHA:0:12}, tar_rc=$TAR_RC)"

# Sanity: архив не должен быть подозрительно мелким (защита от пустого SOURCE_DIR).
if [ "$TGZ_SIZE" -lt 1024 ]; then
    die "архив слишком мал: $TGZ_SIZE байт — возможно, $SOURCE_DIR пуст"
fi

# --- Шаг 3a: загружаем history (медленный upload по сети) ---
# Из-за тротлинга Я.Диска WebDAV это может занять до 60-90 минут на ~100 МБ.
# Поэтому TimeoutStartSec в .service = 180min (запас 2×).
log "uploading history (this may take up to 90 min due to Yandex WebDAV throttling)..."
UPLOAD_START="$(date +%s)"
rclone "${RCLONE_FLAGS[@]}" copyto "$STAGED_TGZ" "$RCLONE_REMOTE/$ARCHIVE_NAME" \
    || die "rclone copyto (history) упал"
UPLOAD_END="$(date +%s)"
log "uploaded history: $RCLONE_REMOTE/$ARCHIVE_NAME (took $((UPLOAD_END - UPLOAD_START))s)"

# --- Шаг 3b: server-side copy history → latest ---
# WebDAV-сервер Я.Диска поддерживает COPY-метод: данные НЕ передаются по сети,
# просто создаётся вторая ссылка на тот же blob. Доказано тестом
# (см. PR-comment: 25b src→dst за 27s; для 100 MB также ~10-60s, не часы).
log "server-side copy: $ARCHIVE_NAME → $LATEST_NAME (no network upload)"
SS_START="$(date +%s)"
rclone "${RCLONE_FLAGS[@]}" copyto "$RCLONE_REMOTE/$ARCHIVE_NAME" "$RCLONE_REMOTE/$LATEST_NAME" \
    || die "rclone copyto (latest, server-side) упал"
SS_END="$(date +%s)"
log "uploaded latest:  $RCLONE_REMOTE/$LATEST_NAME (server-side, took $((SS_END - SS_START))s)"

# --- Шаг 4: проверка целостности через hashsum (WebDAV может не поддерживать) ---
REMOTE_HASH="$(rclone "${RCLONE_FLAGS[@]}" hashsum sha256 "$RCLONE_REMOTE/$ARCHIVE_NAME" 2>/dev/null | awk '{print $1}' || true)"
if [ -n "$REMOTE_HASH" ] && [ "$REMOTE_HASH" != "UNSUPPORTED" ]; then
    if [ "$REMOTE_HASH" = "$TGZ_SHA" ]; then
        log "integrity: remote sha256 matches local"
    else
        die "integrity FAIL: local=$TGZ_SHA remote=$REMOTE_HASH"
    fi
else
    log "integrity: remote hash not provided by WebDAV — sverka skipped (OK для Я.Диска)"
fi

# --- Шаг 5: retention на стороне Я.Диска ---
# Удаляем smoktolk-full_*.tar.gz старше FULL_RETENTION_DAYS.
# smoktolk-full-latest.tar.gz паттерну не соответствует → не трогаем.
DELETE_OUTPUT="$(rclone "${RCLONE_FLAGS[@]}" delete \
    --include "$ARCHIVE_GLOB" \
    --min-age "${FULL_RETENTION_DAYS}d" \
    "$RCLONE_REMOTE" 2>&1 || true)"
log "retention output: ${DELETE_OUTPUT:-(nothing deleted)}"

# --- Шаг 6: статистика remote ---
REMOTE_FILES="$(rclone "${RCLONE_FLAGS[@]}" lsf --include "$ARCHIVE_GLOB" "$RCLONE_REMOTE" 2>/dev/null | wc -l || echo 0)"
log "stats: remote history files = $REMOTE_FILES (retention=${FULL_RETENTION_DAYS}d)"

# --- Recovery-уведомление ---
trap - ERR
if [ -x "$NOTIFY_SCRIPT" ]; then
    "$NOTIFY_SCRIPT" offsite-full-recovered || log "WARN: notify_admin.sh offsite-full-recovered упал (rc=$?), но full-offsite успешен"
fi

log "OK: full-offsite backup complete ($TGZ_SIZE bytes)"
exit 0
