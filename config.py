"""Все константы и тексты бота. Меняем здесь — не лезем в логику."""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "5899721537"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "utc200")

WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "127.0.0.1")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8080"))
WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN", "")
WEBHOOK_MODE = os.getenv("WEBHOOK_MODE", "stub")  # stub | live
POS_API_KEY = os.getenv("POS_API_KEY", "")

CATALOG_URL = os.getenv("CATALOG_URL", "")
DB_PATH = os.getenv("DB_PATH", "smoktolk.db")
LOG_FILE = os.getenv("LOG_FILE", "/opt/smoktolk/bot/logs/bot.log")
TZ = os.getenv("TZ", "Europe/Moscow")

BOT_USERNAME = "SMOKTOLK_bot"

# ====== УРОВНИ ======
@dataclass
class Level:
    num: int
    name: str
    earn_rate: float          # 0.10 = 10%
    repeat_bonus: float       # доп. % за повторную покупку
    repeat_window_max: int    # верхняя граница окна (дни)
    min_lifetime_points: int  # для повышения (либо)
    min_purchases_500: int    # либо это
    requires_age: bool
    gift_cooldown_days: int   # 0 = нет подарков
    accessory_discount: float # 0.15 = 15%
    free_delivery: bool

LEVELS = {
    1: Level(1, "Исследователь", 0.10, 0.03, 5,    0,    0,  False, 0,  0.0,  False),
    2: Level(2, "Знаток",        0.11, 0.05, 8,    0,    0,  True,  0,  0.0,  False),
    3: Level(3, "Мастер пара",   0.12, 0.07, 12,   1500, 15, True,  60, 0.0,  False),
    4: Level(4, "Профи",         0.13, 0.10, 15,   4000, 40, True,  30, 0.15, False),
    5: Level(5, "Легенда",       0.15, 0.12, 15,   8000, 80, True,  30, 0.15, True),
}

REPEAT_MIN_DAYS = 3
BIRTHDAY_BONUS_RATE = 0.20      # +20 п.п. сверх базы
POINTS_TO_RUB = 10              # 10 баллов = 1 ₽
MIN_REDEEM_POINTS = 200
MAX_REDEEM_PERCENT = 0.30       # 30% от чека
POINTS_TTL_DAYS = 120
REDEEM_QR_TTL_MINUTES = 15

REFERRAL_REWARD_REFERRER = 300
REFERRAL_REWARD_INVITEE = 200
REFERRAL_MIN_PURCHASE = 500

ALLOWED_REDEEM_CATEGORIES = {"accessories", "tools", "cables", "sweets"}
NICOTINE_CATEGORIES = {"liquid", "device", "tobacco", "pods", "disposable"}

CATALOG_REFRESH_INTERVAL = 3600  # секунд
DAILY_REPORT_HOUR = 9            # МСК

# ====== ТЕКСТЫ ======
DISCLAIMER_TEXT = (
    "🏪 <b>Добро пожаловать в SMOKTOLK!</b>\n\n"
    "Бот не является интернет-магазином и не осуществляет дистанционную продажу.\n"
    "Информация в боте не является рекламой и не направлена на продвижение "
    "никотинсодержащей продукции.\n\n"
    "Продажа отдельных категорий товаров осуществляется только в розничном "
    "магазине после проверки возраста по документу.\n\n"
    "Для участия в программе лояльности необходимо принять правила сервиса 18+."
)

RULES_TEXT = (
    "<b>«Сервис 18+»: правила участия</b>\n\n"
    "1. Участником сервиса может быть только лицо старше 18 лет.\n\n"
    "2. Регистрация в Telegram-боте не даёт права на покупку без проверки "
    "документа в магазине.\n\n"
    "3. Бот не осуществляет дистанционную продажу, бронирование с "
    "обязательством покупки, оплату или доставку товаров.\n\n"
    "4. Сервис не предоставляет скидки, бонусы, подарки, купоны, кэшбэк "
    "или иные преимущества при покупке никотинсодержащей продукции, "
    "табачной продукции, устройств потребления никотина, кальянов и "
    "связанных с ними товаров.\n\n"
    "5. Сервис используется для:\n"
    "   • записи на консультацию;\n"
    "   • гарантийного обслуживания;\n"
    "   • информирования о правилах эксплуатации;\n"
    "   • уведомлений о статусе обращений;\n"
    "   • связи с магазином.\n\n"
    "6. Все решения о покупке принимаются клиентом самостоятельно в "
    "розничном магазине.\n\n"
    "7. Магазин вправе отказать в продаже при отсутствии документа, "
    "подтверждающего возраст.\n\n"
    "8. Магазин не продаёт товары несовершеннолетним.\n\n"
    "9. Уведомления сервиса носят информационный и сервисный характер.\n\n"
    "10. Участник может отключить уведомления или удалить профиль."
)

SUPPORT_TEXT = (
    "🆘 <b>Поддержка</b>\n\n"
    f"По всем вопросам обращайтесь: @{ADMIN_USERNAME}\n\n"
    "Время ответа: в течение рабочего дня."
)


# ─────────────────────────────────────────────────────────
# Адрес магазина (PR #41)
# Переопределяется через .env без редеплоя кода.
# ─────────────────────────────────────────────────────────
STORE_CITY    = os.getenv("STORE_CITY",    "Москва")
STORE_ADDRESS = os.getenv("STORE_ADDRESS", "Волгоградский проспект, 10с2")
STORE_HOURS   = os.getenv("STORE_HOURS",   "Ежедневно, 8:00 – 23:00")
STORE_MAP_URL = os.getenv("STORE_MAP_URL", "https://yandex.com/maps/-/CPgJENnt")
STORE_PHONE   = os.getenv("STORE_PHONE",   "")  # пусто = строка не показывается

def _build_store_info_text() -> str:
    lines = [
        "📍 <b>Наш магазин</b>",
        "",
        f"<b>Адрес:</b> г. {STORE_CITY}, {STORE_ADDRESS}",
        f"<b>Часы работы:</b> {STORE_HOURS}",
    ]
    if STORE_PHONE:
        lines.append(f"<b>Телефон:</b> {STORE_PHONE}")
    lines += [
        "",
        "🚫 Дистанционная продажа не осуществляется.",
        "Покупка возможна только в розничном магазине после проверки документа.",
    ]
    return "\n".join(lines)

STORE_INFO_TEXT = _build_store_info_text()
