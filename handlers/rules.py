"""Просмотр правил из меню."""
from aiogram import Router, F
from aiogram.types import CallbackQuery

import keyboards as kb
from config import RULES_TEXT

router = Router()


@router.callback_query(F.data == "rules_main")
async def show_rules(cb: CallbackQuery):
    await cb.message.edit_text(RULES_TEXT, reply_markup=kb.kb_back_main())
    await cb.answer()
