"""Фоновые задачи: ежедневное сжигание баллов, поздравления с ДР."""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
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


async def deletion_cleanup_loop(bot: Bot):
    """Ежедневно 04:00 UTC: предупреждаем перед очисткой и чистим просроченные профили."""
    while True:
        try:
            await _sleep_until(4, 0)
            warn_ids = await db.warn_before_purge_candidates()
            for uid in warn_ids:
                try:
                    await bot.send_message(
                        uid,
                        "\u26a0\ufe0f <b>\u041f\u0440\u043e\u0444\u0438\u043b\u044c \u0441\u043a\u043e\u0440\u043e \u0431\u0443\u0434\u0435\u0442 \u043e\u0447\u0438\u0449\u0435\u043d</b>\n\n"
                        "\u0417\u0430\u0432\u0442\u0440\u0430 \u0431\u0430\u043b\u043b\u044b \u0438 \u0443\u0440\u043e\u0432\u0435\u043d\u044c \u0431\u0443\u0434\u0443\u0442 \u0431\u0435\u0437\u0432\u043e\u0437\u0432\u0440\u0430\u0442\u043d\u043e \u043e\u0431\u043d\u0443\u043b\u0435\u043d\u044b.\n"
                        "\u0427\u0442\u043e\u0431\u044b \u0441\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0438\u0445 \u2014 \u0432\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u0435 \u043f\u0440\u043e\u0444\u0438\u043b\u044c \u0432 \u0440\u0430\u0437\u0434\u0435\u043b\u0435 \u00ab\u041f\u0440\u043e\u0444\u0438\u043b\u044c\u00bb."
                    )
                except Exception:
                    pass
                await asyncio.sleep(0.05)
            if warn_ids:
                log.info("Deletion warnings sent: %d", len(warn_ids))
            purged = await db.purge_expired_profiles()
            if purged:
                log.info("Profiles purged: %d", purged)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.exception("deletion cleanup loop: %s", e)
            await asyncio.sleep(60)
