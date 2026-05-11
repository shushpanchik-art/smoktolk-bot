# SMOKTOLK Bot — Техническая спецификация v1.2

**Дата:** 2026-05-10
**Предыдущая версия:** v1.1 (2026-05-09), сохранена в `SPEC.md.v1.1.bak.*`
**Админ:** @utc2000 (Telegram ID: **5899721537**)
**Бот:** @SMOKTOLK_bot (ID: 8400165268)
**Сервер:** telegram-bot (Debian 12, Python 3.11.2), путь `/opt/smoktolk/bot/`
**Сервис:** `smoktolk-bot.service` (systemd, enabled, user `smoktolk`)
**Логи:** `/opt/smoktolk/bot/logs/bot.log` + `journalctl -u smoktolk-bot`
**Бэкапы:** cron от `smoktolk` → `/opt/smoktolk/bot/backups/`
**GitHub:** https://github.com/shushpanchik-art/smoktolk-bot (private)

---

## 🚨 0. ПРАВИЛА БЕЗОПАСНОСТИ ПРИ РАБОТЕ С AI-АССИСТЕНТОМ

### ⛔ КАТЕГОРИЧЕСКИ НЕЛЬЗЯ отправлять в чат:

| Что | Почему |
|---|---|
| Полное содержимое `.env` | Содержит `BOT_TOKEN`, `WEBHOOK_TOKEN` |
| `BOT_TOKEN` целиком или фрагменты длиннее 6 символов | Telegram-бот моментально угоняется |
| `WEBHOOK_TOKEN` целиком | Доступ к кассовому API |
| Приватные SSH-ключи (без `.pub`) | Полный угон сервера/GitHub |
| GitHub Personal Access Token | Угон репозитория |
| Пароли, passphrase ключей | Очевидно |

### ✅ Что МОЖНО:

- `ADMIN_ID` (5899721537), `ADMIN_USERNAME` (@utc2000) — публично
- ID бота (часть до `:` в `BOT_TOKEN`), его `@username`
- Структура `.env`: имена переменных, длины значений, статус ✓/✗
- SQL-схемы без живых данных пользователей
- Логи **после** фильтрации: `journalctl ... | grep -vE "TOKEN|KEY|SECRET"`
- Публичные ключи SSH (`*.pub` файлы)

### 🛡 Если случайно отправил токен:

1. Немедленно отозвать `BOT_TOKEN` в BotFather: `/revoke`
2. Сгенерировать новый `WEBHOOK_TOKEN`: `openssl rand -hex 16`
3. Обновить `.env`, рестарт: `sudo systemctl restart smoktolk-bot`
4. Записать инцидент в раздел 23

---

## 1. Изменения в v1.2 относительно v1.1

- ➕ Раздел 0 — правила безопасности при работе с AI-ассистентом
- ➕ Раздел 21 — GitHub: репозиторий, SSH deploy key, CI/CD
- ➕ Раздел 22 — Termius (рабочий клиент SSH на macOS)
- ➕ Раздел 23 — История инцидентов
- ➕ Раздел 24 — Правила взаимодействия с AI-ассистентом
- 🔄 Раздел 19 — обновлено текущее состояние на 2026-05-10
- 🔄 Раздел 20 — добавлены 2FA, branch protection, Termius Pro, мониторинг
- 🔄 Раздел 14 — `.env` теперь явно ссылается на `.env.example`

---

## 2. Назначение

Telegram-бот программы лояльности офлайн-магазина SMOKTOLK. Начисляет
кэшбэк по чекам с кассы, ведёт многоуровневую систему рангов, выдаёт
подарки за 1₽, считает рефералов. Дистанционной продажи нет.

## 3. Стек (зафиксированные версии)

- **Python 3.11.2** (системный, Debian 12)
- **aiogram 3.28.2** — API менялся между минорами, текущая версия зафиксирована; апгрейды только через Dependabot PR с ручным review
- aiohttp 3.10.10, aiosqlite 0.20.0, openpyxl 3.1.5
- qrcode 7.4.2, Pillow 10.4.0, pydantic 2.9.2, python-dotenv 1.0.1
- SQLite (`/opt/smoktolk/bot/data/smoktolk.db`)
- systemd + cron-бэкап (см. раздел 15)

Полный список — `requirements.txt`. Venv: `/opt/smoktolk/bot/venv/`.

## 4. Архитектура

Один процесс, запускается systemd:
- aiogram **polling** (long-poll к Telegram API)
- aiohttp **web-server** на 127.0.0.1:8080 (вебхуки от кассы)
- фоновый `daily_loop` (рассылки, сгорания, отчёты)

Все три сосуществуют в одном event-loop, точка входа — `bot.py`.

## 5. Уровни лояльности (бизнес-логика — НЕ менять)

| L | Название | Кэшбэк | Условия | Окно повтора | Подарок 1₽ |
|---|----------|--------|---------|--------------|------------|
| 1 | Исследователь | 10% | по умолчанию | 3–5 дн., +3% | — |
| 2 | Знаток | 11% | возврат подтверждён | 3–8 дн., +5% | — |
| 3 | Мастер пара | 12% | возраст + (1500 lp ИЛИ 15 чеков ≥500₽) | 3–12 дн., +7% | 60 дн. |
| 4 | Профи | 13% | возраст + (4000 lp ИЛИ 40 чеков) | 3–15 дн., +10% | 30 дн. + 15% на аксессуары |
| 5 | Легенда | 15% | возраст + (8000 lp ИЛИ 80 чеков) | 3–15 дн., +12% | 30 дн. + бесплатная доставка |

## 6. Бонусы и сгорания

- **Repeat-bonus**: если 3 ≤ дни_от_последней_покупки ≤ окно_уровня → +X%
- **Birthday**: +20 п.п. в день рождения
- **Сгорание**: 120 дней без покупок → обнуление баллов (через `daily_loop`)

## 7. Списание баллов

- 10 баллов = 1 ₽, минимум 200 баллов, максимум 30% чека
- Только категории: `accessories, tools, cables, sweets`
- Через QR-токен (UUID), TTL 15 мин

## 8. Подарки за 1₽

- Список из Excel (лист `gifts`)
- Доступны от уровня + cooldown по уровню
- QR-токен + 6-значный резервный код

## 9. Реферальная программа

- Ссылка: `t.me/SMOKTOLK_bot?start=ref_<6chars>`
- Награда (300/200 баллов) после: регистрация → возраст → первая покупка ≥500₽

## 10. Webhook от кассы

- Прослушка: 127.0.0.1:8080
- Эндпоинты: `POST /webhook/purchase`, `/webhook/redeem`, `/webhook/redeem_gift`
- Заголовок: `X-API-Token: <WEBHOOK_TOKEN>` (в `.env`)
- Режим: `WEBHOOK_MODE=stub` (текущий) | `live`
- Реализация: `webhook.py`

## 11. Ассортимент

- Excel на Я.Диске: `https://disk.yandex.ru/i/jlz-VbSdVaUbTQ`
- Листы: `products`, `gifts`
- Кэш: `data/catalog.xlsx`, обновление раз в час или кнопкой админа
- Парсер: `catalog.py`. Заголовок на 2-й строке, cols: num=1, name=11, price=56, stock=53, rec=70
- Факт: **143 товара**

## 12. Админ-панель (только ID 5899721537)

- 📊 Статистика
- 👥 Пользователи
- ✅ Заявки на верификацию (18+)
- 🎁 Подарки
- 📡 Рассылка
- 📤 Экспорт в CSV (добавлен 2026-05-09)
- 🔄 Обновить каталог
- 🧪 Тест webhook (для отладки stub)

## 13. Верификация 18+

- Юзер жмёт «Подтвердить возраст», бот отправляет заявку админу
- Заявка хранится в `verification_requests`
- Админ нажимает «Подтвердить» / «Отклонить» в чате
- При подтверждении: `users.age_verified=1`, `age_verified_at=now`, `age_verified_by=admin_id`
- Поле `gosuslugi_verified` зарезервировано на будущее (интеграция через ЕСИА)

## 14. Конфигурация `.env`

**Шаблон с плейсхолдерами:** `.env.example` (в git, безопасно)
**Боевой файл:** `.env` (НЕ в git, права 600, владелец `smoktolk`)

Структура (значения — заглушки):

```
BOT_TOKEN=<получить у @BotFather>
ADMIN_ID=5899721537
WEBHOOK_TOKEN=<openssl rand -hex 16>
WEBHOOK_MODE=stub
DB_PATH=/opt/smoktolk/bot/data/smoktolk.db
CATALOG_URL=https://disk.yandex.ru/i/jlz-VbSdVaUbTQ
LOG_LEVEL=INFO
```

⚠️ Никогда не коммитить `.env` — проверка через gitleaks (см. раздел 21.4)
⚠️ Никогда не отправлять `.env` ассистенту (см. раздел 0)

## 15. Бэкапы (cron)

Активная задача — crontab пользователя `smoktolk`:

```
0 4 * * * /opt/smoktolk/bot/backup.sh >> /opt/smoktolk/bot/logs/backup.log 2>&1
```

Скрипт `/opt/smoktolk/bot/backup.sh`:
- `sqlite3 .backup` (безопасно при работающем боте) → `backups/smoktolk_YYYYMMDD_HHMMSS.db`
- `cp catalog.xlsx` → `backups/catalog_YYYYMMDD_HHMMSS.xlsx`
- Хранит последние 30 копий каждого, старое удаляет

История: ранее существовала битая cron-задача под `shushpanchik_art`
(`/home/shushpanchik_art/smoktolk_bot/backup.sh` — путь не существовал).
Удалена 2026-05-09.

Ручные tar-бэкапы перед изменениями: `/opt/smoktolk/backup_YYYYMMDD_HHMM.tar.gz`

## 16. Файлы проекта

```
bot.py, config.py, db.py, keyboards.py, utils.py, catalog.py,
webhook.py, tasks.py
handlers/{start,profile,gifts,catalog,referral,rules,verify,admin}.py
scripts/setup-hooks.sh
scripts/git-hooks/pre-commit
.github/dependabot.yml
.env.example, .gitignore, requirements.txt
SPEC.md, README.md
```

## 17. Запуск / диагностика

- Основной лог приложения: `/opt/smoktolk/bot/logs/bot.log` (RotatingFileHandler, см. `bot.py:setup_logging()`)
- Свежие записи логгера бота: `tail -f /opt/smoktolk/bot/logs/bot.log`

```
sudo systemctl status smoktolk-bot
sudo systemctl restart smoktolk-bot
sudo journalctl -u smoktolk-bot -f
sudo tail -f /opt/smoktolk/bot/logs/bot.log
sudo tail -f /opt/smoktolk/bot/logs/backup.log
```

### 17.1 Проверка синтаксиса Python-файлов

- `python3 -m py_compile <file>` НЕ работает из-под `shushpanchik_art`, потому что `__pycache__/` принадлежит сервисному пользователю `smoktolk` (бот пишет туда `.pyc` при запуске)
- Признак проблемы: `[Errno 13] Permission denied: '__pycache__/*.pyc.<random>'`
- Правильный способ — парсинг AST без записи на диск:

      python3 -c "import ast; ast.parse(open('handlers/profile.py').read()); print('OK')"

- Альтернатива: запустить от имени `smoktolk` через `sudo -u smoktolk python3 -m py_compile <file>`
- Главный критерий что код синтаксически валиден — бот успешно стартует и пишет в `logs/bot.log` строку `Bot started: @SMOKTOLK_bot`

### 17.2 Работа с БД SQLite — корректный путь

- Путь к БД: `/opt/smoktolk/bot/data/smoktolk.db` (НЕ `bot.db` — частая ошибка)
- Список таблиц: `sqlite3 /opt/smoktolk/bot/data/smoktolk.db ".tables"`
- Схема: `sqlite3 /opt/smoktolk/bot/data/smoktolk.db ".schema"`
- Read-only режим (безопасно при работающем боте): добавить флаг `-readonly`
- Форматированный вывод: флаги `-header -column`
- Признак ошибки в пути: `Error: in prepare, no such table: <name>` — обычно значит, что обратились к несуществующему файлу БД (sqlite создаёт пустой)

### 17.3 Где искать что — быстрая шпаргалка

- Стартует ли процесс — `systemctl status smoktolk-bot`
- Перезапуски, OOM, события systemd — `journalctl -u smoktolk-bot -n 50`
- Ошибки бизнес-логики, Traceback приложения — `tail -100 /opt/smoktolk/bot/logs/bot.log`
- Данные пользователей, баллы, redemptions — `sqlite3 -readonly /opt/smoktolk/bot/data/smoktolk.db ...`
- Конфигурация — `/opt/smoktolk/bot/.env` (НЕ коммитить!)
- Бэкапы БД — `/opt/smoktolk/bot/backups/` + лог в `logs/backup.log`
- Логи бота принадлежат пользователю `smoktolk`, читаются всеми (`-rw-rw-r--`); для `tail -f` sudo не нужен

### 17.4 Инструменты контроля качества и безопасности кода

В проекте используется набор инструментов для регулярной проверки качества и безопасности. Запускаются вручную из корня репозитория, все установлены в `venv`.

#### Линтер: ruff

Стиль, неиспользуемые импорты, f-string без placeholder, неоднозначные имена переменных.

venv/bin/ruff check . --exclude venv --exclude data --exclude backups --exclude logs --statistics
venv/bin/ruff check . --exclude venv --exclude data --exclude backups --exclude logs --output-format=concise
venv/bin/ruff check . --fix --exclude venv --exclude data --exclude backups --exclude logs   # автофикс

#### Security-сканер кода: bandit

Hardcoded secrets, SQL-инъекции, eval/exec, shell=True. Сканируем только проектный код (без venv и тестов):
venv/bin/bandit -r . -x venv,data,backups,logs,scripts,pycache -ll

Для подробного отчёта:
venv/bin/bandit -r bot.py catalog.py config.py db.py keyboards.py tasks.py utils.py webhook.py handlers/ -ll

#### Уязвимости в зависимостях: pip-audit

Проверка `requirements.txt`:
venv/bin/pip-audit -r requirements.txt

Проверка фактически установленных пакетов в venv:
venv/bin/pip-audit

#### Мёртвый код: vulture

venv/bin/vulture . --exclude venv,data,backups,logs --min-confidence 80

#### Цикломатическая сложность: radon

Функции категории C+ (CC > 10) — кандидаты на рефакторинг:
venv/bin/radon cc . -nc -e "venv/,data/,backups/,logs/"
venv/bin/radon mi . -nb -e "venv/,data/,backups/,logs/"

#### Dependabot (GitHub)

- Алёрты безопасности: <https://github.com/shushpanchik-art/smoktolk-bot/security/dependabot>
- Pull requests с обновлениями: <https://github.com/shushpanchik-art/smoktolk-bot/pulls?q=author%3Aapp%2Fdependabot>
- CLI-проверка:

gh pr list --repo shushpanchik-art/smoktolk-bot --state open --author "app/dependabot"
gh api repos/shushpanchik-art/smoktolk-bot/dependabot/alerts --jq '.[] | {number, state, severity: .security_advisory.severity, package: .dependency.package.name, summary: .security_advisory.summary}'

#### Pre-commit hook: gitleaks

Запускается автоматически при `git commit`, блокирует коммит с секретами. Установка для новых разработчиков:
scripts/setup-hooks.sh

### 17.5 Регламент регулярных проверок

| Периодичность | Что проверяем | Команды |
|---|---|---|
| **Перед каждым PR** | ruff (без новых ошибок), bandit (без новых medium+) | `venv/bin/ruff check ...`, `venv/bin/bandit -r ...` |
| **Еженедельно** | Dependabot PR — обработать или закрыть | `gh pr list --author "app/dependabot"` |
| **Еженедельно** | Dependabot alerts — все должны быть `fixed` или с обоснованием | команда `gh api .../dependabot/alerts` выше |
| **Ежемесячно** | pip-audit на venv (системные пакеты вроде setuptools) | `venv/bin/pip-audit` |
| **Ежемесячно** | Полный audit-прогон всех инструментов + запись результатов в CHANGELOG | все команды из 17.4 |
| **При появлении CVE high+** | Внеплановое обновление, отдельный PR | через Dependabot или вручную |

### 17.6. Audit follow-up (исправления 2026-05-11)

После аудита 2026-05-11 (см. CHANGELOG / Audit) исправлены все находки:

- **Ruff (10 → 0):** удалены неиспользуемые импорты (`io`, `shutil`, `tempfile`, `InlineKeyboardButton`, `time` из `datetime`); переменные `l` в `handlers/profile.py` переименованы в `lvl` (E741); убран лишний префикс `f` у строки без placeholders (F541); неиспользуемая локальная переменная `backup` в `webhook.py` заменена на закомментированный TODO-фрагмент (F841)
- **Bandit medium (1 → 0):** `db.py:601` — добавлен `# nosec B608` с пояснением, что `field` проверяется по whitelist `allowed` строкой выше; параметры подставляются через `?`, SQL-инъекция невозможна
- **Smoke-тест:** все модули проекта импортируются без ошибок (`python -c "import bot, db, catalog, webhook, tasks, keyboards, config; from handlers import profile"`)

После этих правок CI-чеки `Ruff lint` и `Bandit security scan` стали зелёными без `continue-on-error`. Включение строгого режима (удаление `continue-on-error`) запланировано отдельным PR.

#### Целевые показатели

- **ruff**: 0 ошибок в проектном коде (исключения — через `# noqa: <code>` с комментарием)
- **bandit**: 0 medium+ в проектном коде (исключения — через `# nosec <code>` с обоснованием)
- **pip-audit (requirements.txt)**: 0 уязвимостей
- **pip-audit (venv)**: допустимы CVE в системных пакетах (setuptools, pip) — не блокирующее
- **radon CC**: не больше 1-2 функций категории D, ни одной E (рефакторить по мере накопления)
- **Dependabot alerts**: 0 в состоянии `open` со степенью `high`/`critical`

## 18. Схема БД (актуальная, проверена 2026-05-09)

**Таблицы (8):** users, purchases, redemptions, gifts_log,
gift_cooldowns, history, verification_requests, daily_stats

### users (главная таблица)

```sql
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    phone TEXT,
    birthday TEXT,
    age_verified INTEGER DEFAULT 0,
    age_verified_at TEXT,
    age_verified_by INTEGER,
    gosuslugi_verified INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    points INTEGER DEFAULT 0,
    lifetime_points INTEGER DEFAULT 0,
    total_spent INTEGER DEFAULT 0,
    purchases_count INTEGER DEFAULT 0,
    purchases_count_500 INTEGER DEFAULT 0,
    last_purchase_date TEXT,
    last_activity TEXT,
    referral_code TEXT UNIQUE,
    referrer_id INTEGER,
    referral_reward_paid INTEGER DEFAULT 0,
    rules_accepted_at TEXT,
    notifications_enabled INTEGER DEFAULT 1,
    created_at TEXT
);
```

### Прочие таблицы

- `purchases` — все чеки с кассы (приход через webhook)
- `redemptions` — все списания баллов (выпуск QR + факт списания)
- `gifts_log` — выданные подарки за 1₽
- `gift_cooldowns` — таймеры кулдауна по уровням
- `history` — лента событий пользователя для профиля
- `verification_requests` — заявки 18+ в очереди к админу
- `daily_stats` — агрегаты для админ-статистики

Полные DDL — см. `db.py` или `sqlite3 smoktolk.db ".schema"`.

## 19. Текущее состояние (2026-05-10)

- ✅ Сервис: запущен, polling активен
- ✅ `ADMIN_ID`: исправлен с `1492067664` на `5899721537` (см. инцидент 23.1)
- ✅ Пользователей в БД: 4 (тестовые + админ)
- ✅ Каталог: 143 товара, кэш на диске
- 🟡 Webhook: режим **stub** (контракт API готов, к live кассе не подключён)
- ✅ Бэкапы: работают, последний `smoktolk_20260510_040002.db`
- ✅ GitHub: репо создан, код залит, Dependabot активен (1 PR смержен — #1)
- ✅ Pre-commit hook с gitleaks 8.21.2 установлен
- ✅ SSH к GitHub: проверен, deploy key работает

## 20. Технический долг

### 🔴 Высокий приоритет

- **Включить 2FA на GitHub** (`shushpanchik-art`) — сейчас выключен,
  единственная защита репо = пароль
- **Включить 2FA в Termius** — сейчас выключен, аккаунт
  `shushpanchik.art@gmail.com` защищён только паролем; при компрометации
  Termius-аккаунта = доступ ко всем сохранённым SSH-ключам через Sync
- **Branch protection для `main`** в GitHub — запретить force-push,
  требовать PR-review (хоть и self-review)

### 🟡 Средний приоритет

- **Termius Trial истекает через 14 дней** (с 2026-05-10) — решить:
  оплатить Pro / перейти на бесплатный (потеря Snippets, Sync, истории)
- Подключить webhook кассы в live (после согласования API с интегратором)
- Мониторинг: алерт в Telegram при падении сервиса (`OnFailure=` в systemd unit)
- Покрыть тестами `tasks.daily_loop` (сгорание, рассылки, отчёты)
- Создать Snippets в Termius для частых задач (рестарт, логи, статус, бэкап)

### 🟢 Низкий приоритет

- Реализовать `gosuslugi_verified` через ЕСИА
- Уточнить единицы измерения `total_spent` (₽ vs копейки) — задокументировать
- GitHub Actions: запускать тесты при push (CI)

---

## 21. GitHub — репозиторий, ключи, CI

### 21.1 Репозиторий

| Параметр | Значение |
|---|---|
| URL | `git@github.com:shushpanchik-art/smoktolk-bot.git` |
| HTTPS | `https://github.com/shushpanchik-art/smoktolk-bot` |
| Видимость | private |
| Владелец | `shushpanchik-art` (User ID 283429830) |
| Активная ветка | `main` |
| Email коммитера | `283429830+shushpanchik-art@users.noreply.github.com` |
| Contributors | 1 |
| Языки | Python 97.1%, Shell 2.9% |

### 21.2 Аутентификация (SSH deploy key)

- Приватный ключ: `/home/smoktolk/.ssh/github_deploy` (ed25519, права 600)
- Публичный: `/home/smoktolk/.ssh/github_deploy.pub`
- Содержимое публичной части (безопасно): `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDOlMCYtrZNhzYFt1mDT0zSU6JIeRx74rzRIUeuhiyEA github-shushpanchik-art@telegram-bot`
- Добавлен в GitHub: Settings → SSH and GPG keys (как user SSH key)
- Проверка работы: `sudo -u smoktolk ssh -T git@github.com` → `Hi shushpanchik-art!`

### 21.3 Включённые механизмы безопасности

- `.gitignore` — исключает `.env`, `backups/`, `*.db`, `logs/`, `.venv/`, `venv/`
- `.github/dependabot.yml` — еженедельная проверка зависимостей Python
- `scripts/git-hooks/pre-commit` — запускает gitleaks перед коммитом
- `scripts/setup-hooks.sh` — установщик git-hooks для новых разработчиков

### 21.4 Защита от утечек

- gitleaks 8.21.2 в `/usr/local/bin/gitleaks`
- Pre-commit hook: `.git/hooks/pre-commit` → симлинк на `scripts/git-hooks/pre-commit`
- При попытке закоммитить файл с токеном — commit блокируется

### 21.5 История Dependabot PR

- PR #1 — групповое обновление зависимостей — смержен 2026-05-10
- Открытых PR: проверять через `https://github.com/shushpanchik-art/smoktolk-bot/pulls`

---

### 21.6 GitHub CLI (gh) — стандарт для работы с PR

- Все PR создаются, просматриваются и мержатся через `gh` CLI (а не через веб-интерфейс GitHub)
- Установка: `sudo apt install gh`; авторизация: `gh auth login` (token хранится в `~/.config/gh/`)
- Базовые команды проекта (`OWNER/REPO` = `shushpanchik-art/smoktolk-bot`):
  - Создать PR: `gh pr create --repo OWNER/REPO --base main --head <branch> --title "..." --body-file /tmp/pr-body.md`
  - Тело PR — **только через `--body-file`**, не через `--body "..."` и не через heredoc (правило 24.2: запрет inline markdown с бэктиками)
  - Просмотр PR: `gh pr view N --repo OWNER/REPO --json number,title,state,mergeable,mergeStateStatus,headRefName,baseRefName,url | python3 -m json.tool`
  - **Не использовать** `gh pr view N` без `--json` до обновления `gh` CLI — падает на устаревшем поле `projectCards` (см. инцидент 23.6)
  - Мерж: `gh pr merge N --repo OWNER/REPO --merge --delete-branch` (или `--squash` для squash-мержа)
  - Список открытых PR: `gh pr list --repo OWNER/REPO --state open`
- Проверка готовности к мержу: `mergeable: MERGEABLE` + `mergeStateStatus: CLEAN` = готов
- Если `mergeable: UNKNOWN` — подождать 5–10 секунд (GitHub пересчитывает статус) и проверить повторно
- Если `mergeable: CONFLICTING` — нужен rebase ветки PR поверх свежего `main`

---

## 22. Termius — рабочий клиент SSH

### 22.1 Аккаунт и устройство

| Параметр | Значение |
|---|---|
| Платформа | macOS 26.3 (25D125), десктоп |
| Аккаунт | `shushpanchik.art@gmail.com` (Verified) |
| Тариф | Trial, 14 days left (с 2026-05-10 — истекает ~24.05.2026) |
| 2FA в Termius | выключен (см. техдолг 20) |
| Sync keys and identities | включён |
| Последняя синхронизация | 2026-05-10, 18:49 |

### 22.2 Подключение к серверу

- Хост: `telegram-bot` (Google Cloud Compute Engine)
- Пользователь: `shushpanchik_art`
- Порт: 22 (дефолт)
- Аутентификация: SSH-ключ (пароль на сервере запрещён)
- Конфиг сервера: `PasswordAuthentication no`, `PermitRootLogin no`

### 22.3 Vaults и Snippets

- Vault для проекта: `smoktolk-bot` (отдельный, не дефолтный `Vaults`)
- Snippets: пусто (нужно создать — см. техдолг 20)

### 22.4 Как проверить настройки Termius (для будущих ревизий)

- Sync статус: Termius → ⌘, → Account → блок Sync
- 2FA статус: Termius → ⌘, → Account → toggle Enable 2FA
- Snippets: левая панель → иконка `{ }`
- Тариф: Termius → ⌘, → Pro / Subscription

---


## 23. История инцидентов

### 23.1 Неверный ADMIN_ID (2026-05-08)

- **Симптом:** Админ-панель не открывалась у @utc2000
- **Причина:** В `.env` был `ADMIN_ID=1492067664` (Telegram ID другого аккаунта)
- **Исправление:** `ADMIN_ID=5899721537`, рестарт сервиса
- **Урок:** При смене админа — обновить и `.env`, и `SPEC.md`, и проверить `/start` от имени админа

### 23.2 Битая cron-задача (2026-05-09)

- **Симптом:** В crontab пользователя `shushpanchik_art` была запись на путь `/home/shushpanchik_art/smoktolk_bot/backup.sh`, который не существовал
- **Причина:** Старая запись с этапа разработки до миграции в `/opt/smoktolk/bot/`
- **Исправление:** Удалена через `crontab -e`. Рабочая задача в crontab пользователя `smoktolk` сохранена
- **Урок:** При миграции путей — проверять `crontab -l` у ВСЕХ пользователей

### 23.3 Утечка `.env` в чат AI (2026-05-10)

- **Симптом:** Полный `.env` (включая `BOT_TOKEN` и `WEBHOOK_TOKEN`) был отправлен ассистенту для диагностики
- **Причина:** Не было правил безопасности взаимодействия с AI
- **Исправление:**
  - Немедленно отозван `BOT_TOKEN` через BotFather → `/revoke`
  - Сгенерирован новый `WEBHOOK_TOKEN` через `openssl rand -hex 16`
  - Обновлён `.env`, рестарт сервиса
  - Создан `.env.example` с плейсхолдерами
  - Введены правила раздела 0 и раздела 24
- **Урок:** Никогда не вставлять секреты в чат — даже частично. Структуру/маски — можно, значения — никогда

### 23.4 Heredoc-команды с markdown ломали рендер чата (2026-05-10)

- **Симптом:** Длинные `tee <<EOF` с вложенными тройными бэктиками отображались в чате как обычный текст, нельзя было скопировать одним блоком
- **Причина:** Парсер markdown в чате путает вложенные ` ``` ` внутри bash-команды с концом code-блока
- **Исправление:**
  - Разбивка команд на части по ~50 строк
  - Внутри SPEC.md тройные бэктики заменяются на `~~~` (валидная альтернатива в markdown)
  - Введено правило в раздел 24
- **Урок:** Команды для копипасты — короткие, без вложенной markdown-разметки внутри heredoc

### 23.5 Рецидив heredoc-инцидента (2026-05-10, вечер)

- **Симптом:** При создании `CHANGELOG.md` и `README.md` ассистент снова использовал команды с вложенными тройными бэктиками внутри `tee`/heredoc — рендер в Telegram сломался дважды за одну сессию
- **Причина:** Правило 24.2 существовало, инцидент 23.4 был записан, но ассистент не перечитал раздел 24 перед генерацией команд
- **Исправление:**
  - В раздел 24.4 добавлено правило «мысленно перечитать 24.2 перед записью в файл»
  - В раздел 24.4 добавлено правило «ls -la перед созданием файла»
  - В раздел 24.4 добавлено правило «stop on first anomaly»
- **Урок:** Существование правила в SPEC ≠ его применение. Ассистент обязан явно ссылаться на номер правила перед командой записи

### 23.6 gh pr view падает на устаревшем GraphQL-поле projectCards (2026-05-11)

- **Симптом:** `gh pr view 9 --repo shushpanchik-art/smoktolk-bot` падает с ошибкой "GraphQL: Projects (classic) is being deprecated ... (repository.pullRequest.projectCards)" и не показывает PR
- **Причина:** Установленная версия `gh` CLI запрашивает удалённое поле `projectCards` через GraphQL. GitHub его отключил после 2024-05-23 в рамках sunset Projects (classic)
- **Исправление (workaround):** использовать `--json` запрос только нужных полей, минуя сломанный `projectCards`: `gh pr view N --repo OWNER/REPO --json number,title,body,state,headRefName,baseRefName,mergeable,url | python3 -m json.tool`
- **Исправление (долгосрочное):** обновить `gh` CLI — `sudo apt update && sudo apt install --only-upgrade gh`
- **Урок:** Когда CLI падает на устаревшем поле API — почти всегда есть `--json <fields>` режим для обхода. Запасной вариант: открыть PR в браузере по URL

### 23.7 Рецидив heredoc-инцидента №2: создание LESSONS_LEARNED.md (2026-05-11)

- **Симптом:** Ассистент предложил создать отдельный файл `docs/LESSONS_LEARNED.md` через `cat >> ... << 'EOF'` с вложенным markdown (кодовые блоки, ссылки, бэктики). Heredoc застрял на промпте `>`, файл не записался, ошибка `No such file or directory` (папки `docs/` не существовало)
- **Причина:** Двойная ошибка ассистента:
  1. Игнор правила: уроки ведутся в `SPEC.md` раздел 23, а не в отдельном `LESSONS_LEARNED.md`
  2. Игнор правила 24.2: heredoc с вложенным markdown — запрещён (инциденты 23.4 и 23.5)
- **Исправление:**
  - Папка `docs/` удалена (была создана пустой через `mkdir -p`)
  - Уроки записаны напрямую в `SPEC.md` раздел 23 через `nano` (без heredoc)
  - В раздел 24.4 добавлено правило «уроки и инциденты — только в SPEC.md раздел 23, никаких отдельных файлов»
- **Урок:** При появлении новой задачи (запись урока) — ассистент обязан проверить, КУДА именно ведётся подобная документация в проекте (через `find` или вопрос юзеру), а не создавать новый файл по своему усмотрению. Существование правила 24.2 + два предыдущих рецидива (23.4, 23.5) = третий рецидив = системная проблема внимания. Правило 24.4 «мысленно перечитать 24.2 перед записью в файл» нарушено в третий раз

### 23.8 Рецидив heredoc-инцидента №3: команды с python3 -c и cat << EOF (2026-05-11)

- **Симптом:** Ассистент в одном ответе выдал сразу две команды с heredoc и вложенным markdown/Python-кодом:
  1. `python3 << 'PYEOF' ... PYEOF` — для правки SPEC.md через скрипт
  2. `cat > /tmp/pr-diag-body.md << 'MDEOF' ... MDEOF` — для тела PR с markdown-блоками
- **Причина:** Несмотря на ранее зафиксированные инциденты 23.7 и предыдущие, ассистент при генерации многошаговых блоков «забыл» свериться с правилом 24.2 SPEC.md. Heredoc казался «удобным сокращением» по сравнению с пошаговой работой в nano.
- **Что сработало:** Юзер заметил нарушение по скриншоту и остановил выполнение до запуска команд. Реального ущерба нет, но риск повторения паттерна высокий.
- **Исправление (немедленное):** Переход на работу через nano с ручной вставкой блоков (Ctrl+Shift+V). Тело PR — через `nano /tmp/pr-body.md`, затем `gh pr create --body-file`.
- **Исправление (системное):** Правило 24.2 действует БЕЗ исключений, в том числе для:
  - `python3 << EOF` со скриптами правки файлов
  - `cat > файл << EOF` с любым markdown/кодом внутри
  - `bash << EOF` с многострочными командами
  - Любых других heredoc-конструкций с непустым содержимым сложнее одной строки
- **Урок:** Heredoc допустим ТОЛЬКО для односложного содержимого без бэктиков, без markdown, без вложенных кавычек — например, простой текстовый input в pipe. Для всего остального — nano или отдельный файл, созданный заранее.
- **Урок для ассистента:** Перед выдачей блока команд — мысленно прочитать каждую строку и найти `<<`. Если найден — переписать через nano. Это правило важнее «компактности» ответа.

---

## 24. Правила взаимодействия с AI-ассистентом

### 24.1 Что ассистент НЕ ДОЛЖЕН делать

- Запрашивать значения `BOT_TOKEN`, `WEBHOOK_TOKEN`, пароли, приватные SSH-ключи
- Запрашивать полное содержимое `.env`
- Запрашивать «полный лог» без фильтрации — только после `grep -vE "TOKEN|KEY|SECRET"`
- Генерировать команды, которые автоматически отправят секрет в третий сервис (curl на чужой хост и т.п.)

### 24.2 Формат выдачи команд ассистентом

- **Одна команда — один code-блок.** Не склеивать 5 команд в один блок без необходимости
- **Длина блока ≤ 50 строк.** Длиннее — разбивать на части
- **Не использовать heredoc (`<<EOF`) с вложенной markdown-разметкой** (тройные бэктики, таблицы со сложным форматированием). Альтернатива: тильды `~~~` или base64
- **После каждой записи в файл — verify-шаг** (`wc -l`, `tail`, `diff`, `grep`)
- **Деструктивные команды (`rm`, `DROP`, `force-push`) — с предупреждением** и предварительным бекапом
- **Команды для копипасты — без интерактивных промптов** (если нужен ввод — заранее предупредить юзера)

### 24.3 Формат данных, которые юзер присылает ассистенту

- ✅ Скриншоты UI (Termius, GitHub, BotFather) — но **закрашивать токены и приватные данные**
- ✅ Вывод команд после фильтрации секретов
- ✅ Имена переменных, длины значений, статус наличия (✓/✗)
- ✅ Структура файлов, схемы БД (DDL без живых данных)
- ✅ Публичные ключи `*.pub`
- ❌ Полные `.env`, приватные ключи, пароли — никогда

### 24.4 Что ассистент ДОЛЖЕН делать

- Перед изменением файла — предложить бекап (`cp file file.bak.$(date +%s)`)
- Объяснять КАЖДУЮ команду перед выдачей (1–2 строки)
- При непонимании контекста — задавать уточняющие вопросы, а не угадывать
- При обнаружении инцидента (утечка, ошибка конфига) — записывать в раздел 23 SPEC.md
- Помнить о версии стека (Python 3.11, aiogram 3.28.2) и не предлагать решения с других версий
- При работе с GitHub — всегда через SSH (`git@`), не HTTPS
- Перед созданием любого файла — `ls -la <path>` для проверки, не существует ли он. Если существует — бекап перед перезаписью
- При первом несоответствии вывода ожидаемому — остановиться и диагностировать, не продолжать «по инерции»
- Перед каждой командой записи в файл — мысленно перечитать раздел 24.2 (правила про heredoc и markdown)
- Уроки, инциденты, технические заметки — записываются ТОЛЬКО в SPEC.md (раздел 23 для инцидентов, раздел 20 для техдолга). Не создавать отдельные файлы `LESSONS_LEARNED.md`, `INCIDENTS.md`, `NOTES.md` и т.п.
- При предложении создать любой новый markdown-файл в проекте — сначала задать вопрос юзеру: «Куда обычно ведётся эта документация?» или выполнить `find . -iname "*.md"` для проверки существующих

### 24.5 Чек-лист перед каждой сессией с ассистентом

- [ ] `.env` не открыт в соседнем окне (риск случайно вставить)
- [ ] Бекап SPEC.md/README.md свежий (если планируются правки)
- [ ] Сервис в рабочем состоянии: `systemctl status smoktolk-bot`
- [ ] Свободное место на диске: `df -h /opt`

