# SMOKTOLK Bot

![CI](https://github.com/shushpanchik-art/smoktolk-bot/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)
![Security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)


Telegram-бот для табачного магазина: каталог, заказы, доставка, админ-панель.

**Stack:** Python 3.11+ - aiogram 3 - SQLite/PostgreSQL - Docker

---

## Структура

    .
    ├── app/                    # Исходники бота
    ├── scripts/
    │   ├── git-hooks/          # Git-hooks для разработки
    │   └── setup-hooks.sh      # Установщик git-hooks
    ├── .github/
    │   └── dependabot.yml      # Авто-обновление зависимостей
    ├── requirements.txt
    └── README.md

---

## Setup для разработчика

После клонирования репозитория выполни **один раз**:

### 1. Установи gitleaks

Сканер секретов (используется в pre-commit hook):

    # Linux (Debian/Ubuntu)
    curl -sSfL https://github.com/gitleaks/gitleaks/releases/latest/download/gitleaks_8.21.2_linux_x64.tar.gz | tar -xz -C /tmp
    sudo mv /tmp/gitleaks /usr/local/bin/
    gitleaks version

    # macOS
    brew install gitleaks

### 2. Установи git-hooks

    ./scripts/setup-hooks.sh

После этого **каждый `git commit`** будет автоматически проверять staged-файлы на секреты (Telegram-токены, GitHub PAT, AWS keys и др.). Коммит с секретом будет заблокирован.

### 3. Зависимости и .env

    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt

    cp .env.example .env
    # затем отредактируй .env: подставь BOT_TOKEN и DATABASE_URL

### 4. Запуск

    python -m app.main

---

## Безопасность

- `.env` и `backups/` — в `.gitignore`, **никогда не попадают в репозиторий**
- **gitleaks** проверяет каждый коммит локально (pre-commit hook)
- **Dependabot** еженедельно проверяет зависимости на уязвимости
- Если pre-commit hook нашёл секрет — коммит отменяется

### Обход pre-commit hook (только в крайних случаях)

    git commit --no-verify -m "..."

⚠️ Используй **только** если 100% уверен, что это ложное срабатывание.

---

## Документация

- **[SPEC.md](SPEC.md)** — полная спецификация проекта, архитектура, инциденты и уроки
- **[CHANGELOG.md](CHANGELOG.md)** — история изменений по версиям

---

## Quality checks

Локальный прогон тех же проверок, что и в CI:

    # активируй venv
    source venv/bin/activate

    # линтер стиля и качества (ruff)
    ruff check .

    # security-сканер кода (bandit, medium+)
    bandit -r . -ll -x ./venv,./.venv,./tests

    # CVE в зависимостях
    pip-audit -r requirements.txt

В CI (GitHub Actions, `.github/workflows/ci.yml`) эти же проверки прогоняются автоматически на каждый `push` в `main` и на каждый `pull_request`. Статус виден в бейдже `CI` в шапке README и во вкладке **Actions** репозитория.

Подробности — в **SPEC.md §17.4-17.5** (инструменты и регламент) и **§21.7** (CI workflow).

---

## Лицензия

Proprietary. Все права защищены.
# test protection
