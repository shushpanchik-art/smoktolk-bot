"""Карточка раздела «Магазины»: текст + кнопка-URL на Яндекс.Карты."""
from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)

from config import STORE_INFO_TEXT, STORE_MAP_URL, STORE_MAP2_URL

router = Router(name="address")


def _kb_address(from_disclaimer: bool) -> InlineKeyboardMarkup:
    """Клавиатура раздела магазинов.

    Если попали из дисклеймера (правила ещё не приняты) — кнопка ведёт обратно
    к дисклеймеру. Иначе — стандартная «« Назад» в главное меню.
    """
    rows = [
        [InlineKeyboardButton(text="🗺 Открыть в Яндекс.Картах", url=STORE_MAP_URL)],
    ]
    if STORE_MAP2_URL:
        rows.append([InlineKeyboardButton(text="🧭 Открыть в 2ГИС", url=STORE_MAP2_URL)])
    if from_disclaimer:
        rows.append([InlineKeyboardButton(text="« Назад", callback_data="back_to_rules")])
    else:
        rows.append([InlineKeyboardButton(text="« В главное меню", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "store_address")
async def cb_address(cb: CallbackQuery):
    # Если у текущего сообщения есть фото (баннер дисклеймера/welcome) —
    # отправим новое сообщение, edit_text по медиа нельзя.
    import db
    user = await db.get_user(cb.from_user.id)
    from_disclaimer = bool(not user or not user["rules_accepted_at"])

    msg = cb.message
    has_photo = bool(msg and msg.photo)
    kbm = _kb_address(from_disclaimer=from_disclaimer)
    if has_photo:
        await msg.answer(STORE_INFO_TEXT, reply_markup=kbm)
    else:
        try:
            await msg.edit_text(STORE_INFO_TEXT, reply_markup=kbm)
        except Exception:
            await msg.answer(STORE_INFO_TEXT, reply_markup=kbm)
    await cb.answer()


@router.callback_query(F.data == "back_to_rules")
async def cb_back_to_rules(cb: CallbackQuery):
    """Возврат к экрану welcome+дисклеймер (для гостей без правил)."""
    from handlers.start import _send_welcome_disclaimer
    try:
        await cb.message.delete()
    except Exception:
        pass
    await _send_welcome_disclaimer(cb.message)
    await cb.answer()
