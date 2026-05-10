"""Подарки за 1 ₽: список из каталога, проверка cooldown,
выдача QR-токена и резервного кода."""
import logging
from datetime import datetime, timezone, timedelta
from aiogram import Router, F
from aiogram.types import CallbackQuery, BufferedInputFile

import db
import keyboards as kb
import catalog
from config import LEVELS
from utils import make_qr, esc, fmt_dt_iso

router = Router()
log = logging.getLogger(__name__)


def _available_codes(user: dict, gifts: list[dict]) -> set[str]:
    return {g["code"] for g in gifts if g["min_level"] <= user["level"]}


@router.callback_query(F.data == "gifts_main")
async def gifts_main(cb: CallbackQuery):
    user = await db.get_user(cb.from_user.id)
    lvl = LEVELS[user["level"]]
    gifts = await catalog.get_gifts()
    if not gifts:
        await cb.message.edit_text(
            "🎁 Список подарков скоро появится. Попробуйте позже.",
            reply_markup=kb.kb_back_main()
        )
        await cb.answer()
        return

    available = _available_codes(user, gifts)
    last_gift_at = await db.get_last_gift_at(cb.from_user.id)
    cooldown_text = ""
    if lvl.gift_cooldown_days == 0:
        cooldown_text = (
            f"\n⚠️ Подарки за 1 ₽ доступны с уровня <b>L3 Мастер пара</b>.\n"
            f"Ваш уровень: L{lvl.num} {esc(lvl.name)}."
        )
    elif last_gift_at:
        next_at = datetime.fromisoformat(last_gift_at) + timedelta(days=lvl.gift_cooldown_days)
        if datetime.now(timezone.utc) < next_at:
            cooldown_text = f"\n⏳ Следующий подарок: {fmt_dt_iso(next_at.isoformat())}"

    text = (
        "🎁 <b>Подарки за 1 ₽</b>\n\n"
        f"Ваш уровень: <b>L{lvl.num} {esc(lvl.name)}</b>\n"
        f"Кулдаун: {lvl.gift_cooldown_days or '—'} дн."
        f"{cooldown_text}\n\n"
        "Доступные подарки помечены ✅, остальные требуют более высокого уровня:"
    )
    await cb.message.edit_text(text, reply_markup=kb.kb_gifts_list(gifts, available))
    await cb.answer()


@router.callback_query(F.data.startswith("gift_pick:"))
async def gift_pick(cb: CallbackQuery):
    code = cb.data.split(":", 1)[1]
    gift = await catalog.get_gift(code)
    if not gift:
        await cb.answer("Подарок не найден", show_alert=True)
        return
    text = (
        f"🎁 <b>{esc(gift['name'])}</b>\n\n"
        f"{esc(gift.get('description', ''))}\n\n"
        f"Минимальный уровень: L{gift['min_level']}\n"
        f"Цена: 1 ₽ (символическая, по правилам акции)"
    )
    user = await db.get_user(cb.from_user.id)
    if user["level"] < gift["min_level"]:
        await cb.answer(f"Нужен уровень L{gift['min_level']}", show_alert=True)
        return
    await cb.message.edit_text(text, reply_markup=kb.kb_gift_confirm(code))
    await cb.answer()


@router.callback_query(F.data.startswith("gift_confirm:"))
async def gift_confirm(cb: CallbackQuery):
    code = cb.data.split(":", 1)[1]
    user = await db.get_user(cb.from_user.id)
    lvl = LEVELS[user["level"]]
    gift = await catalog.get_gift(code)
    if not gift:
        await cb.answer("Подарок не найден", show_alert=True)
        return
    if user["level"] < gift["min_level"]:
        await cb.answer("Уровень слишком низкий", show_alert=True)
        return
    if lvl.gift_cooldown_days == 0:
        await cb.answer("На вашем уровне подарки недоступны", show_alert=True)
        return
    last = await db.get_last_gift_at(cb.from_user.id)
    if last:
        next_at = datetime.fromisoformat(last) + timedelta(days=lvl.gift_cooldown_days)
        if datetime.now(timezone.utc) < next_at:
            await cb.answer(f"⏳ Следующий подарок: {fmt_dt_iso(next_at.isoformat())}",
                            show_alert=True)
            return

    qr_token, backup = await db.create_gift_request(
        cb.from_user.id, gift["code"], gift["name"], user["level"]
    )
    qr_payload = f"GIFT:{qr_token}"
    qr_png = make_qr(qr_payload)
    caption = (
        f"🎁 <b>Подарок: {esc(gift['name'])}</b>\n\n"
        f"Покажите QR-код кассиру при покупке. Подарок оформляется за 1 ₽.\n\n"
        f"Резервный код: <code>{backup}</code>\n"
        f"Действует до использования."
    )
    await cb.message.answer_photo(
        BufferedInputFile(qr_png, filename="gift.png"),
        caption=caption, reply_markup=kb.kb_back_main()
    )
    await cb.answer()
