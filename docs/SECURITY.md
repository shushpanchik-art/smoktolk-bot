# Security & Quality posture

Документ описывает **архитектурные решения** по защите репозитория и кода,
а также **сознательно принятые риски** и их митигации.

---

## 1. Видимость репозитория и тариф GitHub

**Репозиторий:** приватный, на тарифе **GitHub Free**.

### Принятое решение

- ❌ **Не делаем репозиторий публичным** ради бесплатного доступа к
  server-side Branch Protection (для public-repo на Free тарифе оно доступно).
  Причина: код содержит бизнес-логику бота и потенциально чувствительные
  fixtures/тестовые данные; публичность увеличивает supply-chain поверхность
  (форки, скрейперы, ботнеты).
- ❌ **Не переходим на GitHub Team ($4/мес/пользователь)** ради server-side
  Branch Protection для приватных репо. Причина: для solo-проекта стоимость
  не оправдана при наличии равноценных локальных альтернатив.

### Митигация (как добиваемся аналогичной защиты бесплатно)

| Слой | Где работает | Что закрывает |
|---|---|---|
| `scripts/git-hooks/pre-push` | Локально на машине разработчика | Прямой `git push origin main` блокируется |
| `scripts/git-hooks/pre-commit` (gitleaks) | Локально | Секреты не попадают в коммит |
| `scripts/git-hooks/pre-commit` (ruff) | Локально | Линт-ошибки не попадают в коммит |
| GitHub Actions CI (`.github/workflows/ci.yml`) | Server-side | Ruff / Bandit / pytest гоняются на каждом PR |
| Dependabot | Server-side | CVE в зависимостях и Actions |
| Code Owners + Required reviewers через UI | Server-side | Невозможно — требует Team. **Принят риск.** |

### Принимаемые остаточные риски

1. **Прямой push в `main` возможен**:
   - с машины, где не установлен `scripts/git-hooks/pre-push` (новый клон без `./scripts/setup-hooks.sh`);
   - при явном `git push --no-verify`.
2. **CI не является блокирующим** — упавший CI не мешает физически смержить
   PR через UI. Митигация: дисциплина flow, ревью своих PR перед merge.
3. **Контрибьюторов с прямым доступом мало (1–2)** — социальный фактор риска низок.

### Триггеры для пересмотра решения

Переход на GitHub Team (или public + бесплатный Branch Protection)
рассматривается при наступлении **любого** из:

- появление третьего контрибьютора с правами на push;
- любой инцидент с попаданием секрета / поломкой `main` через прямой push;
- открытый коммерческий запуск проекта (любая монетизация → расходы $4/мес
  становятся нерелевантными в общем бюджете).

---

## 2. Локальные quality-hooks

Установка после `git clone`:

    ./scripts/setup-hooks.sh

Hooks хранятся в `scripts/git-hooks/` (под VCS) и копируются в `.git/hooks/`
(вне VCS). См. также `README.md`, раздел *Setup → Установи git-hooks*.

### Состав

- **`pre-commit`** — `gitleaks` (секреты) + `ruff` (линт staged `.py`).
  Сканируется именно **staged-версия** файлов (`git show :<file>`), а не
  рабочая копия — чтобы временные правки в WT не маскировали проблему.
- **`pre-push`** — блокирует `git push` в `refs/heads/main`, в том числе
  удаление ветки и push через нестандартный refspec.

Обход (только под персональную ответственность):

    git commit --no-verify
    git push   --no-verify

---

## 3. Reporting security issues

Если ты внешний исследователь и нашёл уязвимость — открой private security
advisory через GitHub UI (`Security` → `Report a vulnerability`) или напиши
владельцу репозитория в Telegram (контакт в профиле GitHub).

## 4. Runtime hardening (systemd)

Бот запускается под `smoktolk-bot.service` с включённым systemd-runtime
hardening. Цель — минимизировать blast radius в случае RCE-уязвимости в
зависимостях (aiogram, openpyxl, Pillow, requests и т.д.) или ошибки в
самом коде, обрабатывающем недоверенный ввод (Telegram-сообщения,
вебхук кассы, xlsx-каталог с Я.Диска).

### Метрика

`systemd-analyze security smoktolk-bot.service`:

| До | После |
|---|---|
| **9.2 UNSAFE** 😨 | **1.3 OK** 🙂 |

Единственная оставшаяся claim — `UMask=` (0.1 pt). У нас выставлено
`UMask=0027`, но анализатор считает строгим только `0077`. Для нашего
сценария group-readable нужен: бэкапы и логи читаются группой
`smoktolk`, в которую входят сервисные утилиты. Менять не планируется.

### Что включено

**Phase 1 — FS isolation:**

- `NoNewPrivileges=yes`
- `PrivateTmp=yes`
- `ProtectSystem=strict` — `/usr`, `/boot`, `/etc` только для чтения
- `ProtectHome=yes` — `/home`, `/root` невидимы
- `ReadWritePaths=/opt/smoktolk/bot/data /opt/smoktolk/bot/logs` —
  единственные точки записи
- `UMask=0027`

**Phase 2 — kernel & namespaces:**

- `ProtectKernelTunables=yes`, `ProtectKernelModules=yes`,
  `ProtectKernelLogs=yes`
- `ProtectControlGroups=yes`, `ProtectClock=yes`, `ProtectHostname=yes`
- `ProtectProc=invisible` — `/proc` чужих PIDs скрыт
- `RestrictNamespaces=yes`, `RestrictSUIDSGID=yes`, `RestrictRealtime=yes`
- `LockPersonality=yes`, `PrivateDevices=yes`
- `RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6` — нет AF_PACKET,
  AF_NETLINK и экзотики
- `CapabilityBoundingSet=` (пусто), `AmbientCapabilities=` (пусто) —
  процесс не наследует и не может приобрести ни одной capability

**Phase 3 — syscall filtering:**

- `SystemCallFilter=@system-service`, дополнительный deny
  `@privileged @resources @debug @cpu-emulation @obsolete`
- `SystemCallErrorNumber=EPERM` — запрещённый syscall возвращает errno,
  а не убивает процесс по SIGSYS (лучше для диагностики и graceful
  degradation)
- `SystemCallArchitectures=native`

### Что НЕ включено

- **`MemoryDenyWriteExecute=yes`** — ломает C-расширения Pillow,
  openpyxl, aiosqlite (они мапят страницы W+X для JIT/инициализации).
  Включим, когда в CI появится smoke-тест полного цикла загрузки
  xlsx-каталога и работы с БД.

### Где лежит юнит и как менять

Канон — в репозитории: `systemd/smoktolk-bot.service` и
`systemd/smoktolk-bot.service.d/`. Деплой только через
`scripts/deploy_systemd.sh` (см. [`OPERATIONS.md`](OPERATIONS.md) §1).
Любая правка проходит через PR.

### Как проверить после изменений

    sudo ./scripts/deploy_systemd.sh --dry-run
    sudo ./scripts/deploy_systemd.sh --restart smoktolk-bot.service
    systemd-analyze security smoktolk-bot.service | tail -3
    sudo journalctl -u smoktolk-bot.service --since "5 minutes ago" \
        | grep -iE 'eperm|denied|seccomp'   # должно быть пусто

Если score вырос выше 4.0 или в журнале появились EPERM — откат через
`/var/backups/smoktolk-systemd/`, точная команда печатается скриптом.

## См. также

- [CONTRIBUTING.md](../CONTRIBUTING.md) — общий гайд для контрибьюторов, включая setup hooks и workflow разработки.
