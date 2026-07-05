"""Логирование message_id сообщений бота и удаление недавних (<48ч).

Telegram Bot API позволяет боту удалять свои сообщения только моложе 48 часов.
Полное стирание истории (deleteHistory) недоступно ботам — только userbot,
который к диалогу user<->bot доступа не имеет. Поэтому максимум возможного:
запомнить id всех отправленных ботом сообщений и при удалении профиля
удалить всё, что ещё моложе 48 часов.
"""
import logging
import time
from typing import Iterable

import aiosqlite
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
import asyncio

log = logging.getLogger(__name__)

# Bot API: удалять можно только сообщения моложе 48ч. Берём с запасом 47ч.
DELETABLE_WINDOW_SEC = 47 * 3600
_DELETE_BATCH = 100  # deleteMessages принимает до 100 id за раз


async def migrate_msg_log(db_path: str):
    """Идемпотентно создаёт таблицу лога сообщений бота."""
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_messages (
                chat_id    INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                sent_at    INTEGER NOT NULL,
                PRIMARY KEY (chat_id, message_id)
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bot_messages_chat "
            "ON bot_messages(chat_id, sent_at)"
        )
        await conn.commit()
    log.info("msg_wipe: bot_messages table ready")


async def log_message(db_path: str, chat_id: int, message_id: int):
    """Записать id отправленного ботом сообщения."""
    now = int(time.time())
    try:
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute(
                "INSERT OR IGNORE INTO bot_messages(chat_id, message_id, sent_at) "
                "VALUES (?, ?, ?)",
                (chat_id, message_id, now),
            )
            await conn.commit()
    except Exception as e:  # логирование не должно ломать бота
        log.warning("msg_wipe.log_message failed: %s", e)


async def _fetch_deletable(db_path: str, chat_id: int) -> list[int]:
    cutoff = int(time.time()) - DELETABLE_WINDOW_SEC
    async with aiosqlite.connect(db_path) as conn:
        cur = await conn.execute(
            "SELECT message_id FROM bot_messages "
            "WHERE chat_id = ? AND sent_at >= ? ORDER BY message_id",
            (chat_id, cutoff),
        )
        return [row[0] for row in await cur.fetchall()]


async def _forget(db_path: str, chat_id: int, message_ids: Iterable[int]):
    ids = list(message_ids)
    if not ids:
        return
    async with aiosqlite.connect(db_path) as conn:
        await conn.executemany(
            "DELETE FROM bot_messages WHERE chat_id = ? AND message_id = ?",
            [(chat_id, mid) for mid in ids],
        )
        await conn.commit()


async def _forget_all(db_path: str, chat_id: int):
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute("DELETE FROM bot_messages WHERE chat_id = ?", (chat_id,))
        await conn.commit()


async def wipe_recent(bot: Bot, db_path: str, chat_id: int) -> int:
    """Удаляет все сообщения бота в чате моложе 48ч. Возвращает число удалённых.

    Устаревшие (>48ч) записи просто забываются — их всё равно не удалить.
    """
    ids = await _fetch_deletable(db_path, chat_id)
    deleted = 0
    for i in range(0, len(ids), _DELETE_BATCH):
        batch = ids[i:i + _DELETE_BATCH]
        try:
            await bot.delete_messages(chat_id=chat_id, message_ids=batch)
            deleted += len(batch)
            await _forget(db_path, chat_id, batch)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            try:
                await bot.delete_messages(chat_id=chat_id, message_ids=batch)
                deleted += len(batch)
                await _forget(db_path, chat_id, batch)
            except Exception as e2:
                log.warning("msg_wipe: batch retry failed: %s", e2)
        except TelegramBadRequest:
            # часть уже удалена/недоступна — пробуем по одному
            for mid in batch:
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=mid)
                    deleted += 1
                except Exception:
                    pass
                await _forget(db_path, chat_id, [mid])
        except Exception as e:
            log.warning("msg_wipe: delete batch failed: %s", e)
    # чистим весь лог по этому чату (в т.ч. устаревшие записи)
    await _forget_all(db_path, chat_id)
    log.info("msg_wipe: wiped %d messages in chat %s", deleted, chat_id)
    return deleted
