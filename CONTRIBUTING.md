# Contributing to SMOKTOLK Bot

Спасибо за интерес к проекту! Этот документ описывает, как внести вклад в SMOKTOLK Bot — от установки окружения до отправки pull request.

Документ предназначен как для постоянных мейнтейнеров, так и для внешних контрибьюторов.

---

## 📋 Содержание

- [Code of Conduct](#code-of-conduct)
- [Способы внести вклад](#способы-внести-вклад)
- [Setup окружения разработчика](#setup-окружения-разработчика)
- [Workflow разработки](#workflow-разработки)
- [Стиль кода и коммитов](#стиль-кода-и-коммитов)
- [Quality gates](#quality-gates)
- [Pull request: как открыть и провести](#pull-request-как-открыть-и-провести)
- [Документация](#документация)
- [Security](#security)
- [Полезные ссылки](#полезные-ссылки)

---

## Code of Conduct

Проект следует принципам уважительного и конструктивного общения:

- Будь вежлив и терпелив с другими контрибьюторами.
- Критика — только по существу кода, не личности.
- Не приемлемо: оскорбления, дискриминация, харассмент, троллинг.
- О проблемах с поведением — сообщай мейнтейнеру через приватный канал.

Если не уверен, уместен ли комментарий — лучше переформулируй или не отправляй.

---

## Способы внести вклад

### 🐛 Сообщить о баге

1. Проверь [open issues](https://github.com/shushpanchik-art/smoktolk-bot/issues) — возможно, баг уже зарегистрирован.
2. Создай новый issue, используя [Bug report template](.github/ISSUE_TEMPLATE/bug_report.md):
   - Что произошло (ожидаемое vs реальное поведение).
   - Шаги воспроизведения.
   - Версия Python, ОС, логи (без секретов!).

### ✨ Предложить feature

1. Сначала открой issue, используя [Feature request template](.github/ISSUE_TEMPLATE/feature_request.md), с тегом `enhancement` для обсуждения.
2. Опиши проблему, которую решает feature, и предложенное решение.
3. Дождись отклика мейнтейнера — feature может конфликтовать с roadmap (см. SPEC.md §20).

### 📚 Улучшить документацию

Документация — это полноценный вклад. Если нашёл опечатку, неточность или непонятное место в README/SPEC/docs — открывай PR напрямую, обсуждение через issue не требуется.

### 🔧 Прислать код

См. разделы Setup и Workflow ниже.

---

## Setup окружения разработчика

### Требования

- **Python 3.11** (см. `.github/workflows/ci.yml`, проект тестируется только на 3.11).
- **git** ≥ 2.30.
- **gitleaks** (для pre-commit hook).
- Linux/macOS. Windows формально не поддерживается (используется bash в hooks).

### Пошаговая установка

1. Форкни репозиторий через UI GitHub, затем клонируй свой форк:

       git clone git@github.com:<твой-username>/smoktolk-bot.git
       cd smoktolk-bot

2. Добавь upstream:

       git remote add upstream git@github.com:shushpanchik-art/smoktolk-bot.git

3. Создай и активируй виртуальное окружение:

       python3.11 -m venv venv
       source venv/bin/activate

4. Установи зависимости:

       pip install -r requirements.txt
       pip install -r requirements-dev.txt

5. Установи gitleaks:

   Linux:

       GITLEAKS_VERSION=8.18.4
       wget https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz
       tar -xzf gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz gitleaks
       sudo mv gitleaks /usr/local/bin/

   macOS:

       brew install gitleaks

6. **ОБЯЗАТЕЛЬНО:** установи git hooks:

       ./scripts/setup-hooks.sh

7. Скопируй `.env.example` в `.env` и заполни:

       cp .env.example .env

   **Никогда не коммить `.env` в git!**

### Проверка установки

    pytest                                    # все тесты должны пройти
    ruff check .                              # линтер без ошибок
    ls -la .git/hooks/pre-commit              # hooks установлены
    ls -la .git/hooks/pre-push

---

## Workflow разработки

### Цикл работы над изменением

    upstream/main
         │
         ├──► fork/main  (sync)
         │       │
         │       └──► feature/my-change  ──► PR ──► review ──► squash-merge ──► upstream/main
         │
         └──► CI checks (ruff, bandit, pip-audit, pytest)

### Шаги

1. **Синхронизируй fork с upstream:**

       git checkout main
       git fetch upstream
       git merge upstream/main
       git push origin main

2. **Создай feature-ветку от актуального main:**

       git checkout -b feature/short-descriptive-name

   Не работай напрямую в `main` — local pre-commit hook заблокирует коммит, а pre-push hook — push (см. SPEC §21.8).

3. **Внеси изменения** небольшими атомарными коммитами.

4. **Перед каждым коммитом** автоматически запустятся:
   - `gitleaks` — поиск секретов в diff.
   - `ruff check` — линтинг изменённых `.py` файлов.

   Если хук блокирует коммит — **исправь причину**, не обходи `--no-verify`.

5. **Прогони тесты локально** перед push:

       pytest

6. **Запушь ветку и открой PR:**

       git push origin feature/short-descriptive-name
       gh pr create

---

## Стиль кода и коммитов

### Python код

- **Линтер:** `ruff` (настройки по умолчанию, проверяется в CI и в pre-commit).
- **Форматирование:** PEP 8 + общий стиль проекта.
- **Type hints:** приветствуются для публичных функций, не обязательны.
- **Docstrings:** для нетривиальных функций (на русском, как в существующем коде).

### Имена веток

- `feature/` — новая функциональность (`feature/loyalty-tiers-v2`)
- `fix/` — исправление бага (`fix/webhook-timeout`)
- `docs/` — только документация (`docs/spec-section-22`)
- `chore/` — инфраструктура, CI, deps (`chore/bump-aiogram`)
- `security/` — security-фиксы (`security/pin-actions-sha`)

### Commit messages (Conventional Commits)

Проект использует [Conventional Commits](https://www.conventionalcommits.org/):

    <type>(<scope>): <короткое описание>

    [опциональное тело — что и зачем]

    [опциональный footer — closes #123, BREAKING CHANGE]

**Типы:**

- `feat` — новая функциональность (попадает в CHANGELOG)
- `fix` — исправление бага
- `docs` — документация
- `chore` — рутина, не влияющая на код
- `refactor` — рефакторинг без изменения поведения
- `test` — добавление/исправление тестов
- `security` — security-фиксы
- `ops` — инфраструктура, deployment, бэкапы

**Примеры из истории проекта:**

    feat(security): ruff в pre-commit + ADR docs/SECURITY.md
    fix(ops): fsync backup files for durability against power loss
    chore(deps): document requirements.txt with inline rationale
    docs(ops): refresh stale WebDAV-era comments in full-offsite unit

### PR title

PR title должен следовать тому же формату Conventional Commits, потому что мы используем **squash-merge** — title PR становится сообщением финального коммита в `main`.

---

## Quality gates

### Локально (pre-commit hook)

Запускается автоматически при `git commit`:

| Инструмент | Что проверяет | Источник |
|---|---|---|
| **branch guard** | Запрет прямого коммита в `main` | `scripts/git-hooks/pre-commit` |
| `gitleaks` | Секреты в staged changes | `scripts/git-hooks/pre-commit` |
| `ruff check` | Линтинг изменённых `.py` | то же |

### Локально (pre-push hook)

Запускается при `git push`:

- ❌ **Запрет push напрямую в `main`** (защита от force-push в защищённую ветку).

### CI (GitHub Actions, `.github/workflows/ci.yml`)

Запускается на каждый PR:

| Job | Инструмент | Что проверяет |
|---|---|---|
| Lint | `ruff` | Стиль и базовые ошибки |
| Security | `bandit` | Security issues в Python коде |
| Audit | `pip-audit` | CVE в зависимостях `requirements.txt` |
| Syntax | `python -m py_compile` | Синтаксис всех `.py` |
| Tests | `pytest` | Unit и integration тесты |

**Все 5 чеков должны быть зелёными** до мержа PR.

### Обход хуков — НЕ ДЕЛАЙ

`git commit --no-verify` существует, но используется **только в реальной аварии** (production hotfix в 3 часа ночи). См. подробности в [docs/SECURITY.md](docs/SECURITY.md). Любой обход — повод объяснить причину в PR description.

### Подробнее об инструментах

См. `SPEC.md` §17.4 «Инструменты контроля качества и безопасности кода».

---

## Pull request: как открыть и провести

### Перед открытием PR

- [ ] Все локальные тесты проходят (`pytest`).
- [ ] `ruff check .` без ошибок.
- [ ] `CHANGELOG.md` обновлён (для `feat`/`fix`/`BREAKING`).
- [ ] `SPEC.md` обновлён, если меняется контракт или бизнес-правило.
- [ ] Нет секретов в diff (gitleaks в pre-commit это проверит, но перепроверь глазами).
- [ ] Длинные heredoc не используются (см. SPEC §24.2 — известная проблема с генерацией кода через AI).

### Шаблон PR

При открытии PR автоматически подставится [PR template](.github/pull_request_template.md) — заполни его полностью.

### Review process

1. **Автоназначение:** `CODEOWNERS` автоматически добавит мейнтейнера в reviewers.
2. **CI:** дождись зелёных чеков. Если что-то красное — исправь и пуш в ту же ветку.
3. **Обсуждение:** отвечай на комментарии reviewer'а в разумные сроки.
4. **Изменения:** делай новые коммиты в ветку — squash-merge схлопнет их в один.
5. **Approve:** после approve мейнтейнер мержит PR через **Squash & Merge** и удаляет feature-ветку.

### Размер PR

- 🟢 **Хорошо:** PR на 50–300 строк изменений, одна логическая задача.
- 🟡 **Терпимо:** до 800 строк, если задача атомарна.
- 🔴 **Плохо:** PR на 2000+ строк или «починил баг + добавил фичу + рефакторинг».

Большую задачу разбей на несколько PR, договорившись о порядке мержа.

---

## Документация

Если изменение затрагивает поведение бота — обнови соответствующие документы:

| Документ | Когда обновлять |
|---|---|
| `README.md` | Изменения в setup, запуске, базовых командах |
| `SPEC.md` | Изменения в бизнес-логике, конфигурации, контрактах |
| `CHANGELOG.md` | Любая user-visible change (feat/fix/breaking) |
| `docs/BACKUP.md` | Изменения в процессе бэкапа БД |
| `docs/SECURITY.md` | Изменения в security-policy, hooks, секретах |
| `docs/ANIMATED_AVATAR_RECIPE.md` | Изменения в логике анимированных аватаров |

### Стиль документации

- Язык — **русский** (вся существующая документация на русском).
- Markdown, заголовки иерархически (`#` → `##` → `###`).
- Примеры кода — в fenced блоках или с отступом в 4 пробела.
- Команды для запуска — копируемые целиком, без сокращений.
---

## 🏗 Архитектурная шпаргалка

Быстрая справка по устройству продакшн-окружения и ключевым решениям (полное описание — в SPEC.md).

**Окружение и запуск:**
- **Python: только `venv/bin/python`**, НЕ системный `python3` (в системном нет зависимостей проекта). Все команды импорт-проверки и запуска — через venv.
- Прод запускается под **systemd**: `ExecStart=/opt/smoktolk/bot/venv/bin/python bot.py`, `WorkingDirectory=/opt/smoktolk/bot`. Управление: `systemctl restart smoktolk-bot` (уточни точное имя unit через `systemctl list-units | grep smoktolk`).

**Стек:**
- Фреймворк — **aiogram 3.29.1**.
- БД — **SQLite** через `aiosqlite`, путь в `config.DB_PATH`.
- Веб — **aiohttp** (вебхук кассы, порт `config.WEBHOOK_PORT`).
- Хендлеры — `handlers/*.py`, роутеры собираются в `ROUTERS`.

**Проверки перед коммитом:**
- Синтаксис (не требует venv): `python3 -c "import ast; ast.parse(open('bot.py').read())"`.
- Импорт-проверка модулей — **только** `venv/bin/python -c "import ..."`.

**Тонкости aiogram:**
- API-layer middleware (перехват вызовов Bot API) регистрируется через `bot.session.middleware.register(fn)`. Сигнатура: `async def fn(make_request, bot, method)`. ⚠️ `bot.session.middleware(fn)` (без `.register`) — падает.
- Модуль `msg_wipe`: логирует `message_id` исходящих сообщений бота в таблицу `bot_messages` и умеет удалять собственные сообщения моложе 48 ч (ограничение Bot API). Полное стирание истории чата боту недоступно.

---

## Security

### Никогда не коммить

- `.env` файлы с реальными значениями.
- Токены Telegram бота, ключи API, пароли БД, SSH-ключи.
- Личные данные клиентов (даже в тестовых данных и логах).
- Production URL с авторизацией.

Pre-commit hook (gitleaks) ловит большинство случаев, но **внимательность — твоя ответственность**.

### Если случайно закоммитил секрет

1. **НЕ просто удаляй в следующем коммите** — он остаётся в истории.
2. **Немедленно отзови секрет** (revoke token, смени пароль).
3. См. инструкцию в `SPEC.md` §0 «🛡 Если случайно отправил токен».
4. Если коммит уже в публичной ветке — пиши мейнтейнеру, нужна `git filter-repo` чистка истории.

### Полное security-policy

См. [docs/SECURITY.md](docs/SECURITY.md) — ADR по security posture, обоснование архитектурных решений.

---

## Полезные ссылки

### В этом репозитории

- [README.md](README.md) — общая информация о проекте
- [SPEC.md](SPEC.md) — техническая спецификация (источник истины по бизнес-логике)
- [CHANGELOG.md](CHANGELOG.md) — история изменений
- [docs/SECURITY.md](docs/SECURITY.md) — security policy и ADR
- [docs/BACKUP.md](docs/BACKUP.md) — процедуры бэкапа БД
- [.github/pull_request_template.md](.github/pull_request_template.md) — шаблон PR
- [scripts/setup-hooks.sh](scripts/setup-hooks.sh) — установщик git hooks

### Внешние

- [Conventional Commits](https://www.conventionalcommits.org/)
- [PEP 8 — Python style guide](https://peps.python.org/pep-0008/)
- [GitHub Flow](https://docs.github.com/en/get-started/quickstart/github-flow)
- [Ruff documentation](https://docs.astral.sh/ruff/)

---

## Вопросы?

- 💬 Вопросы по архитектуре — issue с тегом `question`.
- 🐛 Баги — issue с тегом `bug`.
- 📧 Приватные вопросы (security, etc.) — через контакты мейнтейнера.

Спасибо за вклад! 🎉
