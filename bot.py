"""Запуск aiogram-бота + aiohttp-вебхук в одном процессе."""
import asyncio
import logging
import logging.handlers
import os
import sys
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

import config
import db
import catalog
import webhook
import tasks
from handlers import ROUTERS
import crash_alert


def setup_logging():
    os.makedirs(os.path.dirname(config.LOG_FILE), exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        "%Y-%m-%d %H:%M:%S"
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()


    fh = logging.handlers.RotatingFileHandler(
        config.LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)

    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)


async def on_startup(bot: Bot):
    await db.init_db()
    await catalog.refresh(force=True)
    await bot.set_my_commands([
        BotCommand(command="start", description="Запустить бота / главное меню"),
    ])
    me = await bot.get_me()
    logging.info("Bot started: @%s (id=%s)", me.username, me.id)
    await crash_alert.notify_recovered_if_needed(bot)


async def main():
    setup_logging()
    log = logging.getLogger("main")

    if not config.BOT_TOKEN:
        log.error("BOT_TOKEN не задан в .env")
        sys.exit(1)
    if not config.POS_API_KEY:
        log.warning("POS_API_KEY пустой — вебхук кассы будет отклонять все запросы")

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    for r in ROUTERS:
        dp.include_router(r)

    await on_startup(bot)

    # aiohttp app для вебхука кассы
    app = web.Application()
    app["bot"] = bot
    webhook.setup_webhook(app)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="127.0.0.1", port=config.WEBHOOK_PORT)
    await site.start()
    log.info("Webhook listening on 127.0.0.1:%s", config.WEBHOOK_PORT)

    # фоновые задачи
    bg = [
        asyncio.create_task(tasks.daily_burn_loop()),
        asyncio.create_task(tasks.birthday_loop(bot)),
        asyncio.create_task(tasks.deletion_cleanup_loop(bot)),
    ]

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        for t in bg:
            t.cancel()
        await runner.cleanup()
        await bot.session.close()
        log.info("Bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
