"""Фоновые задачи: ежедневное сжигание баллов, поздравления с ДР."""
import asyncio
import logging
from datetime import datetime, time, timezone, timedelta
from aiogram import Bot

import db
from config import BIRTHDAY_BONUS_RATE

log = logging.getLogger(__name__)


async def _sleep_until(hour_utc: int, minute_utc: int = 0):
    now = datetime.now(timezone.utc)
    target = now.replace(hour=hour_utc, minute=minute_utc, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    await asyncio.sleep((target - now).total_seconds())


async def daily_burn_loop():
    """Каждый день в 03:00 UTC сжигаем баллы у неактивных."""
    while True:
        try:
            await _sleep_until(3, 0)
            burned = await db.burn_inactive_points()
            if burned:
                await db.bump_daily("points_burned", burned)
                log.info("Daily burn: %d points", burned)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.exception("burn loop: %s", e)
            await asyncio.sleep(60)


async def birthday_loop(bot: Bot):
    """Каждый день в 09:00 UTC (12:00 МСК) шлём поздравление пользователям, у которых сегодня ДР."""
    while True:
        try:
            await _sleep_until(9, 0)
            ids = await db.all_user_ids(only_with_notifications=True)
            today = datetime.now(timezone.utc).date()
            sent = 0
            for uid in ids:
                u = await db.get_user(uid)
                if not u or not u["birthday"]:
                    continue
                try:
                    bd = datetime.fromisoformat(u["birthday"]).date()
                except Exception:
                    continue
                if bd.month == today.month and bd.day == today.day:
                    try:
                        await bot.send_message(
                            uid,
                            f"🎂 С днём рождения!\n\n"
                            f"Сегодня к каждой покупке +{int(BIRTHDAY_BONUS_RATE*100)}% "
                            f"к кэшбэку. Заходите в магазин!"
                        )
                        sent += 1
                    except Exception:
                        pass
                    await asyncio.sleep(0.05)
            if sent:
                log.info("Birthday greetings sent: %d", sent)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.exception("birthday loop: %s", e)
            await asyncio.sleep(60)
