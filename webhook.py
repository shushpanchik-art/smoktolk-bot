"""Webhook от кассы: POST /pos/purchase.
Авторизация: заголовок X-API-Key == POS_API_KEY.

Логика начисления баллов:
  1) Получаем пользователя (по user_id или phone).
  2) Считаем кэшбэк по уровню; для категорий с category_rates применяется множитель.
  3) Проверяем, есть ли предыдущая покупка в окне 3..repeat_window_max дней —
     если да и сейчас сумма >= 500 ₽, добавляем repeat_bonus к ставке.
  4) Если сегодня день рождения — единоразовый бонус +5%.
  5) Сохраняем покупку, начисляем баллы, пересчитываем уровень.
  6) Если у юзера есть referrer и условия выполнены — выплачиваем рефералу.

Пример запроса:
{
  "receipt_id": "POS-2025-001234",
  "user_id": 123456789,            // ИЛИ phone
  "phone": "+79001234567",
  "amount_rub": 1500,
  "items": [
    {"category": "liquid", "amount_rub": 1200},
    {"category": "accessories", "amount_rub": 300}
  ]
}
"""
import json
import logging
from datetime import datetime, timezone
from aiohttp import web

import db
from config import POS_API_KEY, LEVELS, BIRTHDAY_BONUS_RATE
from utils import is_birthday_today, days_between_iso

log = logging.getLogger(__name__)


async def handle_purchase(request: web.Request) -> web.Response:
    if request.headers.get("X-API-Key") != POS_API_KEY:
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)

    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "bad_json"}, status=400)

    receipt_id = str(payload.get("receipt_id") or "").strip()
    if not receipt_id:
        return web.json_response({"ok": False, "error": "no_receipt_id"}, status=400)

    if await db.purchase_exists(receipt_id):
        return web.json_response({"ok": False, "error": "duplicate_receipt"}, status=409)

    user_id = payload.get("user_id")
    phone = payload.get("phone")
    user = None
    if user_id:
        user = await db.get_user(int(user_id))
    if not user and phone:
        user = await db.get_user_by_phone(str(phone))
    if not user:
        return web.json_response({"ok": False, "error": "user_not_found"}, status=404)

    try:
        amount = int(payload.get("amount_rub") or 0)
    except Exception:
        amount = 0
    if amount <= 0:
        return web.json_response({"ok": False, "error": "bad_amount"}, status=400)

    items = payload.get("items") or []
    if not items:
        items = [{"category": "other", "amount_rub": amount}]

    lvl = LEVELS[user["level"]]
    base_rate = lvl.earn_rate
    category_rates = getattr(lvl, "category_rates", None) or {}

    points_total = 0.0
    breakdown = []
    for it in items:
        cat = str(it.get("category", "other")).lower()
        try:
            it_amount = int(it.get("amount_rub") or 0)
        except Exception:
            it_amount = 0
        if it_amount <= 0:
            continue
        rate = category_rates.get(cat, base_rate)
        pts = it_amount * rate
        points_total += pts
        breakdown.append({"category": cat, "amount": it_amount, "rate": rate, "points": pts})

    bonuses = []

    # повторная покупка
    last = await db.get_last_purchase_before(user["user_id"], 10**18)
    if last and amount >= 500:
        days = days_between_iso(datetime.now(timezone.utc).isoformat(), last["created_at"])
        if 3 <= days <= lvl.repeat_window_max:
            extra = amount * lvl.repeat_bonus
            points_total += extra
            bonuses.append({"type": "repeat", "days": days, "points": extra})

    # день рождения
    if is_birthday_today(user["birthday"]):
        extra = amount * BIRTHDAY_BONUS_RATE
        points_total += extra
        bonuses.append({"type": "birthday", "points": extra})

    points_earned = int(round(points_total))

    purchase_id = await db.register_purchase(
        user_id=user["user_id"],
        receipt_id=receipt_id,
        amount_rub=amount,
        points_earned=points_earned,
        categories_json=json.dumps(breakdown, ensure_ascii=False),
        raw_payload_json=json.dumps(payload, ensure_ascii=False),
    )

    if points_earned > 0:
        await db.add_points(
            user["user_id"], points_earned, "purchase",
            f"чек {receipt_id} на {amount} ₽"
        )
        if any(b["type"] == "repeat" for b in bonuses):
            await db.add_points(user["user_id"], 0, "repeat_bonus",
                                "бонус за повторную покупку учтён в начислении")
        if any(b["type"] == "birthday" for b in bonuses):
            await db.add_points(user["user_id"], 0, "birthday_bonus",
                                "бонус за ДР учтён в начислении")

    await db.bump_daily("purchases_count")
    await db.bump_daily("purchases_sum", amount)
    await db.bump_daily("points_earned", points_earned)

    new_level = await db.recalc_level(user["user_id"])

    # реферальная награда
    paid_to = await db.try_pay_referral_reward(user["user_id"])

    # уведомление пользователю
    bot = request.app["bot"]
    try:
        await bot.send_message(
            user["user_id"],
            f"🛒 Покупка на <b>{amount} ₽</b> учтена.\n"
            f"Начислено баллов: <b>+{points_earned}</b>"
            + ("\n🎉 Включён бонус за повторную покупку!" if any(b["type"] == "repeat" for b in bonuses) else "")
            + ("\n🎂 Бонус за день рождения!" if any(b["type"] == "birthday" for b in bonuses) else "")
            + (f"\n\nУровень: <b>L{new_level}</b>" if new_level != user["level"] else "")
        )
    except Exception:
        pass

    if paid_to:
        try:
            await bot.send_message(
                paid_to,
                "👥 Ваш приглашённый друг сделал покупку — реферальный бонус начислен!"
            )
        except Exception:
            pass

    return web.json_response({
        "ok": True,
        "purchase_id": purchase_id,
        "points_earned": points_earned,
        "new_level": new_level,
        "breakdown": breakdown,
        "bonuses": bonuses,
    })


async def handle_redeem(request: web.Request) -> web.Response:
    """Списание баллов при сканировании QR на кассе.
    POST /pos/redeem  { "qr_token": "..." | "backup_code": "..." }
    """
    if request.headers.get("X-API-Key") != POS_API_KEY:
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "bad_json"}, status=400)

    qr_token = payload.get("qr_token")
    backup = payload.get("backup_code")

    redemption = None
    if qr_token:
        redemption = await db.get_redemption_by_token(qr_token)
    # (поиск по backup_code не реализован для простоты — рекомендуется QR)
    if not redemption:
        return web.json_response({"ok": False, "error": "not_found"}, status=404)
    if redemption["status"] != "pending":
        return web.json_response({"ok": False, "error": "already_used"}, status=409)
    expires = datetime.fromisoformat(redemption["expires_at"])
    if datetime.now(timezone.utc) > expires:
        return web.json_response({"ok": False, "error": "expired"}, status=410)

    try:
        new_balance = await db.spend_points(
            redemption["user_id"], redemption["points_amount"],
            "spend", f"списание по QR {redemption['qr_token'][:8]}…"
        )
    except ValueError as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)

    await db.mark_redemption_used(redemption["qr_token"])
    await db.bump_daily("points_spent", redemption["points_amount"])

    bot = request.app["bot"]
    try:
        await bot.send_message(
            redemption["user_id"],
            f"💸 Списано <b>{redemption['points_amount']}</b> баллов.\n"
            f"Остаток: <b>{new_balance}</b>"
        )
    except Exception:
        pass
    return web.json_response({"ok": True, "spent": redemption["points_amount"],
                              "balance": new_balance})


async def handle_gift_check(request: web.Request) -> web.Response:
    """Проверка/погашение подарка. POST /pos/gift  { "qr_token": "..." }"""
    if request.headers.get("X-API-Key") != POS_API_KEY:
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "bad_json"}, status=400)
    token = payload.get("qr_token")
    if not token:
        return web.json_response({"ok": False, "error": "no_token"}, status=400)
    gift = await db.get_gift_by_token(token)
    if not gift:
        return web.json_response({"ok": False, "error": "not_found"}, status=404)
    if gift["redeemed"]:
        return web.json_response({"ok": False, "error": "already_used"}, status=409)
    await db.mark_gift_redeemed(token)
    await db.bump_daily("gifts_redeemed")
    bot = request.app["bot"]
    try:
        await bot.send_message(
            gift["user_id"],
            f"🎁 Подарок «{gift['gift_name']}» выдан в магазине. Спасибо!"
        )
    except Exception:
        pass
    return web.json_response({"ok": True, "user_id": gift["user_id"],
                              "gift_name": gift["gift_name"]})


def setup_webhook(app: web.Application):
    app.router.add_post("/pos/purchase", handle_purchase)
    app.router.add_post("/pos/redeem", handle_redeem)
    app.router.add_post("/pos/gift", handle_gift_check)
    app.router.add_get("/health", lambda r: web.json_response({"ok": True}))
