#!/usr/bin/env bash
# ============================================================================
# backup.sh - ezhednevnyy bekap SQLite-bazy SMOKTOLK-bota.
#
# Zapuskaetsya systemd-taymerom smoktolk-backup.timer ezhednevno v 04:00.
# Logi: /opt/smoktolk/bot/logs/backup.log (via StandardOutput=append:...)
#
# Alertovaya semantika:
#   - Pri lyuboy oshibke (die / non-zero exit) trap ERR vyzyvaet
#     notify_admin.sh backup-failed -> sozdaet state-fayl i shlet alert.
#   - Pri uspeshnom zavershenii zaprashivaem backup-recovered, kotoryy
#     sam reshit: esli state-fayl est' - poslat RECOVERED i udalit ego.
#   - systemd-yunit smoktolk-backup-alert.service (cherez OnFailure=) -
#     dopolnitelnaya strakhovka, esli backup.sh upadet do trap ERR
#     (naprimer, OOM, kill -9, oshibka set -u v samom nachale).
# ============================================================================

set -euo pipefail

# --- Konfiguratsiya ---
BOT_DIR="${BOT_DIR:-/opt/smoktolk/bot}"
DB_PATH="${DB_PATH:-$BOT_DIR/data/smoktolk.db}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/smoktolk}"
RETENTION_DAYS="${RETENTION_DAYS:-150}"
MAX_TOTAL_BYTES="${MAX_TOTAL_BYTES:-5368709120}"   # 5 GiB
SAFETY_NET_DAYS="${SAFETY_NET_DAYS:-7}"
LOCK_FILE="${LOCK_FILE:-$BACKUP_DIR/.backup.lock}"
NOTIFY_SCRIPT="${NOTIFY_SCRIPT:-$BOT_DIR/scripts/notify_admin.sh}"

HASH_FILE="$BACKUP_DIR/.last_dump.sha256"
DATE="$(date +%Y%m%d_%H%M%S)"
BACKUP_PREFIX="smoktolk_"
BACKUP_GLOB="${BACKUP_PREFIX}*.db"

# --- Utility ---
log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$*"
}

# --- Alertovyy trap ---
# Sleetsya odin raz pri lyuboy oshibke (set -e). Vnutri trap'a otklyuchaem
# set -e, chtoby oshibka v notify_admin.sh ne meshala vyyti s pravilnym kodom.
notify_failure() {
    local rc=$?
    set +e
    log "ERROR: backup zavershilsya s kodom $rc, otpravlyayu alert"
    if [ -x "$NOTIFY_SCRIPT" ]; then
        "$NOTIFY_SCRIPT" backup-failed || log "WARN: notify_admin.sh backup-failed sam upal (rc=$?)"
    else
        log "WARN: $NOTIFY_SCRIPT ne ispolnyaem ili otsutstvuyet - alert ne otpravlen"
    fi
    exit "$rc"
}
trap notify_failure ERR

die() {
    log "ERROR: $*"
    exit 1
}

file_mtime() {
    [ -f "$1" ] && stat -c %Y "$1" || echo 0
}

total_size() {
    local dir="$1" pattern="$2"
    find "$dir" -maxdepth 1 -name "$pattern" -type f -printf '%s\n' 2>/dev/null \
        | awk '{s+=$1} END {print s+0}'
}

# --- Proverki ---
[ -f "$DB_PATH" ] || die "BD ne naydena: $DB_PATH"
command -v sqlite3 >/dev/null || die "sqlite3 ne ustanovlen"
command -v sha256sum >/dev/null || die "sha256sum ne ustanovlen"

mkdir -p "$BACKUP_DIR"

# --- Lock ---
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    log "WARN: predydushchiy zapusk eshche rabotaet (lock=$LOCK_FILE), vykhozhu"
    # Eto NE oshibka - drugoy ekzemplyar uzhe rabotaet, prosto vyhodim 0.
    # ERR-trap ne srabotayet, recovery ne nuzhen.
    exit 0
fi

# --- Shag 1: atomarnyy snimok BD vo vremennyy fayl ---
TMP_SNAPSHOT="$BACKUP_DIR/.tmp_snapshot_$$.db"
cleanup() {
    rm -f "$TMP_SNAPSHOT" "$TMP_SNAPSHOT-journal" "$TMP_SNAPSHOT-wal" "$TMP_SNAPSHOT-shm"
}
trap cleanup EXIT

sqlite3 "$DB_PATH" ".backup '$TMP_SNAPSHOT'" \
    || die "sqlite3 .backup upal"

[ -s "$TMP_SNAPSHOT" ] || die "vremennyy snimok pustoy"

# --- Shag 2: SHA-256 ot SQL-dampa snimka ---
NEW_HASH="$(sqlite3 "$TMP_SNAPSHOT" .dump | sha256sum | awk '{print $1}')"
[ -n "$NEW_HASH" ] || die "ne udalos poschitat khesh dampa"

# --- Shag 3: reshenie o bekape ---
SHOULD_BACKUP=1
SKIP_REASON=""

LAST_BACKUP="$(find "$BACKUP_DIR" -maxdepth 1 -name "$BACKUP_GLOB" -type f -printf '%T@ %p\n' 2>/dev/null \
    | sort -nr | head -1 | awk '{print $2}')"

if [ -n "$LAST_BACKUP" ] && [ -f "$HASH_FILE" ]; then
    OLD_HASH="$(cat "$HASH_FILE" 2>/dev/null || true)"
    if [ "$NEW_HASH" = "$OLD_HASH" ]; then
        LAST_MTIME="$(file_mtime "$LAST_BACKUP")"
        NOW="$(date +%s)"
        AGE_DAYS=$(( (NOW - LAST_MTIME) / 86400 ))
        if [ "$AGE_DAYS" -lt "$SAFETY_NET_DAYS" ]; then
            SHOULD_BACKUP=0
            SKIP_REASON="no data changes (last backup ${AGE_DAYS}d ago, safety-net=${SAFETY_NET_DAYS}d)"
        else
            log "INFO: dannye ne menyalis ${AGE_DAYS} dney - delaem safety-net bekap"
        fi
    fi
fi

# --- Shag 4: sozdaem bekap ili propuskaem ---
if [ "$SHOULD_BACKUP" -eq 0 ]; then
    log "skipped: $SKIP_REASON"
else
    FINAL_PATH="$BACKUP_DIR/${BACKUP_PREFIX}${DATE}.db"
    mv "$TMP_SNAPSHOT" "$FINAL_PATH"
    echo "$NEW_HASH" > "$HASH_FILE"
    SIZE="$(stat -c %s "$FINAL_PATH")"
    log "backup ok: ${BACKUP_PREFIX}${DATE}.db (${SIZE} bytes, sha256=${NEW_HASH:0:12})"
fi

# --- Shag 5a: retenshn po vozrastu ---
DELETED_AGE=0
while IFS= read -r -d '' old; do
    rm -f "$old"
    DELETED_AGE=$((DELETED_AGE + 1))
done < <(find "$BACKUP_DIR" -maxdepth 1 -name "$BACKUP_GLOB" -type f -mtime "+$RETENTION_DAYS" -print0)
[ "$DELETED_AGE" -gt 0 ] && log "retention: udaleno po vozrastu (>${RETENTION_DAYS} dn.): $DELETED_AGE sht."

# --- Shag 5b: retenshn po summarnomu razmeru ---
DELETED_SIZE=0
CURRENT_SIZE="$(total_size "$BACKUP_DIR" "$BACKUP_GLOB")"
if [ "$CURRENT_SIZE" -gt "$MAX_TOTAL_BYTES" ]; then
    while [ "$CURRENT_SIZE" -gt "$MAX_TOTAL_BYTES" ]; do
        OLDEST="$(find "$BACKUP_DIR" -maxdepth 1 -name "$BACKUP_GLOB" -type f -printf '%T@ %p\n' 2>/dev/null \
            | sort -n | head -1 | awk '{print $2}')"
        [ -z "$OLDEST" ] && break
        REMAINING="$(find "$BACKUP_DIR" -maxdepth 1 -name "$BACKUP_GLOB" -type f | wc -l)"
        if [ "$REMAINING" -le 1 ]; then
            log "WARN: ostavshiysya bekap ($OLDEST) bolshe limita, no ne udalyayu - eto posledniy"
            break
        fi
        rm -f "$OLDEST"
        DELETED_SIZE=$((DELETED_SIZE + 1))
        CURRENT_SIZE="$(total_size "$BACKUP_DIR" "$BACKUP_GLOB")"
    done
    log "retention: udaleno po limitu razmera (>${MAX_TOTAL_BYTES} B): $DELETED_SIZE sht., itogo: ${CURRENT_SIZE} B"
fi

# --- Itogovaya statistika ---
TOTAL_FILES="$(find "$BACKUP_DIR" -maxdepth 1 -name "$BACKUP_GLOB" -type f | wc -l)"
TOTAL_BYTES="$(total_size "$BACKUP_DIR" "$BACKUP_GLOB")"
log "stats: files=$TOTAL_FILES, total_size=${TOTAL_BYTES}B"

# --- Recovery-uvedomlenie ---
# Snimaem ERR-trap, chtoby oshibka v notify_admin.sh ne triggerila backup-failed.
trap - ERR
if [ -x "$NOTIFY_SCRIPT" ]; then
    "$NOTIFY_SCRIPT" backup-recovered || log "WARN: notify_admin.sh backup-recovered upal (rc=$?), no bekap uspeshen"
fi

exit 0
