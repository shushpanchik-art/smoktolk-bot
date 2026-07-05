"""aiogram 3 middleware: логирует message_id всех сообщений, отправленных ботом.

Вешается на bot.session.middleware() — перехватывает ЛЮБОЙ вызов API,
и если результат содержит Message (send_message, answer, send_photo и т.д.),
пишет его id в bot_messages.
"""
import logging

from aiogram.types import Message

import msg_wipe
from config import DB_PATH

log = logging.getLogger(__name__)


async def bot_outgoing_logger(make_request, bot, method):
    """API-layer middleware (aiogram 3): вызывается на каждый запрос к Bot API."""
    result = await make_request(bot, method)
    try:
        msg = None
        if isinstance(result, Message):
            msg = result
        elif isinstance(result, (list, tuple)):
            # напр. send_media_group -> список Message
            for item in result:
                if isinstance(item, Message):
                    await msg_wipe.log_message(DB_PATH, item.chat.id, item.message_id)
            return result
        if msg is not None:
            await msg_wipe.log_message(DB_PATH, msg.chat.id, msg.message_id)
    except Exception as e:
        log.warning("msg_wipe_mw: %s", e)
    return result
