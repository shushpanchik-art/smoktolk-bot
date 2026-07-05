# Operations runbook

Документ описывает повседневные операционные процедуры: деплой, проверка
здоровья, диагностика, откаты. Не дублирует `BACKUP.md` и `SECURITY.md` —
ссылается на них.

---

## 0. Доступ и sudo

На сервере `telegram-bot` рабочий пользователь — `shushpanchik_art`.
Для него настроен `sudo` с правилом **`NOPASSWD: ALL`**
(проверить: `sudo -n -l`). Практические следствия:

- **Пароль root НЕ нужен и НЕ спрашивается**, если команда идёт через `sudo`.
- Если система вдруг просит пароль (`Authenticating as: root` / `Password:`),
  значит команду запустили **без** `sudo` — она пошла через polkit.
  Нажми `Ctrl+C` и запусти ту же команду **с `sudo` в начале**.
- **Не** используй `sudo -i`, `sudo su`, `sudo bash` — они открывают
  интерактивный root-шелл, который «зависает». Всегда пиши команду целиком:
  `sudo <команда>`.

Базовые команды управления ботом:

    sudo systemctl restart  smoktolk-bot.service    # рестарт после обновления кода
    sudo systemctl status   smoktolk-bot.service    # статус (Active, Main PID, память)
    sudo systemctl is-active smoktolk-bot.service   # коротко: active / inactive
    sudo journalctl -u smoktolk-bot.service -n 50    # последние 50 строк логов
    sudo journalctl -u smoktolk-bot.service -f       # логи в реальном времени (Ctrl+C выход)

Проверка, что рестарт реально произошёл: `Main PID` в `status` должен
**измениться** после команды restart.

---

## 1. Деплой systemd-юнитов

### Source of Truth

Каноническая версия unit-файлов для бота и связанных таймеров живёт в
репозитории, в каталоге `systemd/`:

    systemd/
    ├── smoktolk-bot.service              # основной юнит бота
    └── smoktolk-bot.service.d/
        ├── 10-alerts.conf                # OnFailure → smoktolk-alert@
        └── 20-resources.conf             # MemoryHigh/Max, TasksMax, OOMScoreAdjust

Структура **1:1** совпадает с `/etc/systemd/system/` на проде. Любые ручные
правки в `/etc/systemd/system/` запрещены — они будут затёрты следующим
деплоем. Изменения вносятся **только** через PR в `systemd/`.

### Скрипт `scripts/deploy_systemd.sh`

Идемпотентный деплой с timestamped-бэкапами и rollback-on-failure.

**Сухой прогон (обязательный шаг перед реальным деплоем):**

    sudo ./scripts/deploy_systemd.sh --dry-run

Покажет `diff -u` между репозиторием и `/etc/systemd/system/`. Если diff
пустой — изменений нет, ничего применять не нужно.

**Реальный деплой без рестарта (только подмена файлов + daemon-reload):**

    sudo ./scripts/deploy_systemd.sh

**Деплой с рестартом сервиса и автоматическим rollback при падении:**

    sudo ./scripts/deploy_systemd.sh --restart smoktolk-bot.service

Скрипт:
1. Делает timestamped-бэкап в `/var/backups/smoktolk-systemd/YYYYMMDD-HHMMSS/`
   (все unit-файлы, которые планируется изменить).
2. Копирует новые версии в `/etc/systemd/system/`.
3. Делает `systemctl daemon-reload`.
4. Если передан `--restart`, рестартит сервис и через 3 секунды проверяет
   `systemctl is-active`. Если `failed` → автоматически восстанавливает
   файлы из бэкапа, делает daemon-reload + рестарт старой версии,
   завершается с exit code 1.
5. Печатает команду ручного отката (на случай если деградация замечена
   позже, не моментально).

**Бэкапы**: `/var/backups/smoktolk-systemd/` — каталог принадлежит `root`,
ретеншн не настроен (юнит-файлы крошечные, чистка раз в год вручную).

### Откат

Автоматический (внутри скрипта) — если сервис не поднялся через 3 секунды
после `--restart`.

Ручной — для случаев, когда деградация замечена позже:

    sudo cp -a /var/backups/smoktolk-systemd/<TIMESTAMP>/* /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl restart smoktolk-bot.service

Точная команда ручного отката печатается скриптом в конце успешного деплоя.

---

## 2. Health checks

### Бот живой?

    systemctl is-active smoktolk-bot.service
    systemctl status   smoktolk-bot.service --no-pager

Ожидаемое: `active (running)`, MainPID стабильный, Memory < 500M
(`MemoryHigh` из `20-resources.conf`), Tasks ≤ 10.

### Webhook кассы слушает?

    sudo ss -tlnp | grep ':8080'

Ожидаемое: `LISTEN 127.0.0.1:8080` от процесса `python`.

### Журнал — есть ли свежие ошибки?

    sudo journalctl -u smoktolk-bot.service --since "1 hour ago" \
        | grep -iE 'error|denied|eperm|traceback|exception'

Пусто = всё ок. Если что-то нашлось — см. `logs/bot.log` для деталей
(`journalctl` показывает только stdout/stderr, прикладной лог пишется в
файл через Python `logging`).

### Security score юнита

    systemd-analyze security smoktolk-bot.service | tail -3

Текущий baseline: **1.3 OK**. Если после деплоя стало хуже 4.0 — что-то
пошло не так, см. `docs/SECURITY.md` §4 и diff с прошлой версией юнита.

### OOM-приоритет

    PID=$(systemctl show smoktolk-bot.service -p MainPID --value)
    cat /proc/$PID/oom_score_adj   # ожидаемое: -500

---

## 3. Где что лежит

| Артефакт | Путь | Owner |
|---|---|---|
| Код бота | `/opt/smoktolk/bot/` | `smoktolk:smoktolk` |
| venv | `/opt/smoktolk/bot/venv/` | `smoktolk:smoktolk` |
| БД | `/opt/smoktolk/bot/data/smoktolk.db` | `smoktolk:smoktolk` |
| Прикладные логи | `/opt/smoktolk/bot/logs/bot.log` | `smoktolk:smoktolk` |
| systemd journal | `journalctl -u smoktolk-bot.service` | systemd |
| Бэкапы БД (L1) | `/var/backups/smoktolk/` | `smoktolk:smoktolk` |
| Бэкапы systemd-юнитов | `/var/backups/smoktolk-systemd/` | `root:root` |
| Offsite БД (L2) | Я.Диск `smoktolk-backup/` | yandex_native |
| Offsite полный архив (L3) | Я.Диск, см. `BACKUP.md` §L3 | — |

---

## См. также

- [`docs/SECURITY.md`](SECURITY.md) — security posture, runtime hardening бота
- [`docs/BACKUP.md`](BACKUP.md) — регламент бэкапов БД (L1/L2/L3) и DR-drill
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — workflow разработки и git-hooks
