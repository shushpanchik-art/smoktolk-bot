#!/usr/bin/env bash
# Healthcheck свежести бэкапов SMOKTOLK.
#
# Запускается отдельным systemd timer (smoktolk-backup-healthcheck.timer)
# в 10:00 MSK — через 6 часов после основного бэкапа в 04:00.
# Если в /var/backups/smoktolk/ нет файла младше MAX_AGE_HOURS — шлёт алерт
# через scripts/notify_admin.sh backup-failed.
#
# ВАЖНО про MAX_AGE_HOURS = 192 (8 дней):
# backup.sh имеет SAFETY_NET_DAYS=7 — при отсутствии изменений в БД он
# валидно пропускает создание файла до 7 дней подряд. На 7-й день он
# принудительно делает бэкап (safety-net). Healthcheck должен быть
# толерантен к этому: 7д safety-net + 24ч запаса = 192 часа.
#
# Если файл старше 192ч — это значит даже safety-net не сработал, что
# реальный сбой (выключенный таймер, упавший systemd, размонтированный диск).
#
# Зачем это нужно, если есть OnFailure= в smoktolk-backup.service:
# OnFailure ловит ситуацию "service запустился и упал". Этот healthcheck
# ловит ситуацию "timer вообще не сработал".
#
# ENV-override для тестов:
#   BACKUP_DIR (default: /var/backups/smoktolk)
#   MAX_AGE_HOURS (default: 192)
#   NOTIFY_SCRIPT (default: /opt/smoktolk/bot/scripts/notify_admin.sh)

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/smoktolk}"
MAX_AGE_HOURS="${MAX_AGE_HOURS:-192}"
NOTIFY_SCRIPT="${NOTIFY_SCRIPT:-/opt/smoktolk/bot/scripts/notify_admin.sh}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] healthcheck: $*"; }

# find -mmin принимает минуты. 192h = 11520min.
max_age_min=$(( MAX_AGE_HOURS * 60 ))

if [ ! -d "$BACKUP_DIR" ]; then
    log "ERROR: BACKUP_DIR не существует: $BACKUP_DIR"
    "$NOTIFY_SCRIPT" backup-failed "healthcheck: $BACKUP_DIR not found" || true
    exit 1
fi

# Свежий файл = бэкап младше MAX_AGE_HOURS
fresh=$(find "$BACKUP_DIR" -maxdepth 1 -name 'smoktolk_*.db' -mmin "-${max_age_min}" -print -quit 2>/dev/null || true)

if [ -z "$fresh" ]; then
    log "FAIL: нет бэкапа младше ${MAX_AGE_HOURS}ч в $BACKUP_DIR"
    "$NOTIFY_SCRIPT" backup-failed "healthcheck: no fresh backup (<${MAX_AGE_HOURS}h)" || true
    exit 1
fi

log "OK: свежий бэкап найден — $(basename "$fresh")"
exit 0
