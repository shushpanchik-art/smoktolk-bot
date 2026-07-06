# ════════════════════════════════════════════════════════
#  ВВОДНОЕ ДЛЯ ИИ-АССИСТЕНТА — ПРОЕКТ SMOKTOLK
#  Прочитай ЭТО ПЕРВЫМ в начале сессии.
# ════════════════════════════════════════════════════════

## ЧТО ЗА ПРОЕКТ
Telegram-бот программы лояльности магазина SMOKTOLK (никотин/вейп-розница 18+).
Функции: онбординг с дисклеймером и правилами 18+, накопление баллов за покупки,
уровни (L1..Ln), подарки за уровень, реферальная система (приглашение друзей),
интеграция с кассой через вебхук (начисление баллов по чекам).
Бот НЕ интернет-магазин — только лояльность, покупки в офлайн-магазине.

## КАК РАБОТАЕМ / ДОСТУПЫ
- Пользователь = владелец бота, НЕ программист. Давать готовый код и пошаговые
  инструкции. Все решения принимать самому, стремиться к MVP.
- Работаем через терминал сервера (Warp на macOS у юзера).
- На сервер юзер уже залогинен; команды выполняются на сервере (Linux, systemd).
- sudo доступен (для systemctl/journalctl).
- Лимит: 25 запросов/час, 150/день -> ВЫДАВАТЬ МАКСИМУМ КОМАНД ЗА РАЗ
  (разведка + правки + проверки вместе). Команды дробить на отдельные bash-блоки.
- Большие вставки — через heredoc (nano в интерактиве неудобен в этом канале).
  Приоритет: правка файлов Python-скриптом с .replace() + assert anchor.
- base64 НЕ использовать.

## СРЕДА / ПУТИ
- Корень проекта:  /opt/smoktolk/bot
- Python ТОЛЬКО через venv:  venv/bin/python   (СИСТЕМНЫЙ python3 БЕЗ зависимостей!)
- systemd unit:  smoktolk-bot.service
    рестарт: sudo systemctl restart smoktolk-bot.service
    статус:  sudo systemctl is-active smoktolk-bot.service
    логи:    sudo journalctl -u smoktolk-bot.service -n 50 --no-pager
- ExecStart: venv/bin/python bot.py   WorkingDirectory: /opt/smoktolk/bot

## СТЕК
- aiogram 3.29.1 (Telegram)
- SQLite через aiosqlite, путь = config.DB_PATH
- aiohttp — вебхук кассы, порт config.WEBHOOK_PORT

## СТРУКТУРА КОДА
- bot.py            — точка входа, сборка роутеров (ROUTERS), запуск polling + web
- config.py         — константы: DB_PATH, WEBHOOK_PORT, ADMIN_ID, LEVELS,
                      DISCLAIMER_TEXT, RULES_TEXT, REFERRAL_REWARD_REFERRER и т.п.
- db.py             — работа с БД (get_user, create/restore_profile, accept_rules,
                      add_points, ... ) async-функции
- keyboards.py      — импортируется как `kb`; функции kb_main(is_admin),
                      kb_accept_rules(), kb_share_phone() и др.
- handlers/*.py     — роутеры. Главный флоу — handlers/start.py
- ONBOARDING_AI.md  — ЭТОТ ФАЙЛ.

## ФЛОУ ОНБОРДИНГА (handlers/start.py) — держи в голове
1. /start -> show DISCLAIMER_TEXT + kb_accept_rules()
   kb_accept_rules(): 2 кнопки — "📖 Прочитать правила"(cb: show_rules_first),
   "✅ Принимаю правила"(cb: accept_rules).  Кнопки "Магазины" НЕТ.
2. accept_rules_cb:
   - профиль был удалён (deleted_at) -> db.restore_profile -> "♻️ С возвращением" -> меню
   - нет телефона -> FSM Reg.awaiting_phone -> kb_share_phone()
   - иначе -> "✅ Правила приняты" -> меню
3. show_main_menu(msg, user_id=None) — шлёт "🏪 SMOKTOLK" + уровень/баллы/покупки
   + kb_main(). ВАЖНО: при вызове из callback передавать user_id=cb.from_user.id
   (иначе msg.from_user = БОТ!).

## ОБЯЗАТЕЛЬНЫЕ ПРОВЕРКИ ПОСЛЕ ЛЮБОЙ ПРАВКИ
    cd /opt/smoktolk/bot
    venv/bin/python -c "import ast; ast.parse(open('ФАЙЛ.py').read()); print('AST OK')"
    venv/bin/python -c "import МОДУЛЬ; print('IMPORT OK')"
    sudo systemctl restart smoktolk-bot.service && sleep 2 && sudo systemctl is-active smoktolk-bot.service

## GIT
- Коммиты в main ЗАПРЕЩЕНЫ (защищённая ветка).
- Flow: git checkout -b feature/... ; commit ; push ; PR на GitHub ; CI ; merge через UI.

## ТЕСТОВЫЙ ЮЗЕР
- telegram id: 1492067664 (проверить, совпадает ли с config.ADMIN_ID)
- Сымитировать удалённый профиль для теста восстановления:
    venv/bin/python -c "import sqlite3,config; c=sqlite3.connect(config.DB_PATH); c.execute(\"UPDATE users SET deleted_at='2026-07-05T12:36:12+00:00' WHERE user_id=1492067664\"); c.commit(); print('re-deleted')"

# ════════════════════════════════════════════════════════
#  ИСТОРИЯ / СТАТУС ЗАДАЧ
# ════════════════════════════════════════════════════════
[DONE] Убрана кнопка "🏬 Магазины" из kb_accept_rules (keyboards.py).
[DONE] DISCLAIMER_TEXT дополнен: "Магазин для тех, кто знает, чего хочет." +
       "Программа лояльности: баллы за покупки, подарки за уровень, приглашение друзей." (config.py ~стр 67).
[DONE-ФИКС] "Меню не приходит после принятия правил" — РЕШЕНО.
       Причина: show_main_menu(cb.message) брал msg.from_user.id = БОТ ->
       db.get_user(BOT_ID)=None -> тихий сбой.
       Решение: show_main_menu(msg, user_id=None); внутри uid=user_id or msg.from_user.id;
       все callback-вызовы теперь show_main_menu(cb.message, cb.from_user.id)
       (строки ~172,183,253). Применено, IMPORT OK, сервис active.

## ЖДЁТ ФИНАЛЬНОГО ТЕСТА ЮЗЕРОМ
Профиль 1492067664 пере-удалён. Юзер должен: /start -> "✅ Принимаю правила"
-> ожидается: "♻️ С возвращением..." + меню "🏪 SMOKTOLK". Если меню пришло — задача закрыта.

## ЕСЛИ ТЕСТ НЕ ПРОШЁЛ — разведка первой командой:
    cd /opt/smoktolk/bot
    sed -n '138,150p' handlers/start.py
    grep -n "show_main_menu" handlers/start.py
    sudo journalctl -u smoktolk-bot.service -n 60 --no-pager | grep -iB2 -A6 "error\|traceback\|KeyError\|None"
