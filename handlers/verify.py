"""Подтверждение возраста: пользователь шлёт фото документа,
админу @utc2000 приходит карточка с кнопками."""
import logging
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import db
import keyboards as kb
from config import ADMIN_ID
from utils import esc

router = Router()
log = logging.getLogger(__name__)


class Vrf(StatesGroup):
    waiting_photo = State()


@router.callback_query(F.data == "verify_start")
async def verify_start(cb: CallbackQuery):
    user = await db.get_user(cb.from_user.id)
    if user["age_verified"]:
        await cb.answer("Возраст уже подтверждён", show_alert=True)
        return
    text = (
        "🔞 <b>Подтверждение возраста</b>\n\n"
        "Пришлите фото страницы паспорта <b>с датой рождения</b>.\n"
        "Серию, номер и адрес можно закрыть пальцем или замазать.\n\n"
        "Заявку проверит администратор вручную.\n\n"
        "⚠️ Подтверждение не даёт права купить никотиновую продукцию "
        "без проверки документа в магазине — оно нужно только для "
        "повышения уровня в программе лояльности."
    )
    await cb.message.edit_text(text, reply_markup=kb.kb_verify_start())
    await cb.answer()


@router.callback_query(F.data == "verify_send_photo")
async def verify_send_photo(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Vrf.waiting_photo)
    await cb.message.answer("📷 Пришлите одну фотографию документа.")
    await cb.answer()


@router.message(Vrf.waiting_photo, F.photo)
async def got_photo(msg: Message, state: FSMContext, bot: Bot):
    file_id = msg.photo[-1].file_id
    req_id = await db.create_verification_request(msg.from_user.id, file_id, None)
    await state.clear()
    await msg.answer(
        "✅ Заявка отправлена. Администратор проверит её в течение рабочего дня.\n"
        "Вы получите уведомление о результате.",
        reply_markup=kb.kb_back_main()
    )
    user = await db.get_user(msg.from_user.id)
    caption = (
        f"🔞 <b>Заявка #{req_id}</b>\n\n"
        f"User: <code>{user['user_id']}</code>\n"
        f"Имя: {esc(user['full_name'] or '—')}\n"
        f"Username: @{esc(user['username']) if user['username'] else '—'}\n"
        f"Телефон: <code>{esc(user['phone'] or '—')}</code>"
    )
    try:
        await bot.send_photo(ADMIN_ID, file_id, caption=caption,
                             reply_markup=kb.kb_verify_admin(req_id))
    except Exception as e:
        log.exception("Cannot notify admin: %s", e)


@router.message(Vrf.waiting_photo)
async def waiting_photo_other(msg: Message):
    await msg.answer("Нужно прислать именно фото документа.")


@router.callback_query(F.data.startswith("vrf_ok:"))
async def vrf_ok(cb: CallbackQuery, bot: Bot):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("Только для админа", show_alert=True)
        return
    req_id = int(cb.data.split(":")[1])
    req = await db.get_verification_request(req_id)
    if not req or req["status"] != "pending":
        await cb.answer("Заявка уже обработана", show_alert=True)
        return
    await db.set_age_verified(req["user_id"], ADMIN_ID, True)
    await db.update_verification_status(req_id, "approved", ADMIN_ID)
    await db.bump_daily("age_verified")
    new_lvl = await db.recalc_level(req["user_id"])
    await cb.message.edit_caption(
        caption=(cb.message.caption or "") + "\n\n✅ Подтверждено",
        reply_markup=None
    )
    try:
        await bot.send_message(
            req["user_id"],
            f"✅ Возраст подтверждён. Ваш уровень: L{new_lvl}.\n"
            "Теперь доступны повышенные ставки кэшбэка."
        )
    except Exception:
        pass
    # проверим реферальную награду
    paid_to = await db.try_pay_referral_reward(req["user_id"])
    if paid_to:
        try:
            await bot.send_message(paid_to, "👥 Ваш приглашённый друг подтвердил возраст и сделал покупку — баллы начислены!")
        except Exception:
            pass
    await cb.answer("Готово")


@router.callback_query(F.data.startswith("vrf_no:"))
async def vrf_no(cb: CallbackQuery, bot: Bot):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("Только для админа", show_alert=True)
        return
    req_id = int(cb.data.split(":")[1])
    req = await db.get_verification_request(req_id)
    if not req or req["status"] != "pending":
        await cb.answer("Уже обработана", show_alert=True)
        return
    await db.update_verification_status(req_id, "rejected", ADMIN_ID)
    await cb.message.edit_caption(
        caption=(cb.message.caption or "") + "\n\n❌ Отклонено",
        reply_markup=None
    )
    try:
        await bot.send_message(
            req["user_id"],
            "❌ Заявка на подтверждение возраста отклонена.\n"
            "Если это ошибка — отправьте новое фото через меню → Профиль."
        )
    except Exception:
        pass
    await cb.answer("Отклонено")


@router.callback_query(F.data.startswith("vrf_again:"))
async def vrf_again(cb: CallbackQuery, bot: Bot):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("Только для админа", show_alert=True)
        return
    req_id = int(cb.data.split(":")[1])
    req = await db.get_verification_request(req_id)
    if not req or req["status"] != "pending":
        await cb.answer("Уже обработана", show_alert=True)
        return
    await db.update_verification_status(req_id, "need_more", ADMIN_ID)
    await cb.message.edit_caption(
        caption=(cb.message.caption or "") + "\n\n⚠️ Запрошено новое фото",
        reply_markup=None
    )
    try:
        await bot.send_message(
            req["user_id"],
            "⚠️ Документ не читается. Пришлите более чёткое фото "
            "через меню → Профиль → Подтвердить возраст."
        )
    except Exception:
        pass
    await cb.answer("Запрошено новое фото")
