# AI Onboarding Guide — SMOKTOLK Bot

> **Назначение:** этот файл — единый источник «вводной» для нового AI-ассистента, открывающего проект с нуля.
> Скопируй блок ниже целиком в первое сообщение новому ассистенту.
>
> **Когда обновлять:** при любом значимом изменении стека, ветки `main` HEAD, бизнес-логики, hardening-статуса или roadmap.
> Источник правды по бизнес-логике остаётся `SPEC.md`; этот файл — навигационная карта.

---

# 🎯 Проект: SMOKTOLK Bot

Telegram-бот лояльности для табачного магазина (Москва, Волгоградский пр-т 10с2). Хост: облачный VPS, Debian 12, одиночный systemd-сервис.

**URL репозитория:** `git@github.com:shushpanchik-art/smoktolk-bot.git` (приватный, владелец `shushpanchik-art`).

## 🏗 Стек и архитектура

| Слой | Технология |
|---|---|
| Язык | Python 3.11.2 |
| Bot framework | aiogram 3.28.2 (async) |
| HTTP | aiohttp 3.13.5 (для webhook от кассы) |
| БД | SQLite через aiosqlite 0.22.1 (`data/smoktolk.db`, ~68 KB) |
| TZ | Europe/Moscow, pytz 2026.2 |
| Доп. | openpyxl (Excel-отчёты), qrcode + Pillow (QR), python-dotenv |

**Архитектура:** монолит, одиночный процесс `smoktolk-bot.service` (long-polling Telegram + aiohttp webhook-listener на `127.0.0.1:8080`). Nginx (`/etc/nginx/sites-enabled/smoktolk-bot`) проксирует webhook извне. Нет worker/beat — фоновые задачи в `tasks.py` через asyncio.

## 📁 Структура (важное)

```
/opt/smoktolk/bot/                  # owner: smoktolk:smoktolk
├── bot.py (106)                    # entrypoint
├── config.py (136)                 # все ENV + бизнес-константы
├── db.py (759)                     # вся работа с БД, async, без ORM/alembic
├── webhook.py (260)                # aiohttp listener для POS-кассы
├── catalog.py (347)                # парсинг Excel-каталога с Я.Диска
├── tasks.py (71)                   # фоновые задачи
├── crash_alert.py (57)             # DOWN/RECOVERED алерты
├── handlers/                       # aiogram routers
├── services/admin_notify.py        # утилита алертов админу
├── keyboards.py, utils.py
├── tests/                          # 103 теста, pytest 9 + pytest-asyncio + pytest-cov
├── scripts/                        # backup_*.sh, deploy_systemd.sh, healthchecks
├── systemd/                        # 17 unit-файлов (бот + бэкапы + алерты + drop-in)
├── docs/                           # BACKUP.md, SECURITY.md, OPERATIONS.md, AI_ONBOARDING.md
├── SPEC.md (~106 KB)               # ИСТОЧНИК ПРАВДЫ
├── CHANGELOG.md (Keep a Changelog)
├── README.md, CONTRIBUTING.md
├── .env, .env.example
└── venv/
```

## 🔐 Бизнес-логика (из `config.py` и SPEC §5–9, не трогать без согласования)

- Уровни лояльности: см. `config.LEVELS` (SPEC §5).
- 10 баллов = 1 ₽, минимум списания — 200 баллов, максимум — 30% от чека.
- TTL баллов: 120 дней.
- Бонус ко дню рождения: +20 п.п. сверх базы.
- Подарки: за 1 ₽ (одна категория).
- Рефералка: +300 ₽ рефереру, +200 ₽ приглашённому, мин. покупка 500 ₽.
- Категории со списанием баллов: `accessories, tools, cables, sweets`.
- Никотиновые категории (списание запрещено): `liquid, device, tobacco, pods, disposable`.
- Админ: `ADMIN_ID=5899721537`, `ADMIN_USERNAME=utc2000`.

## 🚀 Деплой / эксплуатация

- **Сервис:** `smoktolk-bot.service` (active, enabled).
- **Runtime hardening:** `systemd-analyze security` = **1.3 OK** (PR #61). Включены NoNewPrivileges, ProtectSystem=strict, ProtectHome, PrivateTmp, ProtectKernel{Tunables,Modules,Logs}, ProtectControlGroups/Clock/Hostname/Proc=invisible, LockPersonality, PrivateDevices, CapabilityBoundingSet=(пусто), SystemCallFilter=@system-service + deny privileged/resources/debug, RestrictAddressFamilies/Namespaces/SUIDSGID/Realtime, SystemCallArchitectures=native, UMask=0027. **`MemoryDenyWriteExecute=yes` НЕ включён** — ломает Pillow/openpyxl/aiosqlite.
- **Деплой unit-файлов:** `sudo ./scripts/deploy_systemd.sh --dry-run` → `sudo ./scripts/deploy_systemd.sh --restart smoktolk-bot.service` (idempotent, auto-rollback).
- **Runbook:** `docs/OPERATIONS.md` — деплой/health/откаты. SPEC §17 — указатель на него.
- **Бэкапы:** 5 systemd-таймеров (backup, offsite, full-offsite, healthcheck ×2) на Я.Диск. SPEC §15 + `docs/BACKUP.md`.
- **Алерты:** через `OnFailure=` юнита `*-alert.service` (SPEC §25 + §15.7).
- **Логи:** `logs/{bot,backup,backup-offsite,backup-full-offsite}.log` + `journalctl -u smoktolk-bot`.
- **Пользователь:** runtime `smoktolk:smoktolk`, разработка через `shushpanchik_art`.

## 🤖 CI/CD (GitHub Actions, `.github/workflows/ci.yml`)

Все actions запинены к SHA (`docs/SECURITY.md`):

| Job | Что делает | Блокирует мердж? |
|---|---|---|
| `syntax` | `python -m py_compile` | ✅ |
| `lint` | `ruff check .` | ❌ (continue-on-error) |
| `security` | `bandit -ll` | ❌ |
| `deps` | `pip-audit` | ✅ |
| `tests` | `pytest --cov --cov-fail-under=10` + HTML/XML artifacts (14d) | ✅ |
| `sbom` | `cyclonedx-py` → SBOM artifact (CycloneDX JSON, 90d) | ❌ (после PR #63) |

**Coverage baseline:** 11.36%% (103 теста). Покрыты: `config.py` 97%%, `services/admin_notify.py` 91%%, `db.py` 43%%. Не покрыты (0%%): handlers/*, webhook.py, tasks.py, keyboards.py, utils.py, bot.py, catalog.py, crash_alert.py.

## 🛡 Локальные quality-gates

**Pre-commit** (`.git/hooks/pre-commit`, ставится через `./scripts/setup-hooks.sh`):
- `gitleaks` — блокирует коммит при находке секретов.
- `ruff check` на staged-файлах.

**Pre-push** — синтаксис + pytest + блокирует прямой push в `refs/heads/main`.

## 🔒 Безопасность: что реализовано / что отложено

| Контроль | Статус | Где описано |
|---|---|---|
| 2FA на GitHub | ✅ | manual |
| Dependabot (pip weekly, GH Actions monthly) | ✅ | `.github/dependabot.yml` |
| Actions pinned to SHA | ✅ | `.github/workflows/ci.yml` |
| `pip-audit` (блокирующий) | ✅ | CI `deps` |
| `bandit` (informational) | ✅ | CI `security` |
| `ruff` (informational) | ✅ | CI `lint` |
| Coverage gate `--cov-fail-under=10` | ✅ | CI `tests` (PR #60) |
| `gitleaks` в pre-commit | ✅ | `.git/hooks/pre-commit` |
| Pre-push защита `main` | ✅ (client-side) | `.git/hooks/pre-push` |
| CODEOWNERS | ✅ | `.github/CODEOWNERS` |
| Backup fsync durability | ✅ | PR #53 |
| systemd runtime hardening (1.3 OK) | ✅ | PR #61, `docs/SECURITY.md §4` |
| SBOM generation в CI (CycloneDX) | ✅ | PR #63 |
| **Branch Protection (server-side)** | ❌ accepted risk | GitHub Free private не поддерживает |
| **Signed commits (GPG/SSH)** | ❌ deferred 6 мес | overhead для соло-maintainer |
| **pre-commit-config.yaml framework** | ❌ skip | кастомные hooks работают |
| **MemoryDenyWriteExecute=yes** | ❌ deferred | ломает Pillow/openpyxl/aiosqlite |

## 📋 Конвенции работы

1. `SPEC.md` — единый источник правды. §20 — roadmap, §28 — DoD-чек-листы.
2. **Conventional Commits:** `feat(scope): …`, `fix(scope): …`, `chore(…): …`, `docs(…): …`.
3. **Workflow:** feature-branch → PR → CI green → squash-merge в `main`. Прямые пуши запрещены.
4. **PR-template:** `.github/pull_request_template.md` обязателен.
5. **CHANGELOG.md** обновляется в каждом PR, секция `[Unreleased]`, Keep a Changelog.
6. **Версии** в `requirements*.txt` — exact pin, Dependabot шлёт авто-PR.

## ⚠️ Правила взаимодействия (SPEC §0, §24)

- ⛔ Никогда не присылать в чат: содержимое `.env`, токены, ключи, gitleaks-отчёты с реальными значениями.
- ✅ Для разведки `.env` показывать только имена ключей через `grep` по шаблону `^[A-Z_]+=`.
- **Heredoc-инциденты (SPEC §23.4–23.8):** длинные markdown-команды через `cat <<EOF` ломают рендер в чате. Использовать Python-скрипт-файл или `printf` построчно. Команды не длиннее ~31000 токенов.
- Все команды — отдельными bash-блоками.
- Ответы — на русском.

## 🎯 Roadmap (SPEC §20)

### 🔴 High
- CI smoke-test полного цикла (xlsx + БД). После этого можно включить `MemoryDenyWriteExecute=yes`.
- Разделить webhook кассы в отдельный systemd-юнит.

### 🟡 Medium
- Рост покрытия `handlers/` (0%% → 30%%+). Каждый PR поднимает порог `--cov-fail-under` на 1–2 п.п.
- Codecov badge (вместо shields.io static).

### 🟢 Long-term
- П-1. Live-режим webhook от кассы (сейчас `WEBHOOK_MODE=stub`).
- П-2. Верификация возраста через ЕСИА.
- П-3. Прочее — см. SPEC §20.

## 🚦 Первые команды для нового ассистента

Перед любой работой попросить юзера выполнить:

```bash
cd /opt/smoktolk/bot
git checkout main && git pull --ff-only
git log --oneline -5
gh pr list --state open
systemctl is-active smoktolk-bot
systemd-analyze security smoktolk-bot.service 2>&1 | tail -3
source venv/bin/activate && pytest --cov --cov-config=.coveragerc 2>&1 | tail -5
```

Это даёт: актуальную ветку, открытые PR, статус бота, security score (должен быть **1.3 OK**) и текущее покрытие.
