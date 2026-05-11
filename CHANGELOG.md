# Changelog

Все значимые изменения проекта документируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), проект следует [Semantic Versioning](https://semver.org/lang/ru/).

---


## [Unreleased]

### Security

- Настроен **Dependabot** для еженедельного автообновления зависимостей (`pip`, `github-actions`)
- Установлен **gitleaks** как pre-commit hook — блокирует коммиты с секретами (Telegram-токены, GitHub PAT, AWS keys и др.)
- Добавлен установщик git-hooks (`scripts/setup-hooks.sh`) для автоматизации настройки у новых разработчиков

### Changed

- Обновлён **aiogram**: `3.13.1` → `3.28.2` (через Dependabot PR #1 с ручным review)
- Политика версионирования: переход от «фиксируем точно» к «контролируемые апгрейды через Dependabot»
- **SPEC обновлён до v1.2**: актуализирована версия aiogram, зафиксирована новая политика обновлений зависимостей

### Added

- `CHANGELOG.md` — история изменений в формате Keep a Changelog
- `README.md`: блок «Документация» со ссылками на SPEC.md и CHANGELOG.md
- `.gitignore`: правило `*.bak-*` для исключения timestamped-бекапов
## [Unreleased]

### Added

- `CHANGELOG.md` — история изменений в формате Keep a Changelog
- `README.md`: блок «Документация» со ссылками на SPEC.md и CHANGELOG.md
- `.gitignore`: правило `*.bak-*` для исключения timestamped-бекапов
- **SPEC раздел 17 расширен** (PR #12): подразделы 17.1 «Проверка синтаксиса Python-файлов через ast.parse», 17.2 «Корректный путь к БД SQLite (data/smoktolk.db)», 17.3 «Где искать что — быстрая шпаргалка», явное упоминание `logs/bot.log` как основного лога приложения
- **SPEC раздел 21** — секция про GitHub CLI / gh PR workflow (PR #10)
- **SPEC раздел 23** — история инцидентов с AI-ассистентом:
  - 23.6 — `gh pr view` падает на устаревшем GraphQL-поле `projectCards`
  - 23.7 — рецидив heredoc-инцидента №2 (LESSONS_LEARNED.md)
  - 23.8 — рецидив heredoc-инцидента №3 (`python3 << EOF`, `cat << EOF` с markdown)

### Changed

- Обновлён **aiogram**: `3.13.1` → `3.28.2` (через Dependabot PR #1 с ручным review)
- Политика версионирования: переход от «фиксируем точно» к «контролируемые апгрейды через Dependabot»
- **SPEC обновлён до v1.2**: актуализирована версия aiogram, зафиксирована новая политика обновлений зависимостей
- Правило 24.2 SPEC расширено: heredoc запрещён для `python3 << EOF`, `cat > file << EOF`, `bash << EOF` с многострочным содержимым

### Fixed

- **PR #9** `handlers/profile.py`: исправлена сигнатура вызова `create_redemption()` — была причина падения QR списания баллов. Теперь QR списания и QR подарков работают штатно (проверено в продакшне)

### Security

- Настроен **Dependabot** для еженедельного автообновления зависимостей (`pip`, `github-actions`)
- Установлен **gitleaks** как pre-commit hook — блокирует коммиты с секретами (Telegram-токены, GitHub PAT, AWS keys и др.)
- Добавлен установщик git-hooks (`scripts/setup-hooks.sh`) для автоматизации настройки у новых разработчиков
- Удалён небезопасный разовый бэкап `backups/env_bak_20260509.tar.gz` (содержал `.env` с боевыми токенами при странных правах `0620`); процедура бэкапа `.env` пересмотрена — разовые архивы с секретами больше не создаются вручную

### Housekeeping

- Удалены устаревшие локальные бэкапы SPEC.md (`SPEC.md.bak.*`)
- Удалены разовые архивы из `backups/` (старше 30 часов и не от cron): `backup_20260509_1840.tar.gz`, `backup_before_addon_20260509_1813.tar.gz`, `catalog_20260509_174135.xlsx`, `smoktolk_20260509_174135.db`
- Удалены локальные `__pycache__/` каталоги (генерируются при запуске бота)
- Удалены смерженные локальные ветки: `docs/incidents-23.6-23.7`, `fix/create-redemption-signature`, `docs/spec-diagnostics-notes`, `docs/spec-incident-heredoc-recurrence`
- Очищены stale remote-ссылки (`git fetch --prune`)

---

## [0.1.0] — 2026-05-10

Первый baseline проекта: инфраструктура, конфигурация, документация. Бизнес-логика бота — в `app/`, реализована на момент initial snapshot.

### Added

- **Initial snapshot** бота SMOKTOLK с технической спецификацией **SPEC v1.1**
- Конфигурация **Dependabot** (`.github/dependabot.yml`): еженедельное автообновление Python-зависимостей (`pip`), ежемесячное обновление GitHub Actions
- **Gitleaks pre-commit hook** + установщик `scripts/setup-hooks.sh`
- **README.md** с инструкциями для разработчика (установка, запуск, структура проекта)

### Security

- Pre-commit сканирование секретов через **gitleaks** — защита от случайного коммита токенов
- Автоматический мониторинг уязвимостей в зависимостях через **Dependabot**

### Notes

- Данная версия фиксирует **инфраструктурный baseline** перед началом активной работы над фичами
- На момент `0.1.0` открыты 4 Dependabot-PR (pillow, pytz, qrcode, python-minor-patch group) — будут обработаны в следующих релизах

---

## Категории изменений

- **Added** — новая функциональность
- **Changed** — изменения в существующей функциональности
- **Deprecated** — функциональность, которая будет удалена
- **Removed** — удалённая функциональность
- **Fixed** — исправления багов
- **Security** — улучшения безопасности и обновления уязвимых зависимостей
