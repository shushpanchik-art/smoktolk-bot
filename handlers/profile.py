"""Профиль, история, уровни, ДР, переключение уведомлений."""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import db
from db import BirthdayAlreadySetError
import keyboards as kb
from config import LEVELS, REDEEM_QR_TTL_MINUTES, MIN_REDEEM_POINTS
from utils import esc, fmt_dt_iso, fmt_date_iso, parse_birthday

router = Router()
log = logging.getLogger(__name__)


class BDay(StatesGroup):
    waiting = State()


ACTION_LABELS = {
    "purchase": "🛒 Покупка",
    "spend": "💸 Списание",
    "referral": "👥 Реферал",
    "birthday_bonus": "🎂 ДР-бонус",
    "repeat_bonus": "🔁 Повторная",
    "welcome": "🎁 Приветственный",
    "admin_add": "➕ Админ",
    "admin_sub": "➖ Админ",
    "burn": "🔥 Сгорание",
    "gift_redeem": "🎁 Подарок",
}


@router.callback_query(F.data == "profile_main")
async def profile_main(cb: CallbackQuery):
    user = await db.get_user(cb.from_user.id)
    lvl = LEVELS[user["level"]]
    text = (
        f"👤 <b>Профиль</b>\n\n"
        f"ID: <code>{user['user_id']}</code>\n"
        f"Имя: {esc(user['full_name'] or '—')}\n"
        f"Username: @{esc(user['username']) if user['username'] else '—'}\n"
        f"Телефон: <code>{esc(user['phone'] or '—')}</code>\n"
        f"День рождения: {fmt_date_iso(user['birthday'])}\n"
        f"Возраст подтверждён: {'✅' if user['age_verified'] else '❌'}\n\n"
        f"Уровень: <b>L{lvl.num} {esc(lvl.name)}</b> (кэшбэк {int(lvl.earn_rate*100)}%)\n"
        f"Баллы: <b>{user['points']}</b>\n"
        f"Всего начислено: {user['lifetime_points']}\n"
        f"Покупок: {user['purchases_count']} (на {user['total_spent']} ₽)\n"
        f"Уведомления: {'🔔 вкл' if user['notifications_enabled'] else '🔕 выкл'}\n"
    )
    await cb.message.edit_text(text, reply_markup=kb.kb_profile(bool(user["age_verified"])))
    await cb.answer()


@router.callback_query(F.data == "profile_history")
async def profile_history(cb: CallbackQuery):
    rows = await db.get_history(cb.from_user.id, limit=20)
    if not rows:
        text = "📜 История пуста."
    else:
        lines = ["📜 <b>Последние операции:</b>\n"]
        for r in rows:
            sign = "+" if r["amount"] > 0 else ""
            label = ACTION_LABELS.get(r["action"], r["action"])
            lines.append(
                f"{fmt_dt_iso(r['created_at'])} • {label}: <b>{sign}{r['amount']}</b>"
                + (f"\n  <i>{esc(r['comment'])}</i>" if r["comment"] else "")
            )
        text = "\n".join(lines)
    await cb.message.edit_text(text, reply_markup=kb.kb_back_main())
    await cb.answer()


@router.callback_query(F.data == "profile_set_bday")
async def set_bday_start(cb: CallbackQuery, state: FSMContext):
    user = await db.get_user(cb.from_user.id)
    if user and user["birthday"]:
        await cb.answer(
            "Дата рождения уже указана. Изменить её может только поддержка.",
            show_alert=True,
        )
        return
    await state.set_state(BDay.waiting)
    await cb.message.answer(
        "🎂 Введите дату рождения в формате <b>ДД.ММ.ГГГГ</b>\n\n"
        "⚠️ <b>Внимание:</b> дата рождения указывается <b>один раз</b> "
        "и не может быть изменена самостоятельно. "
        "Если допустите ошибку — обратитесь в поддержку."
    )
    await cb.answer()


@router.message(BDay.waiting)
async def set_bday_got(msg: Message, state: FSMContext):
    iso = parse_birthday(msg.text or "")
    if not iso:
        await msg.answer("❌ Неверный формат. Пример: 15.03.1990")
        return
    try:
        await db.set_birthday(msg.from_user.id, iso)
    except BirthdayAlreadySetError:
        await state.clear()
        await msg.answer(
            "⚠️ Дата рождения уже указана. "
            "Изменить её может только поддержка.",
            reply_markup=kb.kb_back_main(),
        )
        return
    await state.clear()
    await msg.answer(
        f"✅ День рождения сохранён: {fmt_date_iso(iso)}\n\n"
        f"ℹ️ Помните: изменить дату самостоятельно нельзя.",
        reply_markup=kb.kb_back_main(),
    )


@router.callback_query(F.data == "profile_toggle_notify")
async def toggle_notify(cb: CallbackQuery):
    new_val = await db.toggle_notifications(cb.from_user.id)
    await cb.answer("🔔 Включены" if new_val else "🔕 Выключены", show_alert=True)
    # перерисуем профиль
    await profile_main(cb)


@router.callback_query(F.data == "levels_main")
async def levels_main(cb: CallbackQuery):
    user = await db.get_user(cb.from_user.id)
    lines = ["⭐️ <b>Уровни программы</b>\n",
             f"Ваш текущий уровень: <b>L{user['level']}</b>\n"]
    for n in sorted(LEVELS.keys()):
        lvl = LEVELS[n]
        mark = "👉 " if n == user["level"] else "    "
        lines.append(f"{mark}<b>L{n} {esc(lvl.name)}</b> — {int(lvl.earn_rate*100)}% кэшбэк")
    lines.append("\nНажмите на уровень для подробностей:")
    await cb.message.edit_text("\n".join(lines), reply_markup=kb.kb_levels())
    await cb.answer()


@router.callback_query(F.data.startswith("level_info:"))
async def level_info(cb: CallbackQuery):
    n = int(cb.data.split(":")[1])
    lvl = LEVELS[n]
    user = await db.get_user(cb.from_user.id)
    cond = []
    if lvl.requires_age:
        cond.append("• возраст 18+ подтверждён")
    if lvl.min_lifetime_points or lvl.min_purchases_500:
        cond.append(
            f"• {lvl.min_lifetime_points} баллов за всё время "
            f"<b>или</b> {lvl.min_purchases_500} покупок ≥ 500 ₽"
        )
    if not cond:
        cond.append("• по умолчанию (для всех)")

    perks = [
        f"• Кэшбэк <b>{int(lvl.earn_rate*100)}%</b>",
        f"• Бонус за повторную покупку (3–{lvl.repeat_window_max} дн.): <b>+{int(lvl.repeat_bonus*100)}%</b>",
    ]
    if lvl.gift_cooldown_days:
        perks.append(f"• Подарок за 1 ₽ — раз в {lvl.gift_cooldown_days} дн.")
    if lvl.accessory_discount:
        perks.append(f"• Скидка {int(lvl.accessory_discount*100)}% на аксессуары")
    if lvl.free_delivery:
        perks.append("• Бесплатная доставка аксессуаров")

    progress = ""
    if n == user["level"] + 1:
        progress = (
            f"\n\n📊 <b>До этого уровня:</b>\n"
            f"  баллы: {user['lifetime_points']}/{lvl.min_lifetime_points}\n"
            f"  покупки ≥500: {user['purchases_count_500']}/{lvl.min_purchases_500}"
        )

    text = (
        f"<b>L{n} {esc(lvl.name)}</b>\n\n"
               "<b>Условия:</b>\n" + "\n".join(cond) + "\n\n"
        "<b>Преимущества:</b>\n" + "\n".join(perks)
        + progress
    )
    await cb.message.edit_text(text, reply_markup=kb.kb_back_to_levels())
    await cb.answer()


@router.callback_query(F.data == "support_main")
async def support_main(cb: CallbackQuery):
    from config import SUPPORT_TEXT
    await cb.message.edit_text(SUPPORT_TEXT, reply_markup=kb.kb_back_main())
    await cb.answer()


# ===== СПИСАНИЕ БАЛЛОВ (QR на кассе) =====
class Redeem(StatesGroup):
    waiting_amount = State()


@router.callback_query(F.data == "redeem_start")
async def redeem_start(cb: CallbackQuery, state: FSMContext):
    user = await db.get_user(cb.from_user.id)
    if user["points"] <= 0:
        await cb.answer("На балансе нет баллов", show_alert=True)
        return
    await state.set_state(Redeem.waiting_amount)
    await cb.message.answer(
        f"💸 <b>Списание баллов</b>\n\n"
        f"Доступно: <b>{user['points']}</b> баллов\n\n"
        f"Введите сумму к списанию (целое число):",
        reply_markup=kb.kb_back_main()
    )
    await cb.answer()


@router.message(Redeem.waiting_amount)
async def redeem_amount(msg: Message, state: FSMContext):
    from aiogram.types import BufferedInputFile
    from utils import make_qr
    try:
        amount = int((msg.text or "").strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await msg.answer("❌ Введите положительное целое число.")
        return
    if amount < MIN_REDEEM_POINTS:
        await msg.answer(
            f"❌ Минимальная сумма списания — {MIN_REDEEM_POINTS} баллов.",
            reply_markup=kb.kb_back_main()
        )
        return
    user = await db.get_user(msg.from_user.id)
    if amount > user["points"]:
        await msg.answer(f"❌ Недостаточно баллов. Доступно: {user['points']}")
        return
    await state.clear()
    try:
        token, backup = await db.create_redemption(
            msg.from_user.id, amount, REDEEM_QR_TTL_MINUTES
        )
    except Exception as e:
        log.exception("create_redemption: %s", e)
        await msg.answer(
            "❌ Не удалось создать заявку. Попробуйте позже.",
            reply_markup=kb.kb_back_main()
        )
        return
    qr_png = make_qr(f"REDEEM:{token}")
    await msg.answer_photo(
        BufferedInputFile(qr_png, filename="redeem.png"),
        caption=(
            f"💸 <b>Списание {amount} баллов</b>\n\n"
            f"Покажите QR кассиру для списания.\n"
            f"Резервный код: <code>{backup}</code>\n"
            f"Действует {REDEEM_QR_TTL_MINUTES} минут."
        ),
        reply_markup=kb.kb_back_main()
    )
