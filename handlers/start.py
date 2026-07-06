"""/start, регистрация, дисклеймер, главное меню, обработка телефона."""
import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from pathlib import Path as _Path

import db
import keyboards as kb
from config import (DISCLAIMER_TEXT, RULES_TEXT, ADMIN_ID, LEVELS,
                    REFERRAL_REWARD_REFERRER)
from services.admin_notify import notify_admin_new_user_bg
from utils import normalize_phone, esc

router = Router()
log = logging.getLogger(__name__)

# Welcome-баннер: показывается при каждом /start (и новичкам, и вернувшимся).
# Файл лежит локально, в .gitignore — поэтому шлём как FSInputFile.
_WELCOME_BANNER = _Path(__file__).resolve().parent.parent / "data" / "signboard_hor.jpg"
_WELCOME_CAPTION = (
    "🏪 <b>SMOKTOLK</b>\n"
    "Магазин для тех, кто знает, чего хочет.\n\n"
    "Программа лояльности: баллы за покупки, подарки за уровень, "
    "приглашение друзей."
)


async def _send_welcome_banner(msg: Message) -> None:
    """Шлёт картинку-вывеску с короткой подписью. Молча игнорит, если файла нет."""
    if not _WELCOME_BANNER.exists():
        log.warning("welcome banner not found: %s", _WELCOME_BANNER)
        return
    try:
        await msg.answer_photo(FSInputFile(str(_WELCOME_BANNER)), caption=_WELCOME_CAPTION)
    except Exception as e:
        log.warning("welcome banner send failed: %s", e)




async def _send_welcome_disclaimer(msg: Message) -> None:
    """Отправляет ОДНО сообщение: фото-вывеску с подписью-дисклеймером и
    кнопками «📜 Прочитать правила» / «🏬 Магазины» / «✅ Принимаю правила».

    Если файл баннера отсутствует — fallback на текстовое сообщение."""
    caption = DISCLAIMER_TEXT
    markup = kb.kb_accept_rules()
    if _WELCOME_BANNER.exists():
        try:
            await msg.answer_photo(
                FSInputFile(str(_WELCOME_BANNER)),
                caption=caption,
                reply_markup=markup,
            )
            return
        except Exception as e:
            log.warning("welcome+disclaimer photo failed, fallback to text: %s", e)
    await msg.answer(caption, reply_markup=markup)


class Reg(StatesGroup):
    awaiting_rules = State()
    awaiting_phone = State()


@router.message(CommandStart(deep_link=True))
async def start_with_payload(msg: Message, command: CommandObject, state: FSMContext):
    payload = (command.args or "").strip()
    referrer_id = None
    if payload.startswith("ref_"):
        code = payload[4:].upper()
        ref_user = await db.get_user_by_ref_code(code)
        if ref_user and ref_user["user_id"] != msg.from_user.id:
            referrer_id = ref_user["user_id"]
    await _start_common(msg, state, referrer_id)


@router.message(CommandStart())
async def start_plain(msg: Message, state: FSMContext):
    await _start_common(msg, state, None)


async def _start_common(msg: Message, state: FSMContext, referrer_id):
    user = await db.get_user(msg.from_user.id)
    # Удалённый профиль (grace period): прогоняем через онбординг как новичка.
    # Данные в БД сохранены; восстановление произойдёт после принятия правил.
    if user and user.get("deleted_at"):
        await state.set_state(Reg.awaiting_rules)
        await _send_welcome_disclaimer(msg)
        return
    if not user:
        user = await db.create_user(
            msg.from_user.id,
            msg.from_user.username or "",
            msg.from_user.full_name or "",
            referrer_id=referrer_id,
        )
        # Уведомить админа о новой регистрации (fire-and-forget).
        # SPEC §26: push при каждом новом пользователе.
        try:
            referrer_user = None
            if referrer_id:
                referrer_user = await db.get_user(referrer_id)
            notify_admin_new_user_bg(msg.bot, user, referrer_user)
        except Exception as _e:
            import logging as _lg
            _lg.getLogger(__name__).exception('notify_admin failed: %s', _e)

        await db.bump_daily("new_users")
    else:
        await db.update_user_meta(
            msg.from_user.id,
            msg.from_user.username or "",
            msg.from_user.full_name or "",
        )

    if not user["rules_accepted_at"]:
        await state.set_state(Reg.awaiting_rules)
        await _send_welcome_disclaimer(msg)
        return

    if not user["phone"]:
        await state.set_state(Reg.awaiting_phone)
        await msg.answer(
            "Для участия в программе укажите номер телефона.\n"
            "Он используется кассой для идентификации при покупке.",
            reply_markup=kb.kb_share_phone(),
        )
        return

    await show_main_menu(msg)


async def show_main_menu(msg: Message, user_id: int | None = None):
    uid = user_id if user_id is not None else msg.from_user.id
    user = await db.get_user(uid)
    lvl = LEVELS[user["level"]]
    text = (
        f"🏪 <b>SMOKTOLK</b>\n\n"
        f"Уровень: <b>L{lvl.num} {esc(lvl.name)}</b>\n"
        f"Баллы: <b>{user['points']}</b>\n"
        f"Покупок: {user['purchases_count']}\n\n"
        "Выберите раздел:"
    )
    await msg.answer(text, reply_markup=kb.kb_main(uid == ADMIN_ID))


@router.callback_query(F.data == "show_rules_first")
async def show_rules_first(cb: CallbackQuery):
    await cb.message.answer(RULES_TEXT, reply_markup=kb.kb_accept_rules())
    await cb.answer()


@router.callback_query(F.data == "accept_rules")
async def accept_rules_cb(cb: CallbackQuery, state: FSMContext):
    # Если это восстанавливаемый профиль — вернём данные (баллы/историю).
    _pre = await db.get_user(cb.from_user.id)
    _was_deleted = bool(_pre and _pre.get("deleted_at"))
    if _was_deleted:
        await db.restore_profile(cb.from_user.id)
    await db.accept_rules(cb.from_user.id)
    user = await db.get_user(cb.from_user.id)
    if _was_deleted:
        await cb.message.answer(
            "♻️ <b>С возвращением!</b>\nВаши баллы и история восстановлены."
        )
        await state.clear()
        await show_main_menu(cb.message, cb.from_user.id)
        await cb.answer()
        return
    if not user["phone"]:
        await state.set_state(Reg.awaiting_phone)
        await cb.message.answer(
            "✅ Правила приняты.\n\nТеперь укажите номер телефона:",
            reply_markup=kb.kb_share_phone(),
        )
    else:
        await cb.message.answer("✅ Правила приняты.")
        await show_main_menu(cb.message, cb.from_user.id)
    await cb.answer()


@router.message(Reg.awaiting_phone, F.contact)
async def got_contact(msg: Message, state: FSMContext):
    phone = normalize_phone(msg.contact.phone_number)
    if not phone or msg.contact.user_id != msg.from_user.id:
        await msg.answer("Используйте кнопку «📱 Поделиться номером».",
                         reply_markup=kb.kb_share_phone())
        return
    await db.set_phone(msg.from_user.id, phone)
    await state.clear()
    from aiogram.types import ReplyKeyboardRemove
    await msg.answer(f"✅ Номер сохранён: <code>{esc(phone)}</code>",
                     reply_markup=ReplyKeyboardRemove())
    # реферальный приветственный бонус начислится только после первой покупки
    user = await db.get_user(msg.from_user.id)
    if user["referrer_id"]:
        await msg.answer(
            f"🎁 Вас пригласил друг. После первой покупки от 500 ₽ "
            f"вы получите приветственный бонус, а друг — {REFERRAL_REWARD_REFERRER} баллов."
        )
    await show_main_menu(msg)


@router.message(Reg.awaiting_phone)
async def phone_text_fallback(msg: Message):
    await msg.answer("Нажмите кнопку «📱 Поделиться номером».",
                     reply_markup=kb.kb_share_phone())


@router.callback_query(F.data == "back_main")
async def back_to_main(cb: CallbackQuery):
    user = await db.get_user(cb.from_user.id)
    if not user:
        await cb.message.answer("Введите /start")
        await cb.answer()
        return
    lvl = LEVELS[user["level"]]
    text = (
        f"🏪 <b>SMOKTOLK</b>\n\n"
        f"Уровень: <b>L{lvl.num} {esc(lvl.name)}</b>\n"
        f"Баллы: <b>{user['points']}</b>\n"
        f"Покупок: {user['purchases_count']}\n\n"
        "Выберите раздел:"
    )
    try:
        await cb.message.edit_text(text, reply_markup=kb.kb_main(cb.from_user.id == ADMIN_ID))
    except Exception:
        await cb.message.answer(text, reply_markup=kb.kb_main(cb.from_user.id == ADMIN_ID))
    await cb.answer()


@router.callback_query(F.data == "restore_own_profile")
async def restore_own_profile_cb(cb: CallbackQuery, state: FSMContext):
    user = await db.get_user(cb.from_user.id)
    if not user:
        await cb.message.answer("Профиль не найден. Введите /start")
        await cb.answer()
        return
    if not user.get("deleted_at"):
        await cb.answer("Профиль уже активен", show_alert=True)
        return
    await db.restore_profile(cb.from_user.id)
    await cb.answer("Профиль восстановлен", show_alert=False)
    try:
        await cb.message.edit_text("♻️ Профиль восстановлен. Данные на месте.")
    except Exception:
        await cb.message.answer("♻️ Профиль восстановлен. Данные на месте.")
    await show_main_menu(cb.message, cb.from_user.id)
