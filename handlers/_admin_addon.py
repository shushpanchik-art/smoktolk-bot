"""
Дополнения к админ-панели:
- Экспорт пользователей в CSV (всех / новых за N дней)

Не дублирует существующий функционал admin.py.
Использует РЕАЛЬНУЮ схему БД (full_name, без is_active/first_name/last_name).
"""
import csv
import io
import logging
from datetime import datetime, timezone, timedelta

import aiosqlite
from aiogram import F, Router
from aiogram.types import (
    CallbackQuery, BufferedInputFile,
    InlineKeyboardButton, InlineKeyboardMarkup
)

from config import ADMIN_ID, DB_PATH

router = Router()
log = logging.getLogger(__name__)


def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID


def kb_export_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Все пользователи", callback_data="adm_export_all")],
        [InlineKeyboardButton(text="🆕 Новые за 24 часа", callback_data="adm_export_new_1")],
        [InlineKeyboardButton(text="🆕 Новые за 7 дней",  callback_data="adm_export_new_7")],
        [InlineKeyboardButton(text="🆕 Новые за 30 дней", callback_data="adm_export_new_30")],
        [InlineKeyboardButton(text="« К админке", callback_data="admin_main")],
    ])


@router.callback_query(F.data == "adm_export")
async def adm_export_menu(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("Доступ запрещён", show_alert=True)
        return
    await cb.message.edit_text(
        "📤 <b>Экспорт пользователей в CSV</b>\n\nВыберите выборку:",
        reply_markup=kb_export_menu()
    )
    await cb.answer()


async def _fetch_users(since_days: int | None):
    sql = ("SELECT user_id, username, full_name, phone, birthday, "
           "age_verified, level, points, lifetime_points, "
           "purchases_count, total_spent, "
           "notifications_enabled, created_at, last_activity "
           "FROM users")
    params = ()
    if since_days is not None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()
        sql += " WHERE created_at >= ?"
        params = (cutoff,)
    sql += " ORDER BY created_at DESC"

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(sql, params) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def _send_csv(cb: CallbackQuery, since_days: int | None, label: str):
    rows = await _fetch_users(since_days)
    if not rows:
        await cb.message.answer("📭 Пользователей по этой выборке нет.")
        await cb.answer()
        return

    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow([
        "user_id", "username", "full_name", "phone", "birthday",
        "age_verified", "level", "points", "lifetime_points",
        "purchases_count", "total_spent",
        "notifications_enabled", "created_at", "last_activity",
    ])
    for r in rows:
        w.writerow([
            r.get("user_id") or "",
            r.get("username") or "",
            r.get("full_name") or "",
            r.get("phone") or "",
            r.get("birthday") or "",
            r.get("age_verified") or 0,
            r.get("level") or 1,
            r.get("points") or 0,
            r.get("lifetime_points") or 0,
            r.get("purchases_count") or 0,
            r.get("total_spent") or 0,
            r.get("notifications_enabled") or 0,
            r.get("created_at") or "",
            r.get("last_activity") or "",
        ])

    data = buf.getvalue().encode("utf-8-sig")  # BOM — чтобы Excel корректно открыл кириллицу
    fname = f"users_{label}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"

    await cb.message.answer_document(
        BufferedInputFile(data, filename=fname),
        caption=f"📊 Экспорт: <b>{len(rows)}</b> пользователей ({label})"
    )
    await cb.answer("Готово")


@router.callback_query(F.data == "adm_export_all")
async def adm_export_all(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("Доступ запрещён", show_alert=True)
        return
    await _send_csv(cb, since_days=None, label="all")


@router.callback_query(F.data.startswith("adm_export_new_"))
async def adm_export_new(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("Доступ запрещён", show_alert=True)
        return
    try:
        days = int(cb.data.rsplit("_", 1)[-1])
    except ValueError:
        days = 1
    await _send_csv(cb, since_days=days, label=f"new_{days}d")


# ============================================================
# Админ: изменить дату рождения пользователя (force=True)
# ============================================================
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message
from datetime import datetime as _dt

import db as _db


class AdmBday(StatesGroup):
    awaiting_date = State()


@router.callback_query(F.data.startswith("adm_bday_set:"))
async def adm_bday_set_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("Доступ запрещён", show_alert=True)
        return
    try:
        uid = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer("Битый ID", show_alert=True)
        return
    user = await _db.get_user(uid)
    cur = (user or {}).get("birthday") or "не указана"
    await state.set_state(AdmBday.awaiting_date)
    await state.update_data(target_uid=uid)
    await cb.message.answer(
        f"🎂 <b>Изменение ДР пользователя</b> <code>{uid}</code>\n"
        f"Текущая: <b>{cur}</b>\n\n"
        "Пришлите новую дату в формате <code>ДД.ММ.ГГГГ</code>\n"
        "Например: <code>15.03.1990</code>\n\n"
        "Или /cancel для отмены."
    )
    await cb.answer()


@router.message(AdmBday.awaiting_date, F.text == "/cancel")
async def adm_bday_cancel(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("Отменено.")


@router.message(AdmBday.awaiting_date, F.text)
async def adm_bday_set_apply(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    raw = (msg.text or "").strip()
    try:
        d = _dt.strptime(raw, "%d.%m.%Y")
    except ValueError:
        await msg.answer("❌ Неверный формат. Жду <code>ДД.ММ.ГГГГ</code>, например <code>15.03.1990</code>.")
        return
    iso = d.strftime("%Y-%m-%d")

    data = await state.get_data()
    uid = int(data.get("target_uid") or 0)
    if not uid:
        await state.clear()
        await msg.answer("❌ Потерян target_uid, повторите.")
        return

    await _db.set_birthday(uid, iso, force=True)
    await state.clear()
    log.info("Admin %s set birthday for user %s -> %s", msg.from_user.id, uid, iso)
    await msg.answer(
        f"✅ ДР пользователя <code>{uid}</code> установлена: <b>{iso}</b>"
    )
