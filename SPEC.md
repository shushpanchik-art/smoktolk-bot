# SMOKTOLK Bot — Техническая спецификация v1.1

**Дата:** 2026-05-09  
**Предыдущая версия:** v1.0 (2026-05-08), сохранена в `SPEC.md.v1.0.bak`  
**Админ:** @utc2000 (Telegram ID: **5899721537**)  
**Бот:** @SMOKTOLK_bot (ID: 8400165268)  
**Сервер:** telegram-bot (Debian 12, Python 3.11.2), путь **`/opt/smoktolk/bot/`**  
**Сервис:** `smoktolk-bot.service` (systemd, enabled, user `smoktolk`)  
**Логи бота:** `/opt/smoktolk/bot/logs/bot.log` + `journalctl -u smoktolk-bot`  
**Бэкапы:** cron от `smoktolk` → `/opt/smoktolk/bot/backups/` (лог `logs/backup.log`)

## Изменения относительно v1.0
- Telegram ID админа исправлен: `1492067664` → **`5899721537`**.
- В разделе 14 зафиксирован реальный путь cron-задачи и пользователь.
- Раздел 17 (схема БД) приведён в соответствие с фактической схемой SQLite — добавлены колонки, которых не было в v1.0: `age_verified_at`, `age_verified_by`, `gosuslugi_verified`, `purchases_count_500`, `last_purchase_date`, `referrer_id`, `referral_reward_paid`, `rules_accepted_at`, `notifications_enabled`.
- Зафиксирован реальный список таблиц БД (8 шт.).

---

## 1. Назначение
Telegram-бот программы лояльности офлайн-магазина SMOKTOLK. Начисляет кэшбэк
по чекам с кассы, ведёт многоуровневую систему рангов, выдаёт подарки за 1₽,
считает рефералов. Дистанционной продажи нет.

## 2. Стек (зафиксированные версии)
- **Python 3.11.2** (системный, Debian 12)
- **aiogram 3.13.1** ← API менялся между 3.x минорами, фиксируем точно
- aiohttp 3.10.10, aiosqlite 0.20.0, openpyxl 3.1.5
- qrcode 7.4.2, Pillow 10.4.0, pydantic 2.9.2, python-dotenv 1.0.1
- SQLite (`/opt/smoktolk/bot/data/smoktolk.db`)
- systemd + cron-бэкап (см. раздел 14)

Полный список — `requirements.txt`. Venv: `/opt/smoktolk/bot/venv/`.

## 3. Архитектура
Один процесс, запускается systemd:
- aiogram **polling** (long-poll к Telegram API)
- aiohttp **web-server** на 127.0.0.1:8080 (вебхуки от кассы)
- фоновый `daily_loop` (рассылки, сгорания, отчёты)

Все три сосуществуют в одном event-loop, точка входа — `bot.py`.

## 4. Уровни лояльности (бизнес-логика — НЕ менять)

| L | Название | Кэшбэк база | Условия | Окно повтора | Подарок 1₽ |
|---|----------|-------------|---------|--------------|------------|
| 1 | Исследователь | 10% | по умолчанию | 3–5 дн., +3% | — |
| 2 | Знаток | 11% | возврат подтверждён | 3–8 дн., +5% | — |
| 3 | Мастер пара | 12% | возраст + (1500 lp ИЛИ 15 чеков ≥500₽) | 3–12 дн., +7% | раз в 60 дн. |
| 4 | Профи | 13% | возраст + (4000 lp ИЛИ 40 чеков) | 3–15 дн., +10% | раз в 30 дн. + 15% на аксессуары |
| 5 | Легенда | 15% | возраст + (8000 lp ИЛИ 80 чеков) | 3–15 дн., +12% | раз в 30 дн. + бесплатная доставка |

## 5. Бонусы
- **Repeat-bonus**: если 3 ≤ дни_от_последней_покупки ≤ окно_уровня → +X%.
- **Birthday**: +20 п.п. к кэшбэку в день рождения.
- **Сгорание**: 120 дней без покупок → обнуление баллов (через `daily_loop`).

## 6. Списание баллов
- 10 баллов = 1 ₽, минимум 200 баллов, максимум 30% чека.
- Только категории: `accessories, tools, cables, sweets`.
- Через QR-токен (UUID), TTL 15 мин.

## 7. Подарки за 1₽
- Список из Excel (лист `gifts`).
- Доступны от уровня + cooldown по уровню.
- QR-токен + 6-значный резервный код.

## 8. Реферальная программа
- Ссылка: `t.me/SMOKTOLK_bot?start=ref_<6chars>`
- Награда (300/200 баллов) после: регистрация → возраст → первая покупка ≥500₽.

## 9. Webhook от кассы
- Прослушка: 127.0.0.1:8080
- Эндпоинты: `POST /webhook/purchase`, `/webhook/redeem`, `/webhook/redeem_gift`
- Заголовок: `X-API-Token: <WEBHOOK_TOKEN>` (в `.env`, установлен)
- Режим: `WEBHOOK_MODE=stub` (текущий) | `live`
- Реализация: `webhook.py`

## 10. Ассортимент
- Excel на Я.Диске: `https://disk.yandex.ru/i/jlz-VbSdVaUbTQ`
- Листы: `products`, `gifts`
- Кэш: `data/catalog.xlsx`, обновление раз в час или кнопкой админа.
- Парсер: `catalog.py`. Заголовок на 2-й строке, cols: num=1, name=11, price=56, stock=53, rec=70.
- Факт: **143 товара**.

## 11. Админ-панель (только для ID 5899721537)
- 📊 Статистика
- 👥 Пользователи
- ✅ Заявки на верификацию (18+)
- 🎁 Подарки
- 📡 Рассылка
- **📤 Экспорт в CSV** — добавлен 2026-05-09 (raz_61)
- 🔄 Обновить каталог
- 🧪 Тест webhook (для отладки stub)

## 12. Верификация 18+
- Юзер жмёт «Подтвердить возраст», бот отправляет заявку админу.
- Заявка хранится в `verification_requests`.
- Админ нажимает «Подтвердить» / «Отклонить» в чате.
- При подтверждении: `users.age_verified=1`, `age_verified_at=now`, `age_verified_by=admin_id`.
- Поле `gosuslugi_verified` зарезервировано на будущее (интеграция через ЕСИА), сейчас всегда 0.

## 13. Конфигурация (`.env`)
```
BOT_TOKEN=...
ADMIN_ID=5899721537
WEBHOOK_TOKEN=...
WEBHOOK_MODE=stub
DB_PATH=/opt/smoktolk/bot/data/smoktolk.db
CATALOG_URL=https://disk.yandex.ru/i/jlz-VbSdVaUbTQ
LOG_LEVEL=INFO
```

## 14. Бэкапы (cron)

**Активная задача** — crontab пользователя `smoktolk`:

```
0 4 * * * /opt/smoktolk/bot/backup.sh >> /opt/smoktolk/bot/logs/backup.log 2>&1
```


Скрипт `/opt/smoktolk/bot/backup.sh`:
- `sqlite3 .backup` (безопасно при работающем боте) → `backups/smoktolk_YYYYMMDD_HHMMSS.db`
- `cp catalog.xlsx` → `backups/catalog_YYYYMMDD_HHMMSS.xlsx`
- Хранит последние 30 копий каждого, старое удаляет.

История: ранее существовала битая cron-задача под `shushpanchik_art`
(`/home/shushpanchik_art/smoktolk_bot/backup.sh` — путь не существовал).
Удалена 2026-05-09.

Ручные tar-бэкапы перед изменениями: `/opt/smoktolk/backup_YYYYMMDD_HHMM.tar.gz`.


## 15. Файлы
```
bot.py, config.py, db.py, keyboards.py, utils.py, catalog.py,
webhook.py, tasks.py
handlers/{start,profile,gifts,catalog,referral,rules,verify,admin}.py
```


## 16. Запуск / диагностика
```bash
sudo systemctl status smoktolk-bot
sudo systemctl restart smoktolk-bot
sudo journalctl -u smoktolk-bot -f
sudo tail -f /opt/smoktolk/bot/logs/bot.log
sudo tail -f /opt/smoktolk/bot/logs/backup.log
```

## 17. Схема БД (актуальная, проверена 2026-05-09)

**Таблицы (8):** users, purchases, redemptions, gifts_log,
gift_cooldowns, history, verification_requests, daily_stats.

### users

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

Ключевые поля для бизнес-логики:

- level (1–5) — текущий ранг.
- points — текущий баланс баллов (расходуется при списании).
- lifetime_points — суммарно начислено за всё время (для перехода уровня).
- total_spent — сумма всех чеков в копейках (или рублях — уточнить в db.py).
- purchases_count — все чеки.
- purchases_count_500 — только чеки ≥500 ₽ (для условия L3).
- last_purchase_date — для repeat-bonus и сгорания.
- referrer_id + referral_reward_paid — рефералка.

### Прочие таблицы (краткое назначение)

- purchases — все чеки с кассы (приход через webhook).
- redemptions — все списания баллов (выпуск QR + факт списания).
- gifts_log — выданные подарки за 1₽.
- gift_cooldowns — таймеры кулдауна по уровням.
- history — лента событий пользователя для профиля.
- verification_requests — заявки 18+ в очереди к админу.
- daily_stats — агрегаты для админ-статистики.

Полные DDL остальных таблиц — см. db.py (функция инициализации) или
sqlite3 smoktolk.db ".schema".


## 18. Текущее состояние (2026-05-09)

- Сервис: запущен, polling активен.
- Пользователей в БД: 4 (тестовые + админ).
- Каталог: 143 товара, кэш на диске.
- Webhook: режим stub (контракт API готов, к live кассе не подключён).
- Бэкапы: работают, последний smoktolk_20260509_040002.db.

## 19. Технический долг / следующие шаги

- Подключить webhook кассы в live (после согласования API с интегратором).
- Реализовать gosuslugi_verified через ЕСИА (низкий приоритет).
- Уточнить единицы измерения total_spent (₽ vs копейки) — задокументировать.
- Покрыть тестами tasks.daily_loop (сгорание, рассылки, отчёты).
- Мониторинг: алерт в Telegram при падении сервиса.

