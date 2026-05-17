# SMOKTOLK Bot

![CI](https://github.com/shushpanchik-art/smoktolk-bot/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)
![Security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)
![Coverage](https://img.shields.io/badge/coverage-11%25-red.svg)


Telegram-бот для табачного магазина: каталог, заказы, доставка, админ-панель.

**Stack:** Python 3.11+ - aiogram 3 - SQLite/PostgreSQL - Docker

---

## Структура

    .
    ├── app/                    # Исходники бота
    ├── scripts/
    │   ├── git-hooks/          # Git-hooks для разработки
    │   └── setup-hooks.sh      # Установщик git-hooks
    ├── docs/
    │   ├── BACKUP.md           # Регламент бэкапов БД
    │   └── SECURITY.md         # Security posture, ADR по GitHub-тарифу
    ├── .github/
    │   ├── CODEOWNERS          # Code owners для PR-ревью
    │   ├── ISSUE_TEMPLATE/     # Шаблоны issues (bug, feature, config)
    │   ├── dependabot.yml      # Авто-обновление зависимостей
    │   ├── pull_request_template.md  # Шаблон PR
    │   └── workflows/          # CI/CD GitHub Actions
    ├── requirements.txt
    ├── README.md
    └── CONTRIBUTING.md     # Гайд для контрибьюторов

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
- **ruff** линтит staged Python-файлы локально на каждый commit (pre-commit hook); тот же ruff 0.15.12 гоняется в CI на PR
- **pre-push hook** блокирует прямой `git push` в ветку `main` (см. подраздел «Защита ветки `main`» ниже)
- **Dependabot** еженедельно проверяет зависимости на уязвимости
- **Бэкапы БД**: ежедневно в 04:00 MSK через `smoktolk-backup.timer` (systemd) от user `smoktolk` (`/var/backups/smoktolk/`), hash-дедупликация, retention 150 дней / 5 GiB, lock через `flock`, Telegram-алерты при сбое. См. `docs/BACKUP.md` и SPEC §15
- Если pre-commit hook нашёл секрет — коммит отменяется

### Документ-источник по security-решениям

Все архитектурные решения по защите репозитория, принятые риски, триггеры пересмотра и состав локальных hooks зафиксированы в **[`docs/SECURITY.md`](docs/SECURITY.md)** — это канонический документ. Изменения в подходе вносятся туда, README и SPEC ссылаются на него.

### Защита ветки `main`

Ветка `main` защищена **только локально** — через git pre-push hook (`scripts/git-hooks/pre-push`), который блокирует прямой `git push` в `main` ещё до отправки на GitHub. Устанавливается через `./scripts/setup-hooks.sh` (см. раздел Setup выше).

**Server-side branch protection не используется**: GitHub Branch Protection Rules недоступны на текущем тарифе (free, private repository). Архитектурное решение и отклонённые альтернативы зафиксированы в SPEC §21.8 и CHANGELOG (раздел Decisions) — к вопросу не возвращаемся.

**Принимаемые риски:** прямой push в `main` всё ещё возможен (а) с машины, где hook не установлен через `setup-hooks.sh`, (б) при явном `git push --no-verify`. Митигация — дисциплина flow и минимальное число контрибьюторов с прямым доступом.

Корректный workflow:

    git checkout -b feat/my-change
    # ... правки, коммиты ...
    git push origin feat/my-change
    # создать PR в GitHub UI → дождаться зелёного CI → merge

Если pre-push hook сработал и заблокировал push — это **ожидаемое поведение**, а не ошибка. Переключись на фича-ветку и открой PR.

В критических случаях (например, hotfix во время инцидента) hook можно временно обойти:

    git push --no-verify

⚠️ Используй `--no-verify` для push **только** если действительно нужно срочно и согласовано с командой. Server-side защиты, которая поймала бы такой push на стороне GitHub, **нет** — ответственность полностью на тебе.

### Обход pre-commit hook (только в крайних случаях)

    git commit --no-verify -m "..."

⚠️ Используй **только** если 100% уверен, что это ложное срабатывание.

---

## Документация

- **[SPEC.md](SPEC.md)** — полная спецификация проекта, архитектура, инциденты и уроки
- **[CHANGELOG.md](CHANGELOG.md)** — история изменений по версиям
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — гайд для контрибьюторов: setup, workflow, стиль кода
- **[docs/SECURITY.md](docs/SECURITY.md)** — security posture и ADR
- **[docs/BACKUP.md](docs/BACKUP.md)** — регламент бэкапов БД

---

## Тестирование

Юнит-тесты (`pytest`) и Bash-тесты бэкап-скриптов покрывают критичные узлы:
БД, начисления баллов, верификация возраста, бэкап-скрипты с healthcheck.

```bash
# Установка dev-зависимостей (один раз)
pip install -r requirements-dev.txt

# Запуск всех тестов
pytest

# С покрытием (term + HTML отчёт в htmlcov/index.html)
pytest --cov=. --cov-config=.coveragerc --cov-report=term-missing --cov-report=html
```

**Текущее покрытие: 11%** (см. badge выше). Это baseline после введения
`pytest-cov`. Прицельно покрыто:

- `config.py` (97%) — загрузка конфигурации
- `services/admin_notify.py` (91%) — алерты админу
- `db.py` (43%) — критичные операции с БД (points, register_purchase, levels)

CI блокирует regress: `--cov-fail-under=10` в `.github/workflows/ci.yml`.
При значимом росте покрытия — поднимаем порог и обновляем badge в README.

Artifacts CI (доступны 14 дней в GitHub Actions runs):

- `coverage-html-<run_id>` — HTML-отчёт (открыть `index.html`)
- `coverage-xml-<run_id>` — XML для внешних инструментов (Codecov и т.п.)

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
