"""
Отправка RECOVERED-уведомления админу при старте бота после крэша.

Принцип:
- systemd при падении вызывает ExecStopPost → scripts/notify_admin.sh down,
  который создаёт /run/smoktolk-bot/crashed (state-файл).
- При следующем старте бот (после успешной инициализации) проверяет наличие
  state-файла. Если есть — значит был крэш, шлём RECOVERED и удаляем файл.
- Если state-файла нет — обычный старт, ничего не делаем.

Это надёжнее, чем shell-based ExecStartPost: RECOVERED отправляется ТОЛЬКО
когда бот реально готов работать (после get_me, init_db, catalog.refresh).
"""
import logging
import os

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

import config


STATE_FILE = "/run/smoktolk-bot/crashed"
log = logging.getLogger(__name__)


async def notify_recovered_if_needed(bot: Bot) -> None:
    """
    Если есть state-файл крэша — шлём админу RECOVERED и удаляем файл.

    Идемпотентно: при отсутствии файла молча выходит.
    При ошибке Telegram API state-файл НЕ удаляется (попробуем при следующем старте).
    При PermissionError на удаление — логируем warning, но уведомление уже ушло.
    """
    if not os.path.exists(STATE_FILE):
        log.debug("crash-state-файл отсутствует — обычный старт, RECOVERED не нужен")
        return

    text = "✅ <b>SMOKTOLK_bot восстановлен</b>\nСервис снова работает."
    try:
        await bot.send_message(config.ADMIN_ID, text)
        log.info("RECOVERED-уведомление отправлено админу")
    except TelegramAPIError as e:
        log.error("Не удалось отправить RECOVERED админу: %s — state-файл оставлен", e)
        return

    try:
        os.unlink(STATE_FILE)
        log.info("crash-state-файл удалён: %s", STATE_FILE)
    except PermissionError as e:
        log.warning(
            "Нет прав удалить %s: %s. "
            "Уведомление ушло, но файл останется до ручной очистки или след. рестарта systemd.",
            STATE_FILE, e
        )
    except OSError as e:
        log.warning("Не удалось удалить %s: %s", STATE_FILE, e)
