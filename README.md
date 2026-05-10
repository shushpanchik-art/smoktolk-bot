# SMOKTOLK Bot

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

    python3 -m venv .venv
    source .venv/bin/activate
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

## Лицензия

Proprietary. Все права защищены.
