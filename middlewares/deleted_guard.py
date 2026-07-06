"""Middleware: блокирует удалённых пользователей (soft-delete grace period).

Пока у пользователя проставлен deleted_at и не наступил purge — он не может
пользоваться ботом. Ему показывается предложение восстановить профиль.
Разрешены только: /start и callback restore_own_profile.
"""
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

import db
import keyboards as kb

log = logging.getLogger(__name__)

# Что разрешено делать удалённому пользователю.
_ALLOWED_TEXT = {"/start"}
_ALLOWED_CB = {"restore_own_profile", "accept_rules", "show_rules_first"}

_DELETED_TEXT = (
    "🗑 <b>Ваш профиль удалён.</b>\n\n"
    "Баллы и история хранятся ограниченное время. "
    "Вы можете восстановить профиль — все данные вернутся."
)


class DeletedGuardMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user_id = None
        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
            text = (event.text or "").strip()
            if text in _ALLOWED_TEXT or text.startswith("/start"):
                return await handler(event, data)
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else None
            if (event.data or "") in _ALLOWED_CB:
                return await handler(event, data)

        if user_id is None:
            return await handler(event, data)

        try:
            user = await db.get_user(user_id)
        except Exception:
            log.exception("deleted_guard: get_user failed")
            return await handler(event, data)

        # Профиль не удалён (или ещё не создан) — пропускаем.
        if not user or not user.get("deleted_at"):
            return await handler(event, data)

        # Профиль удалён — блокируем и предлагаем восстановление.
        markup = kb.kb_restore_own()
        if isinstance(event, Message):
            await event.answer(_DELETED_TEXT, reply_markup=markup)
        elif isinstance(event, CallbackQuery):
            try:
                await event.message.answer(_DELETED_TEXT, reply_markup=markup)
            except Exception:
                pass
            await event.answer("Профиль удалён", show_alert=False)
        return None  # обработку прекращаем
