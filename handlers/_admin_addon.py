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
