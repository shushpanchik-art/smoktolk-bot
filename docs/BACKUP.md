# Бэкапы БД SMOKTOLK

## Что бэкапим
Только SQLite-базу /opt/smoktolk/bot/data/smoktolk.db.

Каталог товаров (data/catalog.xlsx) не бэкапится: первоисточник на Я.Диске,
бот скачивает его при старте через catalog.refresh().

## Где хранятся
/var/backups/smoktolk/ — вне директории приложения.
Владелец: smoktolk:smoktolk.
Имена: smoktolk_YYYYMMDD_HHMMSS.db

## Cron

    0 4 * * * /opt/smoktolk/bot/backup.sh >> /opt/smoktolk/bot/logs/backup.log 2>&1

Ежедневно в 04:00 MSK от пользователя smoktolk.

## Логика "бэкапить только при изменениях"

1. Атомарный снимок БД через sqlite3 .backup во временный файл.
2. SHA-256 от sqlite3 .dump снимка (хеш по данным, не по байтам).
3. Сравниваем с предыдущим хешем (.last_dump.sha256).
4. Если совпал И последний бэкап моложе SAFETY_NET_DAYS — skip.
   Иначе делаем бэкап.

Safety-net: при отсутствии изменений N дней (по умолчанию 7) всё равно
делаем контрольную копию.

## Ретеншн

- По возрасту: файлы старше RETENTION_DAYS (150) удаляются.
- По размеру: суммарный > MAX_TOTAL_BYTES (5 GiB) — удаляем самые старые.
- Защита: последний оставшийся бэкап не удаляется никогда.

## Параллельные запуски

Lock-файл .backup.lock через flock -n. Параллельный запуск выйдет с WARN.

## Лог

/opt/smoktolk/bot/logs/backup.log

Примеры строк:

    [2026-05-14 04:00:01 MSK] backup ok: smoktolk_20260514_040001.db (69632 bytes, sha256=a3f1b2c4d5e6)
    [2026-05-15 04:00:01 MSK] skipped: no data changes (last backup 1d ago, safety-net=7d)

## Ручной запуск

    sudo -u smoktolk /opt/smoktolk/bot/backup.sh

Принудительный (даже при совпадении хеша):

    sudo -u smoktolk rm /var/backups/smoktolk/.last_dump.sha256
    sudo -u smoktolk /opt/smoktolk/bot/backup.sh

## Восстановление

    sudo systemctl stop smoktolk-bot
    sudo -u smoktolk cp /opt/smoktolk/bot/data/smoktolk.db /opt/smoktolk/bot/data/smoktolk.db.before_restore
    sudo -u smoktolk cp /var/backups/smoktolk/smoktolk_YYYYMMDD_HHMMSS.db /opt/smoktolk/bot/data/smoktolk.db
    sudo systemctl start smoktolk-bot
    sudo journalctl -u smoktolk-bot -n 50 --no-pager

## ENV-параметры

BOT_DIR, DB_PATH, BACKUP_DIR, RETENTION_DAYS, MAX_TOTAL_BYTES,
SAFETY_NET_DAYS, LOCK_FILE.

## Мониторинг

    find /var/backups/smoktolk -name 'smoktolk_*.db' -mtime -2 | head -1

Пустой вывод = последний бэкап старше 2 дней, что-то не так.
