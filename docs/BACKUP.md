# Бэкапы БД SMOKTOLK

## Что бэкапим
Только SQLite-базу /opt/smoktolk/bot/data/smoktolk.db.

Каталог товаров (data/catalog.xlsx) не бэкапится: первоисточник на Я.Диске,
бот скачивает его при старте через catalog.refresh().

## Где хранятся
/var/backups/smoktolk/ — вне директории приложения.
Владелец: smoktolk:smoktolk.
Имена: smoktolk_YYYYMMDD_HHMMSS.db

## Расписание (systemd timer)

Запуском управляет `smoktolk-backup.timer`. Cron больше не используется
(мигрировано в PR #ops-backup-alerts, 2026-05-14).

    OnCalendar=*-*-* 04:00:00     # ежедневно в 04:00 MSK
    Persistent=true               # догнать пропущенный запуск (если сервер был выключен)
    RandomizedDelaySec=2min       # случайный jitter ±2 мин

Юниты:

| Юнит                                 | Назначение                                          |
|--------------------------------------|-----------------------------------------------------|
| `smoktolk-backup.timer`              | расписание                                          |
| `smoktolk-backup.service`            | запускает `/opt/smoktolk/bot/backup.sh` (oneshot)   |
| `smoktolk-backup-alert.service`      | OnFailure-страховка: шлёт TG-алерт, если service упал |

Управление:

    sudo systemctl status  smoktolk-backup.timer
    systemctl list-timers smoktolk-backup.timer
    sudo systemctl start   smoktolk-backup.service   # запустить вручную
    sudo journalctl -u     smoktolk-backup.service -n 50 --no-pager

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

Через systemd (предпочтительно — единый канал логов и алертов):

    sudo systemctl start smoktolk-backup.service

Напрямую (для отладки):

    sudo -u smoktolk /opt/smoktolk/bot/backup.sh

Принудительный (даже при совпадении хеша):

    sudo -u smoktolk rm /var/backups/smoktolk/.last_dump.sha256
    sudo systemctl start smoktolk-backup.service

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

Свежий бэкап есть за последние 2 суток?

    find /var/backups/smoktolk -name 'smoktolk_*.db' -mtime -2 | head -1

Пустой вывод = последний бэкап старше 2 дней — что-то не так. См. также
раздел «Алерты» ниже.

## Алерты в Telegram

Алерты идут в чат админа (ADMIN_ID) через `scripts/notify_admin.sh`.

| Событие         | Reason             | Когда отправляется                                              |
|-----------------|--------------------|-----------------------------------------------------------------|
| 🚨 FAILED       | `backup-failed`    | `backup.sh` упал (trap ERR) ИЛИ сервис ушёл в failed (OnFailure) |
| ✅ RECOVERED    | `backup-recovered` | Очередной успешный бэкап после состояния failed                 |

Защита от дубликатов — state-файл `/var/lib/smoktolk-backup/failed`:

- Первый сбой → файл создан, FAILED-алерт отправлен.
- Повторные сбои → файл уже есть, новые FAILED-алерты не шлются.
- Успешный запуск → файл удалён + один RECOVERED-алерт.

State-каталог `/var/lib/smoktolk-backup/` создаётся systemd через
директиву `StateDirectory=` (владелец smoktolk:smoktolk, права 0775).

### Что делать при FAILED-алерте

1. `sudo systemctl status smoktolk-backup.service`
2. `sudo tail -50 /opt/smoktolk/bot/logs/backup.log`
3. `sudo journalctl -u smoktolk-backup.service -n 100 --no-pager`

Типовые причины: нет места на диске; повреждение БД (sqlite3 integrity check
внутри backup.sh); права на каталоги; пропавший /var/lib/smoktolk-backup.

После починки запускаем вручную: `sudo systemctl start smoktolk-backup.service`.
Если успешно — придёт RECOVERED.

## Связанные документы

- SPEC §15 — Бэкапы БД (логика, инкременты)
- SPEC §15.7 — systemd timer + Telegram-алерты (этот документ — операционный)


## Healthcheck свежести

Параллельно с основным бэкапом работает healthcheck-таймер, который проверяет,
что в `/var/backups/smoktolk/` есть файл младше 36 часов.

| Юнит                                       | Когда         | Что делает |
|--------------------------------------------|---------------|------------|
| `smoktolk-backup-healthcheck.timer`        | 10:00 MSK     | расписание |
| `smoktolk-backup-healthcheck.service`      | (oneshot)     | запускает `scripts/backup_healthcheck.sh` |

Скрипт `scripts/backup_healthcheck.sh`:
- ищет `smoktolk_*.db` младше `MAX_AGE_HOURS=36` через `find -mmin`;
- если такого нет — зовёт `scripts/notify_admin.sh backup-failed` и завершается с кодом 1;
- если есть — пишет OK в journal и выходит с 0.

Зачем это нужно при наличии `OnFailure=` в основном `smoktolk-backup.service`:
`OnFailure` ловит сценарий "service запустился и упал". Healthcheck ловит
сценарий "timer вообще не сработал" (юнит выключен, systemd сошёл с ума,
диск размонтировался) — это другая угроза, дополняющая основной механизм.

Управление:

    sudo systemctl status smoktolk-backup-healthcheck.timer
    sudo systemctl start  smoktolk-backup-healthcheck.service
    sudo journalctl -u    smoktolk-backup-healthcheck.service -n 50 --no-pager

## DR-drill (учения по восстановлению)

Раз в квартал нужно проверять, что бэкап реально пригоден к восстановлению.
Минимальная процедура (около 1 минуты):

DRILL=$(mktemp -d)
cp "(ls−t/var/backups/smoktolk/smoktolk∗.db∣head−1)""DRILL/restored.db"
sqlite3 "$DRILL/restored.db" 'PRAGMA integrity_check;'
sqlite3 "$DRILL/restored.db" '.tables'
sqlite3 "$DRILL/restored.db" 'SELECT COUNT(*) FROM users;'
rm -rf "$DRILL"


Полная процедура (с реальным запуском бота на восстановленной БД) — TODO,
делается при первой серьёзной миграции схемы.

### История drill'ов

| Дата       | Результат | Заметки |
|------------|-----------|---------|
| 2026-05-14 | OK        | integrity_check=ok, все 8 таблиц на месте, users=5 (совпадает с prod) |

---

## Offsite-бэкап на Я.Диск (PR #ops-offsite-yandex-disk, 2026-05-15)

### Зачем

Локальные бэкапы в `/var/backups/smoktolk/` живут на том же VPS, что и сам бот.
Сценарии, которые они НЕ покрывают:

- удалили/потеряли VPS (хостер закрылся, аккаунт заблокирован);
- диск вышел из строя физически или повреждена файловая система;
- ошибочный `rm -rf` от админа задел и `/var/backups`;
- ransomware/компрометация — атакующий зашифровал в т.ч. локальные копии.

Offsite-копия на Я.Диске решает все четыре кейса.

### Что и куда отправляется

| Объект                                  | Назначение                                          |
|-----------------------------------------|-----------------------------------------------------|
| `smoktolk-latest.db.gz`                 | всегда последняя копия с фиксированным именем — для быстрого DR без поиска |
| `smoktolk_YYYYMMDD_HHMMSS.db.gz`        | история, ротация 30 дней                            |

Источник — последний (по mtime) файл из `/var/backups/smoktolk/smoktolk_*.db`.
Перед отправкой gzip-сжатие (`-9`) в staging-каталог `/var/backups/smoktolk-offsite/staging/`.

### Конфигурация rclone

- Бэкенд: `webdav` (https://webdav.yandex.ru/)
- Конфиг: `/var/lib/smoktolk-rclone/rclone.conf` (mode 0600, owner `smoktolk:smoktolk`)
- Пароль — отдельный **app-password** Яндекс.ID с именем `smoktolk-backup-webdav`,
  обфусцирован через `rclone obscure`. **НЕ** основной пароль аккаунта.
- Удалённая папка: `yandex:smoktolk-backup/`

### Расписание (systemd timer)

| Юнит                                            | Когда            | Что делает                                        |
|-------------------------------------------------|------------------|---------------------------------------------------|
| `smoktolk-backup-offsite.timer`                 | 02:50 MSK (23:50 UTC) | запускает `backup_offsite.sh` (через ~5 мин после локального бэкапа в 04:00 MSK) |
| `smoktolk-backup-offsite.service`               | (oneshot)        | gzip → rclone copyto (2 копии) → retention 30d   |
| `smoktolk-backup-offsite-alert.service`         | OnFailure        | страховка: алерт TG если service упал            |
| `smoktolk-backup-offsite-healthcheck.timer`     | 11:00 MSK (08:00 UTC) | запускает healthcheck (через 1 час после локального healthcheck §10) |
| `smoktolk-backup-offsite-healthcheck.service`   | (oneshot)             | `rclone lsl yandex:smoktolk-backup/smoktolk-latest.db.gz`, проверка `MAX_AGE_HOURS=30` |

### Telegram-алерты

Семантика зеркальная локальным:

- 🚨 `offsite-failed` — первый сбой (из `trap ERR` в `backup_offsite.sh`,
  из `OnFailure=smoktolk-backup-offsite-alert.service`, или из healthcheck).
- ✅ `offsite-recovered` — первый успех после сбоя.
- Анти-дубликат через state-файл `/var/lib/smoktolk-backup/offsite-failed`.

### Управление

    sudo systemctl status  smoktolk-backup-offsite.timer
    systemctl list-timers  smoktolk-backup-offsite.timer
    sudo systemctl start   smoktolk-backup-offsite.service   # вручную
    sudo journalctl -u     smoktolk-backup-offsite.service -n 50 --no-pager
    tail -50 /opt/smoktolk/bot/logs/backup-offsite.log

### DR: восстановление из offsite

    # 1. Скачать последнюю копию
    sudo -u smoktolk rclone --config /var/lib/smoktolk-rclone/rclone.conf \
        copy yandex:smoktolk-backup/smoktolk-latest.db.gz /tmp/

    # 2. Распаковать
    gunzip /tmp/smoktolk-latest.db.gz   # → /tmp/smoktolk-latest.db

    # 3. Проверить целостность
    sqlite3 /tmp/smoktolk-latest.db 'PRAGMA integrity_check;'

    # 4. Остановить бота и заменить БД
    sudo systemctl stop smoktolk-bot
    sudo cp /opt/smoktolk/bot/data/smoktolk.db /opt/smoktolk/bot/data/smoktolk.db.before-dr.$(date +%s)
    sudo cp /tmp/smoktolk-latest.db /opt/smoktolk/bot/data/smoktolk.db
    sudo chown smoktolk:smoktolk /opt/smoktolk/bot/data/smoktolk.db
    sudo systemctl start smoktolk-bot

### Ротация секретов

При компрометации app-password (или раз в год профилактически):

1. https://id.yandex.ru/security/app-passwords → удалить `smoktolk-backup-webdav`
2. Создать новый с тем же именем
3. `rclone obscure '<новый_пароль>'` → подставить в `/var/lib/smoktolk-rclone/rclone.conf` в поле `pass=`
4. Тест: `sudo -u smoktolk /opt/smoktolk/bot/scripts/backup_offsite.sh`
