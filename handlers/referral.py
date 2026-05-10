from aiogram import Router, F
from aiogram.types import CallbackQuery

import db
import keyboards as kb
from config import (BOT_USERNAME, REFERRAL_REWARD_REFERRER,
                    REFERRAL_REWARD_INVITEE, REFERRAL_MIN_PURCHASE)
from utils import esc

router = Router()


@router.callback_query(F.data == "referral_main")
async def referral_main(cb: CallbackQuery):
    user = await db.get_user(cb.from_user.id)
    refs = await db.get_referrals(cb.from_user.id)
    paid = sum(1 for r in refs if r["referral_reward_paid"])
    pending = len(refs) - paid
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{user['referral_code']}"
    text = (
        "👥 <b>Пригласите друга</b>\n\n"
        f"Ваша ссылка:\n<code>{esc(link)}</code>\n\n"
        f"Код: <code>{user['referral_code']}</code>\n\n"
        f"<b>Награды:</b>\n"
        f"• Вам: <b>{REFERRAL_REWARD_REFERRER}</b> баллов\n"
        f"• Другу: <b>{REFERRAL_REWARD_INVITEE}</b> баллов\n\n"
        f"Условия: друг регистрируется по ссылке, подтверждает возраст "
        f"и делает покупку от {REFERRAL_MIN_PURCHASE} ₽.\n\n"
        f"📊 Приглашено: <b>{len(refs)}</b>\n"
        f"   Награда выплачена: <b>{paid}</b>\n"
        f"   Ожидают условий: <b>{pending}</b>"
    )
    await cb.message.edit_text(text, reply_markup=kb.kb_referral_share(user["referral_code"]))
    await cb.answer()
