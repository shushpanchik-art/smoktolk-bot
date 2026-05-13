# Changelog

Все значимые изменения проекта документируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), проект следует [Semantic Versioning](https://semver.org/lang/ru/).

---

## [Unreleased]

### Security

- **Bump dev-зависимостей**: `pytest 8.3.4 → 9.0.3`, `pytest-asyncio 0.25.2 → 1.3.0`.
  Закрывает Dependabot alert [#28](https://github.com/shushpanchik-art/smoktolk-bot/security/dependabot/28)
  (CVE-2025-71176 / GHSA-6w46-j5rx-g56g — `pytest` tmpdir handling, severity: moderate, scope: development).
  Alert [#29](https://github.com/shushpanchik-art/smoktolk-bot/security/dependabot/29) — тот же CVE,
  выписанный на `requirements.txt`, был устаревшим (pytest удалён из prod-зависимостей при разделении
  dev/prod ещё до этого PR). Закрыт Dependabot'ом автоматически как `fixed` после переоценки графа
  зависимостей (промежуточно вручную был помечен `dismissed`, но GitHub перевёл его в `fixed` поверх). `pytest-asyncio` поднят до 1.x, т.к. 0.25.2 жёстко требует `pytest<9`.
  Проверено: все 17 существующих тестов проходят (`asyncio_mode = auto` совместим с 1.x,
  breaking changes major-релиза не затрагивают наш код).

### Added
- **ROADMAP в SPEC §20**: переработан раздел «Технический долг» в единую
  точку входа для всех запланированных работ. Добавлены подразделы
  перспективных продуктовых работ: П-1 «Система начисления баллов за покупку
  (live)» и П-2 «Подтверждение возраста через ЕСИА». Сохранены секции
  высокого/среднего/низкого приоритета. Зафиксированы принципы работы с
  roadmap (приоритезация, закрытие через `~~зачёркивание~~`, статус
  «список идей» для 🟢). <!-- ROADMAP-V2-CHANGELOG -->
- **Docs-коррекция защиты `main`** (этот PR): убраны упоминания server-side branch protection из SPEC §21.8 / §20 и README. В SPEC §21.8 добавлен Decision-блок с отклонёнными альтернативами (GitHub Pro, публикация репо) и принимаемыми рисками. В §20 пункт «Branch protection для `main`» помечен как закрытый со ссылкой на §21.8. Формулировки в CHANGELOG Unreleased приведены в соответствие («двойная защита» → «единственный уровень»). Follow-up к #28, к вопросу server-side BP не возвращаемся.
- **Pre-push git hook** (`scripts/git-hooks/pre-push`): блокирует прямой `git push` в ветку `main` локально, до отправки на GitHub. Это **единственный уровень защиты** ветки `main` — server-side branch protection не используется (free private tier, см. Decisions ниже). Устанавливается через `scripts/setup-hooks.sh`.
- **CI workflow на pre-push hook**: добавлен smoke-тест в `.github/workflows/ci.yml`, проверяющий, что hook исполняемый, корректно блокирует push в `main` и пропускает push в фича-ветки.
- **SPEC §21.8**: документация защиты ветки `main` через локальный pre-push hook (единственный уровень защиты на free private tier; Decision-блок с отклонёнными альтернативами и принимаемыми рисками), описание поведения hook, инструкция обхода через `--no-verify` для emergency-кейсов.
- **SPEC §24.7**: принцип «документация как часть Definition of Done» — изменение в коде/конфигурации/процессе не считается завершённым, пока соответствующая документация (SPEC/README/CHANGELOG) не обновлена в том же PR.
- **SPEC §16**: файл `scripts/git-hooks/pre-push` добавлен в список файлов проекта.
- **README**: в раздел «Безопасность» добавлен подраздел «Защита ветки `main`» с описанием локальной защиты (pre-push hook), явным указанием что server-side BP не используется, перечнем принимаемых рисков и корректного workflow через PR.
- **Алерт админу о крэше бота** (DOWN / RECOVERED): двусторонние уведомления в Telegram при реальном падении процесса и при успешном восстановлении. Штатные операции (`systemctl restart/stop`, деплой) уведомлений не вызывают.
  - **Архитектура:** два независимых канала через systemd (`ExecStopPost` в drop-in + `OnFailure` на резервный oneshot-юнит) с общим state-файлом `/run/smoktolk-bot/crashed` для идемпотентности (анти-дубликат DOWN при серии крэшей).
  - **RECOVERED отправляется из Python (`crash_alert.py`), а не systemd**, чтобы уведомление уходило только после фактической готовности бота (`init_db` + `get_me` + `catalog.refresh`), а не сразу после fork процесса.
  - **Новые файлы:** `crash_alert.py`, `scripts/notify_admin.sh`, `systemd/smoktolk-bot-alert.service`, `systemd/smoktolk-bot.service.d/10-alerts.conf`.
  - **Изменения:** `bot.py` (import + вызов `notify_recovered_if_needed` в `on_startup`), `SPEC.md` (новый раздел §25 с архитектурой, таблицей сценариев, эксплуатацией и инцидент-историей).
  - **Безопасность:** `BOT_TOKEN` и `ADMIN_CHAT_ID` читаются из окружения через `config`; в коде, скриптах и unit-файлах секретов нет (проверено `grep -RniE 'token|password|secret|api_key'`).

### Verified

- **Pre-push hook**: проведены оба сценарных теста после merge PR #28.
  - **Позитивный** (push в фича-ветку): hook разрешает push, выводит сообщение об успешном прохождении. Push доходит до GitHub штатно.
  - **Негативный** (прямой push в `main`): hook блокирует операцию до отправки на сервер, выводит сообщение об отказе с инструкцией по правильному PR-флоу и подсказку про emergency `--no-verify`. `git push` возвращает non-zero, push не доходит до сервера.
  - Дополнительно: delete-операция в фича-ветке (`git push origin --delete feature/...`) обрабатывается hook'ом корректно и разрешается.
- **Алерт крэша бота**: проверены ключевые сценарии (см. SPEC §25.4).
  - `systemctl restart smoktolk-bot` → тишина (штатный рестарт не триггерит DOWN).
  - `systemctl stop smoktolk-bot` → тишина (штатная остановка не триггерит DOWN).
  - `kill -9 <pid>` → 1×DOWN → автостарт через `Restart=always` → 1×RECOVERED после полной инициализации (`init_db` + `get_me` + `catalog.refresh`).
  - Серия крэшей подряд (множественные рестарты) → 1×DOWN на цикл, дубликаты подавлены через state-файл `/run/smoktolk-bot/crashed`.
  - Чистый старт после `systemctl reset-failed` без предшествующего крэша → тишина (state-файл отсутствует, RECOVERED не отправляется).
  - Синхронизация репозитория с боевыми путями (`/etc/systemd/system/smoktolk-bot.service.d/10-alerts.conf`, `/etc/systemd/system/smoktolk-bot-alert.service`) подтверждена через `diff` — файлы идентичны.

### Decisions

- **Server-side branch protection для `main` НЕ внедряется**. Архитектурное решение, зафиксированное окончательно — к вопросу не возвращаемся.
  - **Причина:** GitHub Branch Protection Rules недоступны на текущем плане (free, private repository). Подтверждено через `gh api repos/.../branches/main/protection` → HTTP 403 с сообщением "Upgrade to GitHub Pro or make this repository public to enable this feature."
  - **Рассмотренные альтернативы и почему отклонены:**
    - Upgrade на GitHub Pro (~$4/мес) — отклонено: текущей защиты достаточно для команды из одного контрибьютора.
    - Сделать репозиторий публичным — отклонено: код содержит логику доменной модели, которую нецелесообразно открывать.
  - **Принятая модель защиты `main`:** только локальный pre-push hook (`scripts/git-hooks/pre-push`), устанавливаемый через `scripts/setup-hooks.sh`. Это **единственный уровень защиты**, не «дополнительный». Формулировки SPEC §21.8 и README приведены в соответствие (см. запись в Added ниже).
  - **Принимаемые риски:** push в `main` возможен (а) с машины, где hook не установлен через `setup-hooks.sh`, (б) с явным `--no-verify`. Митигация — дисциплина flow и минимальное число контрибьюторов с прямым доступом.

### Known issues / TODO

- Добавить `pytest-cov` и coverage-бейдж в README (отдельный PR).

---

## [0.2.2] — 2026-05-12

### Changed
- **SPEC §24.6** (#TBD): лимит длины ответа AI-ассистента увеличен с 10 000 до **31 000 символов**.
  - Основание: официальное подтверждение от поддержки Claude — модельный лимит 32 000 токенов на ответ.
  - Лимит выражен в символах (а не токенах) для простоты ручной самопроверки.
  - Для кириллицы 31 000 символов ≈ 10–15k токенов, запас 2–3× относительно модельного лимита.
  - 1 000 символов запаса (от 32k теоретического до 31k рабочего) — буфер на пограничные случаи токенизации.

### Internal
- Аудит и профилирование production-бота:
  - RSS 284 MB (29% от 970 MB RAM), CPU idle, 0 ошибок за 24h.
  - Зафиксированы наблюдения для будущих улучшений: добавить swap-файл, выставить `MemoryMax` в systemd unit, периодический мониторинг RSS.
  - БД 72 KB, 4 пользователя, 18 записей — система здорова.

## [0.2.1] - 2026-05-12

### Changed

- **SPEC §24.6:** уточнена формулировка правила о лимите длины ответа AI-ассистента. Лимит 10 000 символов теперь явно описан как **потолок безопасности**, а не цель экономии. Добавлен пункт «не сокращать ради сокращения» — ассистент должен упаковывать максимум полезной работы в один ответ (#21).

## [0.2.0] — 2026-05-12

Релиз закрывает большой пласт работы по качеству кода, безопасности и непрерывной интеграции: проведён первый полный code quality audit, исправлены все находки, поднят GitHub Actions CI workflow, существенно расширена SPEC.

### Added

- **GitHub Actions CI workflow** (`.github/workflows/ci.yml`, PR #17): 4 параллельных job — Python syntax check (`py_compile`), Ruff lint, Bandit security scan, pip-audit для `requirements.txt`. Триггеры: `push` в `main`, `pull_request`. После исправления audit findings (PR #18) у Ruff и Bandit снят `continue-on-error` — джобы стали блокирующими.
- **SPEC раздел 21.7** — описание GitHub Actions CI workflow: триггеры, 4 джоба, связь с локальными dev-tools из §17.4, где смотреть статус.
- **README**: бейдж статуса CI, бейдж Python 3.11+, новая секция «Quality checks» с командами локального запуска `ruff check .`, `bandit -r . -ll`, `pip-audit -r requirements.txt`.
- **SPEC раздел 17.6** — audit follow-up: фиксация результатов исправления находок code quality audit 2026-05-11.
- **SPEC раздел 17 расширен** (PR #12): подразделы 17.1 «Проверка синтаксиса Python-файлов через ast.parse», 17.2 «Корректный путь к БД SQLite (`data/smoktolk.db`)», 17.3 «Где искать что — быстрая шпаргалка», явное упоминание `logs/bot.log` как основного лога приложения.
- **SPEC раздел 17.4** (PR #15) — документация по инструментам контроля качества и безопасности: ruff (линтер), bandit (security-сканер кода), pip-audit (CVE в зависимостях), vulture (мёртвый код), radon (цикломатическая сложность), Dependabot, gitleaks. Каждый инструмент с готовой командой запуска.
- **SPEC раздел 17.5** (PR #15) — регламент регулярных проверок: периодичность (перед каждым PR / еженедельно / ежемесячно / при CVE high+), целевые показатели (0 ошибок ruff в проектном коде, 0 medium+ bandit, 0 CVE в requirements.txt, max 1-2 функции категории D в radon).
- **SPEC раздел 21** — секция про GitHub CLI / gh PR workflow (PR #10).
- **SPEC раздел 23** — история инцидентов с AI-ассистентом:
  - 23.6 — `gh pr view` падает на устаревшем GraphQL-поле `projectCards`;
  - 23.7 — рецидив heredoc-инцидента №2 (LESSONS_LEARNED.md);
  - 23.8 — рецидив heredoc-инцидента №3 (`python3 << EOF`, `cat << EOF` с markdown).
- `CHANGELOG.md` — история изменений в формате Keep a Changelog.
- `README.md`: блок «Документация» со ссылками на SPEC.md и CHANGELOG.md.
- `.gitignore`: правило `*.bak-*` для исключения timestamped-бекапов.

### Changed

- Обновлён **aiogram**: `3.13.1` → `3.28.2` (через Dependabot PR #1 с ручным review).
- Политика версионирования: переход от «фиксируем точно» к «контролируемые апгрейды через Dependabot».
- **SPEC обновлён до v1.2**: актуализирована версия aiogram, зафиксирована новая политика обновлений зависимостей.
- Правило 24.2 SPEC расширено: heredoc запрещён для `python3 << EOF`, `cat > file << EOF`, `bash << EOF` с многострочным содержимым.

### Fixed

- **PR #9** `handlers/profile.py`: исправлена сигнатура вызова `create_redemption()` — была причина падения QR списания баллов. Теперь QR списания и QR подарков работают штатно (проверено в продакшне).
- **Code quality findings (audit 2026-05-11)** исправлены в PR #18:
  - `catalog.py:126` — удалены неиспользуемые `import io, shutil, tempfile`, оставлен только `import zipfile`;
  - `keyboards.py:2` — удалён неиспользуемый `InlineKeyboardButton` из импорта `aiogram.types`;
  - `tasks.py:4` — удалён неиспользуемый `time` из импорта `datetime`;
  - `handlers/profile.py:109,120` — переменная `l` (level) переименована в `lvl` (ruff E741);
  - `handlers/profile.py:155` — убран префикс `f` у строки без placeholders (ruff F541);
  - `webhook.py:188` — неиспользуемая переменная `backup = payload.get("backup_code")` заменена на закомментированный TODO-фрагмент с пояснением (fallback по `backup_code` не реализован, см. SPEC);
  - `db.py:601` — добавлен комментарий `# nosec B608` к `UPDATE daily_stats SET {field}=...` (ложное срабатывание Bandit; `field` проверен по whitelist строкой выше, параметры через `?`).
- **Результат после правок:** ruff 0 ошибок в проектном коде, bandit 0 medium+; CI-чеки `Ruff lint` и `Bandit security scan` зелёные без `continue-on-error`.

### Security

- Настроен **Dependabot** для еженедельного автообновления зависимостей (`pip`, `github-actions`).
- Установлен **gitleaks** как pre-commit hook — блокирует коммиты с секретами (Telegram-токены, GitHub PAT, AWS keys и др.).
- Добавлен установщик git-hooks (`scripts/setup-hooks.sh`) для автоматизации настройки у новых разработчиков.
- Поднят **CI security gate** (PR #17, #18): bandit и pip-audit прогоняются на каждом push/PR; medium+ findings блокируют merge.
- Удалён небезопасный разовый бэкап `backups/env_bak_20260509.tar.gz` (содержал `.env` с боевыми токенами при странных правах `0620`); процедура бэкапа `.env` пересмотрена — разовые архивы с секретами больше не создаются вручную.

### Audit

- **Code quality audit 2026-05-11** проведён инструментами ruff, bandit, pip-audit, vulture, radon. Результаты:
  - **ruff**: 10 замечаний (7 fixable) — unused imports, неоднозначное имя переменной `l`, одна f-string без placeholder, одна неиспользуемая переменная `backup` в `webhook.py` (technical debt — недореализованный fallback по `backup_code`). Исправлены в PR #18.
  - **bandit (проектный код)**: 1 medium (`db.py:601`) — ложное срабатывание, whitelist через множество `allowed` проверяется до подстановки в SQL. Закрыт аннотацией `# nosec B608` с пояснением.
  - **pip-audit (requirements.txt)**: 0 уязвимостей.
  - **pip-audit (venv)**: 1 устаревший системный пакет `setuptools 66.1.1` (CVE-2024-6345, PYSEC-2025-49) — не используется ботом напрямую, обновление по плану.
  - **vulture**: 3 unused imports (тот же набор, что и ruff).
  - **radon CC**: 1 функция категории E (`webhook.handle_purchase`, CC>40), 1 категории D (`catalog._parse_xlsx`), 3 категории C — кандидаты на рефакторинг (технический долг).
  - **Dependabot alerts**: 27 алертов, все `fixed`; 0 открытых PR.

### Housekeeping

- Удалены устаревшие локальные бэкапы SPEC.md (`SPEC.md.bak.*`).
- Удалены разовые архивы из `backups/` (старше 30 часов и не от cron): `backup_20260509_1840.tar.gz`, `backup_before_addon_20260509_1813.tar.gz`, `catalog_20260509_174135.xlsx`, `smoktolk_20260509_174135.db`.
- Удалены локальные `__pycache__/` каталоги (генерируются при запуске бота).
- Удалены смерженные локальные ветки: `docs/incidents-23.6-23.7`, `fix/create-redemption-signature`, `docs/spec-diagnostics-notes`, `docs/spec-incident-heredoc-recurrence`, `docs/changelog-code-quality-audit`, `docs/spec-code-quality-tools`, `chore/changelog-and-cleanup`, `fix/code-quality-audit-findings`.
- Очищены stale remote-ссылки (`git fetch --prune`).
- Проведён комплексный security-аудит проекта (2026-05-11): pip-audit для `requirements.txt` — 0 уязвимостей; bandit для проектного кода — 1 medium (`db.py:601`, ложное срабатывание — whitelist полей сделан строкой выше) и 0 high; все 27 Dependabot security alerts в состоянии `fixed`.
- Установлены и зафиксированы dev-инструменты в venv: ruff 0.15.12, bandit 1.9.4, pip-audit, vulture, radon (используются для регламентных проверок согласно SPEC 17.5).

---

## [0.1.0] — 2026-05-10

Первый baseline проекта: инфраструктура, конфигурация, документация. Бизнес-логика бота — в `app/`, реализована на момент initial snapshot.

### Added

- **Initial snapshot** бота SMOKTOLK с технической спецификацией **SPEC v1.1**.
- Конфигурация **Dependabot** (`.github/dependabot.yml`): еженедельное автообновление Python-зависимостей (`pip`), ежемесячное обновление GitHub Actions.
- **Gitleaks pre-commit hook** + установщик `scripts/setup-hooks.sh`.
- **README.md** с инструкциями для разработчика (установка, запуск, структура проекта).

### Security

- Pre-commit сканирование секретов через **gitleaks** — защита от случайного коммита токенов.
- Автоматический мониторинг уязвимостей в зависимостях через **Dependabot**.

### Notes

- Данная версия фиксирует **инфраструктурный baseline** перед началом активной работы над фичами.
- На момент `0.1.0` открыты 4 Dependabot-PR (pillow, pytz, qrcode, python-minor-patch group) — будут обработаны в следующих релизах.

---

## Категории изменений

- **Added** — новая функциональность
- **Changed** — изменения в существующей функциональности
- **Deprecated** — функциональность, которая будет удалена
- **Removed** — удалённая функциональность
- **Fixed** — исправления багов
- **Security** — улучшения безопасности и обновления уязвимых зависимостей
- **Audit** — результаты регламентных проверок качества и безопасности
- **Housekeeping** — техническое обслуживание репозитория
