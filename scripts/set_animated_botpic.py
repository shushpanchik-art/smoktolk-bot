"""
Одноразовая утилита: установить анимированную аватарку бота.

Использование:
    1) sudo systemctl stop smoktolk-bot   # остановить основной процесс
    2) python scripts/set_animated_botpic.py
    3) sudo systemctl start smoktolk-bot

Требует: aiogram >= 3.21 (Bot API 9.0+).
Файл-источник: data/avatr2_botpic.mp4 (640×640, ≤1MB, H.264, без аудио).
"""
import asyncio
import logging
import sys
from pathlib import Path
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InputProfilePhotoAnimated, FSInputFile

# Чтобы импортировать config из корня проекта
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("set_botpic")

AVATAR_PATH = Path(__file__).resolve().parent.parent / "data" / "avatr2_botpic.mp4"
MAIN_FRAME_TS = 1.5  # секунда, из которой возьмётся статичная превьюшка


async def main() -> None:
    if not AVATAR_PATH.exists():
        log.error("Файл не найден: %s", AVATAR_PATH)
        sys.exit(1)

    size = AVATAR_PATH.stat().st_size
    log.info("Файл: %s (%d байт = %.1f KB)", AVATAR_PATH, size, size / 1024)
    if size > 1_048_576:
        log.error("Файл больше 1 MB — Telegram отклонит. Пережмите ffmpeg-ом.")
        sys.exit(1)

    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    try:
        animation = FSInputFile(str(AVATAR_PATH))
        photo = InputProfilePhotoAnimated(
            animation=animation,
            main_frame_timestamp=MAIN_FRAME_TS,
        )
        result = await bot.set_my_profile_photo(photo=photo)
        log.info("✅ set_my_profile_photo вернул: %s", result)

        me = await bot.get_me()
        log.info("Бот: @%s (id=%s) — аватарка обновлена.", me.username, me.id)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
