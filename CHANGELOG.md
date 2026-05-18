# Changelog

Все значимые изменения проекта документируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), проект следует [Semantic Versioning](https://semver.org/lang/ru/).

---

## [Unreleased]

### Added — Pre-commit branch guard (PR chore/hook-block-commit-to-main)
- **`scripts/git-hooks/pre-commit`**: добавлен блок «branch guard» в самом
  начале хука. Сравнивает текущую ветку (`git symbolic-ref --short HEAD`) со
  списком `PROTECTED_BRANCHES="main"` и при совпадении прерывает коммит
  с подсказкой по правильному PR-flow и упоминанием экстренного обхода
  через `git commit --no-verify`. Срабатывает до `gitleaks` и `ruff`.
- **Rationale:** до этого PR клиентская защита `main` была односторонней —
  `pre-push` блокировал push в `refs/heads/main`, но `git commit` напрямую
  на ветке `main` проходил. Сценарий «закоммитил в main → попытался
  запушить → push заблокирован → застрял с локальным коммитом в main»
  встречался многократно (см. SPEC §23.x — heredoc-инциденты с
  ошибочными коммитами в main). Branch guard в pre-commit делает защиту
  симметричной обоим этапам (commit + push) и устраняет необходимость
  ручного `git reset --soft HEAD~1` после ошибки.
- **Проверено:** ручной тест на чистом репо — коммит из `main`
  блокируется с exit=1, коммит из feature-ветки проходит без изменения
  поведения существующих проверок (gitleaks, ruff).
- **Документация:** обновлены `SPEC.md §21.4` (фикс устаревшего упоминания
  «симлинка» — на самом деле `cp`), `§21.8` (состав pre-commit: три
  проверки вместо двух; «Связь с другими защитами»),
  `docs/AI_ONBOARDING.md` (секция «Локальные quality-gates» + таблица
  безопасности), `CONTRIBUTING.md` (таблица локальных проверок + подсказка
  про защиту main).
- **Установка для существующих машин:** `./scripts/setup-hooks.sh` после
  `git pull` (хуки копируются через `cp`, не симлинкуются — см. SPEC §21.8).

### Added — AI onboarding guide (PR docs/ai-onboarding-guide)
- **`docs/AI_ONBOARDING.md`** (новый, ~170 строк): единый «вводный пакет»
  для нового AI-ассистента, открывающего проект с нуля. Содержит:
  стек и архитектуру (Python 3.11/aiogram/aiohttp/SQLite, монолит, systemd),
  бизнес-логику (10 баллов = 1 ₽, TTL 120д, уровни, категории — со ссылками
  на `SPEC.md` §5–9), карту структуры репозитория, статус деплоя
  (`systemd-analyze security` = 1.3 OK), CI/CD jobs и coverage baseline
  (11.36%, 103 теста), инвентарь безопасности с явной фиксацией accepted
  risks (Branch Protection, signed commits, MemoryDenyWriteExecute),
  конвенции (Conventional Commits, PR-only workflow), правила
  взаимодействия с AI (SPEC §0, §24 — heredoc-инциденты §23.4–23.8),
  roadmap (SPEC §20) и стартовый набор команд для первого сообщения.
- **`SPEC.md`**: в шапку добавлена строка-указатель на
  `docs/AI_ONBOARDING.md` сразу после ссылки на `docs/OPERATIONS.md`.
- **Rationale:** до этого PR при смене контекста (новый чат с ИИ,
  возвращение к проекту через паузу, передача коллеге) приходилось
  собирать вводную вручную из `SPEC.md`, `README.md`, `docs/SECURITY.md`,
  `CHANGELOG.md`, `systemctl status` и истории git. `AI_ONBOARDING.md`
  даёт за одно чтение полную карту: где источник правды, что уже
  закрыто, что отложено и почему, какой первый шаг сделать.
- **Когда обновлять:** при значимом изменении стека, ветки `main` HEAD,
  hardening-статуса, coverage baseline или roadmap. Источник правды по
  бизнес-логике остаётся `SPEC.md`; AI_ONBOARDING — навигационная карта.

### Added — Operations runbook + SECURITY §4 hardening (PR docs/ops-hardening-and-deploy)
- **`docs/OPERATIONS.md`** (новый, 134 строки): операционный runbook,
  закрывает пробел между `BACKUP.md` (бэкапы БД) и `SECURITY.md` (политики).
  Разделы: §1 деплой systemd-юнитов (source of truth, `deploy_systemd.sh`,
  откаты), §2 health checks (is-active, ss/webhook, journalctl-фильтр на
  EPERM/denied, `systemd-analyze security`, OOM-приоритет), §3 карта
  артефактов на диске (код, venv, БД, логи, бэкапы L1/L2/L3).
- **`docs/SECURITY.md` §4 «Runtime hardening (systemd)»**: метрика
  9.2 UNSAFE → 1.3 OK, разбор по фазам (FS isolation, kernel/namespaces,
  syscall filtering), почему `MemoryDenyWriteExecute=yes` НЕ включён
  (ломает C-расширения Pillow/openpyxl/aiosqlite — вернёмся когда в CI
  будет smoke-test полного цикла), регламент проверки и отката.
- **`SPEC.md`**: три точечных правки —
  (1) шапка: строка про `docs/OPERATIONS.md` рядом с `BACKUP.md`;
  (2) §16 «Файлы проекта»: добавлены `docs/{SECURITY,BACKUP,OPERATIONS}.md`,
  `CONTRIBUTING.md`, `CHANGELOG.md`, юниты systemd и `deploy_systemd.sh`,
  которых раньше в списке не было;
  (3) §17 «Запуск / диагностика»: врезка-указатель на канонический
  `docs/OPERATIONS.md`, секция оставлена для быстрых однострочников.
- **Rationale документации:** PR #61 задеплоил инфраструктуру (юнит,
  drop-ins, скрипт), но операционная сторона жила в голове. Этот PR
  фиксирует «как этим пользоваться» письменно, чтобы deploy/откат/health
  можно было выполнить по runbook без AI-ассистента.

### Added — systemd hardening для smoktolk-bot.service (PR #61, feat/ops-harden-bot-service)
- **`systemd/smoktolk-bot.service`** (новый, мастер-копия): полный юнит
  основного процесса бота с 3-фазным runtime hardening.
  Score `systemd-analyze security`: **9.2 UNSAFE → 1.3 OK**.
  - Phase 1 (FS isolation): `NoNewPrivileges`, `PrivateTmp`,
    `ProtectSystem=strict`, `ProtectHome=yes`, `ReadWritePaths=` только
    `data/` и `logs/`, `UMask=0027`.
  - Phase 2 (kernel/namespaces): `ProtectKernel{Tunables,Modules,Logs}`,
    `ProtectControlGroups`, `ProtectClock`, `ProtectHostname`,
    `ProtectProc=invisible`, `RestrictNamespaces`, `RestrictSUIDSGID`,
    `RestrictRealtime`, `LockPersonality`, `PrivateDevices`,
    `RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6`,
    `CapabilityBoundingSet=` (пусто), `AmbientCapabilities=` (пусто).
  - Phase 3 (syscall filter): `SystemCallFilter=@system-service` +
    deny `@privileged @resources @debug @cpu-emulation @obsolete`,
    `SystemCallErrorNumber=EPERM` (errno вместо SIGSYS для лучшей
    диагностики и graceful degradation), `SystemCallArchitectures=native`.
- **`systemd/smoktolk-bot.service.d/20-resources.conf`** (новый):
  drop-in лимитов ресурсов — `MemoryHigh=400M`, `MemoryMax=512M`
  (текущий baseline RSS ≈ 280M, потолок с 80% запасом), `TasksMax=50`,
  `OOMScoreAdjust=-500` (бот выживает раньше других процессов при OOM).
- **`scripts/deploy_systemd.sh`** (новый, 163 строки, exec): идемпотентный
  деплой unit-файлов из репо в `/etc/systemd/system/`. Возможности:
  `--dry-run` (показывает `diff -u`), timestamped-бэкапы в
  `/var/backups/smoktolk-systemd/YYYYMMDD-HHMMSS/`, `--restart <unit>` с
  автоматическим rollback при `is-active=failed` через 3 сек, печать
  команды ручного отката. Запускается под `root` (sudo).
- **Верификация на проде** (после деплоя):
  `systemctl is-active smoktolk-bot.service` → active, RSS стабильный
  280M, webhook на `127.0.0.1:8080` слушает, polling зелёный, в журнале
  нет EPERM/seccomp denied, security score 1.3 OK.
- **Что НЕ включено** (с обоснованием):
  - `MemoryDenyWriteExecute=yes` — ломает Pillow/openpyxl/aiosqlite
    (мапят W+X страницы для C-расширений). Вернёмся когда в CI появится
    smoke-test полного цикла (загрузка xlsx-каталога, работа с БД).

### Added — Coverage report: pytest-cov + badge (PR chore/pytest-cov-and-badge)
- **`.coveragerc`**: конфигурация coverage.py. `branch = True` для точности
  (учитывает оба ветвления if/else). Исключает `venv/`, `tests/`,
  `make_sample_catalog.py` (одноразовая утилита). `exclude_lines` для
  декораторов вроде `if TYPE_CHECKING:` и `def __repr__`. Отчёты: term-missing
  (CI), HTML (`htmlcov/`, локально), XML (`coverage.xml`, artifact).
- **`requirements-dev.txt`**: добавлен `pytest-cov==7.1.0` (точная фиксация
  как у остальных зависимостей).
- **`.github/workflows/ci.yml`** — job `tests`: шаг `Run pytest` заменён на
  `Run pytest with coverage` с флагами `--cov=. --cov-config=.coveragerc
  --cov-fail-under=10`. Порог 10% выбран как baseline текущего покрытия
  (минус 1 п.п. для устойчивости к флакам). Добавлены два artifact-upload
  шага: HTML и XML отчёты с `if: always()`, чтобы отчёт сохранялся даже при
  падении тестов. Retention 14 дней. `actions/upload-artifact` запинен к
  SHA `65c4c4a1` (v4) — согласно security policy CI (см. `docs/SECURITY.md`).
- **`.gitignore`**: добавлен `coverage.xml` (рядом с уже существующими
  `.coverage` и `htmlcov/`) — XML-отчёт не должен попадать в git.
- **`README.md`**:
  - coverage-badge `coverage-11%-red` (shields.io, статичный — обновляется
    вручную при значимом росте; миграция на Codecov — отдельный PR при
    необходимости);
  - новая секция «## Тестирование» с командами запуска, текущим покрытием
    по модулям, описанием CI-policy (`--cov-fail-under`).
- **`SPEC.md` §20**: пункт «pytest-cov + coverage-бейдж» помечен как
  выполненный, пункт в DoD-чек-листе §28 закрыт.

**Текущее покрытие (baseline):** 11.36% общего, 261/2129 строк продакшн-кода.
Прицельно протестировано: `config.py` 97%, `services/admin_notify.py` 91%,
`db.py` 43%. Не покрыты (0%): все `handlers/*`, `webhook.py`, `tasks.py`,
`keyboards.py`, `utils.py`, `bot.py`, `catalog.py`, `crash_alert.py`. Это
honest baseline, не цель — рост покрытия handlers будет отдельными PR.


### Added — Issue templates: bug report, feature request, config (PR feature/issue-templates)
- **`.github/ISSUE_TEMPLATE/bug_report.md`**: структурированный шаблон для
  bug reports. Секции: описание, шаги воспроизведения, ожидаемое/фактическое
  поведение, окружение (где воспроизводится, версия бота, Python, OS),
  логи/скриншоты (в `<details>` для компактности), чек-лист контрибьютора.
  Labels: `bug`, `needs-triage`. Напоминание о security-related багах с
  редиректом в private security advisory (см. `docs/SECURITY.md` §«Как
  сообщить об уязвимости»).
- **`.github/ISSUE_TEMPLATE/feature_request.md`**: шаблон для feature
  requests. Секции: проблема (Why), предложенное решение (What),
  альтернативы (Considered), влияние на проект (SPEC/README/тесты/миграции),
  готовность контрибьютора реализовать, дополнительный контекст. Labels:
  `enhancement`, `needs-discussion`. Явно отсылает к SPEC.md §20 (roadmap)
  как к источнику истины по приоритизации.
- **`.github/ISSUE_TEMPLATE/config.yml`**: настройки issue chooser GitHub.
  `blank_issues_enabled: false` — нельзя создать issue без шаблона, что
  снижает количество низкокачественных обращений. Контактные ссылки:
  Security advisory (`/security/advisories/new`), Discussions (если включены
  в будущем), документация (`docs/`).
- **`CONTRIBUTING.md`**: разделы «🐛 Сообщить о баге» и «✨ Предложить
  feature» дополнены прямыми ссылками на соответствующие issue templates,
  чтобы новый контрибьютор сразу попадал в правильный шаблон.

### Changed
- **chore(lint):** очищены ruff-ошибки `F401` (5 unused imports в `tests/`) и `E402` (7 module-level imports в `handlers/_admin_addon.py` и `handlers/start.py`). Импорты перенесены в начало файлов согласно PEP 8.


### Added — CONTRIBUTING.md: гайд для контрибьюторов (PR feature/contributing-guide)
- **Новый документ `CONTRIBUTING.md`** в корне репозитория — единая точка
  входа для внешних контрибьюторов и нового онбординга:
  - Code of Conduct и принципы коммуникации в проекте.
  - Способы внести вклад: bug reports, feature requests, документация, код.
  - Полный setup окружения разработчика (Python 3.11, venv, gitleaks,
    git hooks через `scripts/setup-hooks.sh`).
  - Workflow разработки: fork → feature branch → PR → squash-merge.
  - Стиль кода (ruff, PEP 8) и Conventional Commits с примерами.
  - Quality gates: что проверяет pre-commit, pre-push, CI (5 джобов).
  - Pull request lifecycle: чек-лист, review process, рекомендации по
    размеру PR.
  - Матрица соответствия «изменение → какой документ обновить».
  - Security guidelines: что нельзя коммитить, что делать при утечке.
  - Полезные ссылки на ключевые документы проекта и внешние стандарты.
- `.github/pull_request_template.md`: добавлен заголовок-напоминание для
  новых контрибьюторов со ссылкой на `CONTRIBUTING.md`.
- `docs/SECURITY.md`: добавлена секция «См. также» с обратной ссылкой на
  `CONTRIBUTING.md`.
- `scripts/setup-hooks.sh`: финальное сообщение установщика теперь
  указывает на `CONTRIBUTING.md` как на полный гайд по дальнейшим шагам.
- `README.md`: раздел «Документация» дополнен ссылками на `CONTRIBUTING.md`,
  `docs/SECURITY.md`, `docs/BACKUP.md`; раздел «Структура» дополнен путём
  `CONTRIBUTING.md`.

### Added — Локальные quality-hooks: ruff в pre-commit + ADR по security posture (PR feature/local-quality-hooks)
- `scripts/git-hooks/pre-commit`: добавлена проверка staged `*.py` через
  `venv/bin/ruff check` (fallback на системный `ruff`) с теми же `--exclude`,
  что и CI. gitleaks-проверка сохранена; обе работают в одном hook'е, итог —
  единый `EXIT_CODE`. Без `--fix` (намеренно: коммит ничего не правит сам).
- `scripts/setup-hooks.sh`: установщик теперь проверяет наличие `ruff`
  (`venv/bin/ruff` или PATH) дополнительно к `gitleaks`. Отсутствие → варнинг
  и `exit 0` (hooks ставятся, но не сработают пока утилита не установлена).
- **Новый документ `docs/SECURITY.md`** — каноничное место для security
  posture: ADR «почему не платим GitHub Team», состав и митигации локальных
  hooks, принимаемые остаточные риски, триггеры пересмотра тарифа.
- README.md: раздел «Безопасность» теперь упоминает ruff в pre-commit и
  ссылается на `docs/SECURITY.md` как источник истины; раздел «Структура»
  дополнен путём `docs/SECURITY.md`.
- SPEC.md §21.8 переименован в «Локальные quality-hooks (pre-commit +
  pre-push)», добавлен подраздел «Состав hooks» и ссылка на `docs/SECURITY.md`.

### Fixed — L1 healthcheck: false-positive после safety-net (PR #ops-healthcheck-safety-net)
- `scripts/backup_healthcheck.sh`: порог `MAX_AGE_HOURS` поднят с **36 → 192 часа**
  (= `SAFETY_NET_DAYS=7 × 24 + 24ч запаса`).
- **Причина**: `backup.sh` валидно пропускает создание файла, если БД не
  менялась (до 7 дней подряд, далее safety-net). Healthcheck с порогом 36 ч
  ловил это как failure и слал ложные алерты `backup-failed` админу — что
  и произошло в production 16 мая 2026.
- **Проверка**: на 7-й день безделия `backup.sh` принудительно сделает
  safety-net бэкап, файл обновится, healthcheck увидит свежий файл и OK.
  Если даже safety-net не отработал (192ч без файла) — это реальный сбой
  (выключенный таймер, упавший systemd, размонтированный диск).
- Добавлен `tests/test_backup_healthcheck_sh.py` (8 кейсов: happy-path,
  граничные значения 191/193 ч, safety-net окно 120 ч, отсутствие/пустота
  каталога, игнор посторонних файлов, выбор свежего из нескольких).

---

## [0.4.0] — 2026-05-16

### Added — L2: Offsite-бэкап БД на Яндекс.Диск (PR #ops-offsite-yandex-disk)
- **Вторая копия БД на Я.Диске** через `rclone`. Защищает от
  потери всего VPS (хостер, диск, `rm -rf`, ransomware) — сценариев, которые
  не покрываются локальным бэкапом из §15.7.
- **Расписание**: `smoktolk-backup-offsite.timer` в 02:50 MSK (23:50 UTC),
  через ~5 мин после локального бэкапа §15.7 (04:00 MSK). Healthcheck в
  11:00 MSK (08:00 UTC) — проверяет, что `yandex_native:smoktolk-backup/smoktolk-latest.db.gz`
  существует и младше `MAX_AGE_HOURS=30`. Все таймеры в `OnCalendar=` заданы
  в UTC, чтобы не зависеть от DST/TZ хоста.
- **Загружаются 2 файла**:
  - `smoktolk_YYYYMMDD_HHMMSS.db.gz` — история, retention 30 дней.
  - `smoktolk-latest.db.gz` — фиксированное имя для быстрого DR.
- **Telegram-алерты** (зеркало §15.7): `offsite-failed` / `offsite-recovered`
  через `notify_admin.sh`, state-файл `/var/lib/smoktolk-backup/offsite-failed`
  для анти-дубликата.
- Новые файлы:
  - `scripts/backup_offsite.sh`, `scripts/backup_offsite_healthcheck.sh`
  - `systemd/smoktolk-backup-offsite.{service,timer}`
  - `systemd/smoktolk-backup-offsite-alert.service`
  - `systemd/smoktolk-backup-offsite-healthcheck.{service,timer}`
  - `tests/test_backup_offsite_sh.py` (16 кейсов: gzip, retention, idempotency,
    rclone-фейлы, race-condition при одновременных запусках)
  - `tests/test_backup_offsite_healthcheck_sh.py` (10 кейсов: границы возраста,
    mtime в будущем, нечитаемый rclone-конфиг, отсутствие rclone в PATH)
- Изменён `scripts/notify_admin.sh`: добавлены события `offsite-failed` и
  `offsite-recovered` (общий помощник `ensure_backup_state_dir`).

### Added — L3: Полный offsite-архив проекта (PR #ops-offsite-full-tar)
- **Третий уровень бэкапа**: полный архив `/opt/smoktolk/` (~100 МБ) на
  Я.Диск. Защищает не только БД (как L2), но и код, конфиги, ассеты —
  на случай, если git-репозиторий пропадёт вместе с VPS или последний коммит
  не успели запушить.
- **Расписание**: `smoktolk-backup-full-offsite.timer` в 02:30 MSK (23:30 UTC),
  до L2 (23:50 UTC) чтобы не пересекаться по сети. Healthcheck в 09:00 MSK
  (06:00 UTC), `MAX_AGE_HOURS=30`.
- **Архивация**: `tar.gz` уровня 6 (баланс CPU/размер), исключения
  `venv/`, `__pycache__/`, `.pytest_cache/`, `*.pyc`, `.git/objects/pack/`,
  `*.log`. Загружаются 2 файла: `smoktolk-full_YYYYMMDD_HHMMSS.tar.gz`
  (история, retention 30 дней) и `smoktolk-full-latest.tar.gz` (DR-копия
  через server-side `rclone copyto` — экономит 50% трафика).
- **Telegram-алерты**: `full-offsite-failed` / `full-offsite-recovered`,
  state-файл `/var/lib/smoktolk-backup/full-offsite-failed`.
- Новые файлы:
  - `scripts/backup_full_offsite.sh`, `scripts/backup_full_offsite_healthcheck.sh`
  - `systemd/smoktolk-backup-full-offsite.{service,timer}`
  - `systemd/smoktolk-backup-full-offsite-alert.service`
  - `systemd/smoktolk-backup-full-offsite-healthcheck.{service,timer}`

### Changed — Переход с WebDAV на native Yandex.Disk API (PR #ops-offsite-native-api)
- L2 (БД) и L3 (полный архив) переведены с rclone backend `webdav`
  (https://webdav.yandex.ru/) на native backend `yandex` (через OAuth-токен).
  **Причина**: WebDAV-эндпоинт Я.Диска троттлится на ~70 КБ/с независимо от
  `--bwlimit`/`--transfers`/времени суток. Для L2 (3-4 КБ) это незаметно,
  но для L3 (100 МБ) заливка занимала ~25 минут и натыкалась на
  `TimeoutStartSec=`. После перехода на native API — заливка 100 МБ за
  ~50 секунд (улучшение в ~30 раз).
- Основной remote в `/var/lib/smoktolk-rclone/rclone.conf` теперь
  `yandex_native:` (backend `yandex`, OAuth-токен через `rclone config`
  browser-flow). Legacy WebDAV-remote `yandex:` оставлен как backup-вариант.
- Все скрипты (`backup_offsite.sh`, `backup_full_offsite.sh`,
  `backup_offsite_healthcheck.sh`, `backup_full_offsite_healthcheck.sh`)
  и тесты обновлены под `yandex_native:`.

### Docs
- `docs/BACKUP.md` — раздел "Offsite-бэкап на Я.Диск" (L2) обновлён под
  native API; добавлен раздел "L3 Offsite-бэкап: полный архив проекта"
  с DR-процедурой.
- `SPEC.md` §15.8 переписан под native API; добавлен §15.9 про L3 +
  историю перехода с WebDAV; таблица уровней бэкапа L1/L2/L3.

---

## [0.3.0] — 2026-05-14

### Added
- **Healthcheck-таймер бэкапов** (`smoktolk-backup-healthcheck.timer` в 10:00 MSK):
  проверяет, что в `/var/backups/smoktolk/` есть файл младше 36 часов;
  если нет — шлёт алерт через `notify_admin.sh backup-failed`. Защищает от
  сценария "timer не сработал вообще" (юнит выключен, диск размонтирован),
  который не покрывается существующим `OnFailure=`. Скрипт:
  `scripts/backup_healthcheck.sh`, юниты: `systemd/smoktolk-backup-healthcheck.{service,timer}`.
- **DR-drill процедура** в `docs/BACKUP.md` + первая запись в журнале
  учений (2026-05-14, integrity_check=ok, схема совпадает с prod).
- **systemd timer для бэкапа БД** (`smoktolk-backup.timer` + `smoktolk-backup.service`):
  замена cron-задаче, единый канал логов в journal, `Persistent=true` для догона
  пропущенных запусков, `RandomizedDelaySec=2min` для разнесения нагрузки.
- **Telegram-алерты бэкапа** — двухуровневые, по аналогии с DOWN/RECOVERED для
  основного бота:
  - 🚨 `backup-failed` — отправляется при первом сбое (из `trap ERR` в `backup.sh`
    или из `OnFailure=smoktolk-backup-alert.service`).
  - ✅ `backup-recovered` — отправляется при первом успешном запуске после сбоя.
- **State-файл** `/var/lib/smoktolk-backup/failed` (через `StateDirectory=` в юните)
  для защиты от дубликатов алертов — повторные FAILED заблокированы, пока
  не пройдёт успешный бэкап.
- Мастер-копии юнитов в репо: `systemd/smoktolk-backup.service`,
  `systemd/smoktolk-backup.timer`, `systemd/smoktolk-backup-alert.service`.

- **Ops/Backups**: переписан `backup.sh` — атомарный снимок SQLite через `sqlite3 .backup`,
  hash-дедупликация по `sha256(sqlite3 .dump)`, retention по возрасту (150 дней) и размеру (5 GiB),
  safety-net (контрольная копия раз в 7 дней даже без изменений), lock через `flock -n`,
  ENV-override всех путей для тестов (`BOT_DIR`, `DB_PATH`, `BACKUP_DIR`, `RETENTION_DAYS`,
  `MAX_TOTAL_BYTES`, `SAFETY_NET_DAYS`, `LOCK_FILE`). Бэкапы переехали из
  `/opt/smoktolk/bot/backups/` в `/var/backups/smoktolk/` (вне директории приложения).
  Добавлен operations-док `docs/BACKUP.md` (что бэкапим, восстановление, мониторинг)
  и 8 интеграционных тестов `tests/test_backup_sh.py` через `subprocess.run` —
  без зависимости от bats. SPEC §15 полностью переписан.
- **Admin notify**: push админу при каждой новой регистрации пользователя.
  Сообщение: имя, @username, user_id, реферер (если есть). Реализовано через
  новый модуль `services/admin_notify.py` (fire-and-forget, асинхронно,
  не блокирует регистрацию). HTML-escape для защиты от инъекций.
  Покрыто 9 unit-тестами (форматтеры, mock bot.send_message, обработка
  TelegramAPIError).
- **UX**: единое welcome-сообщение для нового пользователя — фото-вывеска SMOKTOLK + текст дисклеймера в одном сообщении (вместо двух раздельных). См. `handlers/start._send_welcome_disclaimer`.
- **UX**: раздел «🏬 Магазины» (бывш. «📍 Адрес и часы работы») доступен ДО принятия правил — кнопка на экране дисклеймера. Возврат — на тот же экран.
- **UX**: в главном меню новая раскладка кнопок — layout `adjust(2,2,2,2,1,1)` (детали см. в `### Changed`).
- **Admin**: кнопка «🎂 Изменить ДР» в карточке пользователя. Позволяет админу
установить/перезаписать дату рождения юзера (`db.set_birthday(..., force=True)`).
Формат ввода: `ДД.ММ.ГГГГ`. См. `handlers/_admin_addon.AdmBday` FSM.
- **Address**: единый стиль кнопки возврата «« Назад» в разделе «Магазины»
(было «◀️ В меню»).

### Changed
- `scripts/notify_admin.sh` — поддерживает новые reason'ы `backup-failed`
  и `backup-recovered`, state-каталог теперь параметризуется в зависимости
  от reason (для `down`/`up` — `/run/smoktolk-bot/`, для `backup-*` —
  `/var/lib/smoktolk-backup/`).
- `backup.sh` — добавлен `trap ERR` с вызовом `notify_admin.sh backup-failed`
  и финальный вызов `notify_admin.sh backup-recovered` при успехе.
- `docs/BACKUP.md` — раздел `## Cron` заменён на `## Расписание (systemd timer)`,
  добавлены разделы «Алерты в Telegram» и «Что делать при FAILED-алерте».

- `handlers/address.py`: переписан, теперь определяет контекст (из дисклеймера
vs из главного меню) по полю `user.rules_accepted_at` и подставляет
правильный callback возврата (`back_to_rules` или `back_main`).
- `keyboards.kb_main`: layout `adjust(2,2,2,2,1,1)` вместо старого
`(2,2,2,1,1,1,1)`.
- `keyboards.kb_accept_rules`: добавлена 3-я кнопка «🏬 Магазины».
- `keyboards.kb_admin_user_card`: добавлена строка с кнопкой «🎂 Изменить ДР»,
layout `adjust(2,1,1,1,1)`.

### Removed
- Cron-запись `0 4 * * * /opt/smoktolk/bot/backup.sh ...` у пользователя `smoktolk`
  (мигрировано в `smoktolk-backup.timer`).

### Verified
| Сценарий | Результат |
|----------|-----------|
| Новый юзер: `/start` → welcome+дисклеймер одним сообщением | ✅ |
| Тап «🏬 Магазины» из дисклеймера → адрес → «« Назад» → возврат на дисклеймер | ✅ |
| Тап «✅ Принимаю правила» → главное меню с новой раскладкой | ✅ |
| Главное меню «🏬 Магазины» → адрес → «« Назад» → главное меню | ✅ |
| Админ → карточка юзера → «🎂 Изменить ДР» → ввод `15.03.1990` → сохранено как `1990-03-15` | ✅ |
| `pytest` | ✅ 53/53 |
| `_send_welcome_disclaimer` существует и шлёт одно сообщение с фото+caption | ✅ |

### Technical debt closed
- ~~Стартовая последовательность присылала баннер и дисклеймер двумя отдельными
сообщениями~~ — теперь одно сообщение.
- ~~Админ не мог исправить ошибочно введённую юзером ДР~~ — теперь может через
карточку пользователя.

### Notes
- Тесты пройдены вручную (happy path / failed / repeated failed / recovered),
  алерты в TG приходят ровно по одному разу на событие.

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
