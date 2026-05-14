"""
Уведомления админу (ADMIN_ID) о событиях, требующих внимания.

Все функции защищены try/except и НЕ должны срывать основной flow.
Запускаются через asyncio.create_task() — fire-and-forget.

SPEC §25 (алерт-канал админа), §26 (новый пункт: уведомление о регистрации).
"""
from __future__ import annotations

import asyncio
import logging
from html import escape
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from config import ADMIN_ID

log = logging.getLogger(__name__)


def _fmt_referrer(referrer: Optional[dict]) -> str:
    """Форматирует данные реферера для админ-сообщения."""
    if not referrer:
        return "—"
    uid = referrer.get("user_id")
    name = referrer.get("full_name") or "—"
    uname = referrer.get("username")
    uname_part = f" @{escape(uname)}" if uname else ""
    return f"{escape(name)}{uname_part} (id=<code>{uid}</code>)"


def _fmt_user(user: dict) -> str:
    """Карточка нового пользователя в HTML-разметке."""
    uid = user.get("user_id")
    name = user.get("full_name") or "—"
    uname = user.get("username")
    uname_part = f"@{escape(uname)}" if uname else "<i>без username</i>"
    return (
        f"🆕 <b>Новый пользователь</b>\n\n"
        f"👤 {escape(name)}\n"
        f"🔗 {uname_part}\n"
        f"🆔 <code>{uid}</code>"
    )


async def notify_admin_new_user(
    bot: Bot,
    user: dict,
    referrer: Optional[dict] = None,
) -> bool:
    """
    Отправляет админу уведомление о новой регистрации.

    Args:
        bot: объект aiogram.Bot
        user: словарь нового пользователя (из db.get_user)
        referrer: словарь реферера или None

    Returns:
        True если отправлено, False при ошибке (ошибка логируется, не пробрасывается).
    """
    if not user:
        log.warning("notify_admin_new_user: user is empty, skip")
        return False

    text = _fmt_user(user)
    text += f"\n👥 Реферер: {_fmt_referrer(referrer)}"

    try:
        await bot.send_message(ADMIN_ID, text, parse_mode="HTML")
        log.info("admin notified about new user %s", user.get("user_id"))
        return True
    except TelegramAPIError as e:
        log.error("Failed to notify admin about new user %s: %s",
                  user.get("user_id"), e)
        return False
    except Exception as e:
        log.exception("Unexpected error in notify_admin_new_user: %s", e)
        return False


def notify_admin_new_user_bg(
    bot: Bot,
    user: dict,
    referrer: Optional[dict] = None,
) -> asyncio.Task:
    """
    Fire-and-forget обёртка: запускает уведомление в фоне,
    не блокируя основной flow регистрации.
    """
    return asyncio.create_task(notify_admin_new_user(bot, user, referrer))
