"""Админ-панель только для @utc2000."""
import asyncio
import logging
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import db
import keyboards as kb
import catalog
from config import ADMIN_ID, LEVELS
from utils import esc, fmt_dt_iso

router = Router()
log = logging.getLogger(__name__)


class Adm(StatesGroup):
    user_search = State()
    pts_amount = State()
    broadcast_text = State()


def _is_admin(uid: int) -> bool:
    return uid == ADMIN_ID


@router.callback_query(F.data == "admin_main")
async def admin_main(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        await cb.answer("Доступ запрещён", show_alert=True)
        return
    await cb.message.edit_text("🛠 <b>Админ-панель</b>", reply_markup=kb.kb_admin_main())
    await cb.answer()


@router.callback_query(F.data == "adm_stats")
async def adm_stats(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        await cb.answer()
        return
    s = await db.admin_stats()
    text = (
        "📊 <b>Статистика</b>\n\n"
        f"Пользователей всего: <b>{s['total_users']}</b>\n"
        f"Активны за неделю: <b>{s['active_week']}</b>\n"
        f"Возраст подтверждён: <b>{s['verified']}</b>\n"
        f"С покупками: <b>{s['with_purchases']}</b>\n\n"
        f"Сумма выручки: <b>{s['total_spent']} ₽</b>\n"
        f"Баллов на руках: <b>{s['total_points']}</b>\n\n"
        f"Заявок на верификацию: <b>{s['pending_verifications']}</b>"
    )
    await cb.message.edit_text(text, reply_markup=kb.kb_admin_back())
    await cb.answer()


@router.callback_query(F.data == "adm_today_report")
async def adm_today(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        await cb.answer()
        return
    today = datetime.utcnow().strftime("%Y-%m-%d")
    d = await db.get_daily(today)
    text = (
        f"📈 <b>Отчёт за {today}</b>\n\n"
        f"Новых пользователей: <b>{d['new_users']}</b>\n"
        f"Возраст подтверждён: <b>{d['age_verified']}</b>\n"
        f"Покупок: <b>{d['purchases_count']}</b> на <b>{d['purchases_sum']} ₽</b>\n"
        f"Начислено баллов: <b>{d['points_earned']}</b>\n"
        f"Списано баллов: <b>{d['points_spent']}</b>\n"
        f"Сгорело баллов: <b>{d['points_burned']}</b>\n"
        f"Подарков выдано: <b>{d['gifts_redeemed']}</b>"
    )
    await cb.message.edit_text(text, reply_markup=kb.kb_admin_back())
    await cb.answer()


@router.callback_query(F.data == "adm_verifs")
async def adm_verifs(cb: CallbackQuery, bot: Bot):
    if not _is_admin(cb.from_user.id):
        await cb.answer()
        return
    pending = await db.get_pending_verifications()
    if not pending:
        await cb.message.edit_text("✅ Нет заявок в очереди.", reply_markup=kb.kb_admin_back())
        await cb.answer()
        return
    await cb.message.edit_text(
        f"📋 Заявок в очереди: <b>{len(pending)}</b>\n\nКарточки придут отдельными сообщениями.",
        reply_markup=kb.kb_admin_back()
    )
    for req in pending[:10]:
        u = await db.get_user(req["user_id"])
        caption = (
            f"🔞 <b>Заявка #{req['id']}</b>\n"
            f"User: <code>{u['user_id']}</code>\n"
            f"Имя: {esc(u['full_name'] or '—')}\n"
            f"Телефон: <code>{esc(u['phone'] or '—')}</code>\n"
            f"Создана: {fmt_dt_iso(req['created_at'])}"
        )
        try:
            if req["photo_file_id"]:
                await bot.send_photo(ADMIN_ID, req["photo_file_id"], caption=caption,
                                     reply_markup=kb.kb_verify_admin(req["id"]))
            else:
                await bot.send_message(ADMIN_ID, caption,
                                       reply_markup=kb.kb_verify_admin(req["id"]))
        except Exception as e:
            log.exception("send pending: %s", e)
    await cb.answer()


@router.callback_query(F.data == "adm_users")
async def adm_users(cb: CallbackQuery, state: FSMContext):
    if not _is_admin(cb.from_user.id):
        await cb.answer()
        return
    await state.set_state(Adm.user_search)
    await cb.message.edit_text(
        "🔎 Введите user_id, телефон, username или имя:",
        reply_markup=kb.kb_admin_back()
    )
    await cb.answer()


@router.message(Adm.user_search)
async def adm_users_search(msg: Message, state: FSMContext):
    if not _is_admin(msg.from_user.id):
        return
    await state.clear()
    rows = await db.find_users(msg.text.strip())
    if not rows:
        await msg.answer("Ничего не найдено.", reply_markup=kb.kb_admin_back())
        return
    if len(rows) == 1:
        await _send_user_card(msg, rows[0]["user_id"])
        return
    lines = ["Найдено:"]
    for r in rows[:20]:
        lines.append(
            f"• <code>{r['user_id']}</code> {esc(r['full_name'] or '')} "
            f"@{esc(r['username']) if r['username'] else '—'} "
            f"L{r['level']} • {r['points']} б."
        )
    lines.append("\nОтправьте точный <code>user_id</code> для карточки.")
    await msg.answer("\n".join(lines), reply_markup=kb.kb_admin_back())
    await state.set_state(Adm.user_search)


async def _send_user_card(msg_or_cb, user_id: int):
    u = await db.get_user(user_id)
    if not u:
        text = "Пользователь не найден."
        kbm = kb.kb_admin_back()
    else:
        lvl = LEVELS[u["level"]]
        text = (
            f"👤 <b>Карточка</b>\n\n"
            f"ID: <code>{u['user_id']}</code>\n"
            f"Имя: {esc(u['full_name'] or '—')}\n"
            f"Username: @{esc(u['username']) if u['username'] else '—'}\n"
            f"Телефон: <code>{esc(u['phone'] or '—')}</code>\n"
            f"ДР: {esc(u['birthday'] or '—')}\n"
            f"Возраст 18+: {'✅' if u['age_verified'] else '❌'}\n"
            f"Уровень: L{lvl.num} {esc(lvl.name)}\n"
            f"Баллы: <b>{u['points']}</b> (lifetime {u['lifetime_points']})\n"
            f"Покупок: {u['purchases_count']} (≥500: {u['purchases_count_500']}) "
            f"на {u['total_spent']} ₽\n"
            f"Реф-код: <code>{u['referral_code']}</code>\n"
            f"Создан: {fmt_dt_iso(u['created_at'])}"
        )
        kbm = kb.kb_admin_user_card(user_id)
    if isinstance(msg_or_cb, Message):
        await msg_or_cb.answer(text, reply_markup=kbm)
    else:
        await msg_or_cb.message.edit_text(text, reply_markup=kbm)


@router.callback_query(F.data.startswith("adm_pts_add:"))
async def adm_pts_add(cb: CallbackQuery, state: FSMContext):
    if not _is_admin(cb.from_user.id):
        await cb.answer()
        return
    uid = int(cb.data.split(":")[1])
    await state.set_state(Adm.pts_amount)
    await state.update_data(target=uid, op="add")
    await cb.message.answer(f"Сколько баллов начислить пользователю {uid}? (число)")
    await cb.answer()


@router.callback_query(F.data.startswith("adm_pts_sub:"))
async def adm_pts_sub(cb: CallbackQuery, state: FSMContext):
    if not _is_admin(cb.from_user.id):
        await cb.answer()
        return
    uid = int(cb.data.split(":")[1])
    await state.set_state(Adm.pts_amount)
    await state.update_data(target=uid, op="sub")
    await cb.message.answer(f"Сколько баллов списать у пользователя {uid}? (число)")
    await cb.answer()


@router.message(Adm.pts_amount)
async def adm_pts_apply(msg: Message, state: FSMContext, bot: Bot):
    if not _is_admin(msg.from_user.id):
        return
    data = await state.get_data()
    await state.clear()
    try:
        amount = int(msg.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await msg.answer("❌ Нужно положительное целое число.")
        return
    uid = data["target"]
    op = data["op"]
    try:
        if op == "add":
            new = await db.add_points(uid, amount, "admin_add", f"корректировка от @{ADMIN_ID}")
            await bot.send_message(uid, f"➕ Администратор начислил вам {amount} баллов. Баланс: {new}.")
        else:
            new = await db.spend_points(uid, amount, "admin_sub", f"корректировка от @{ADMIN_ID}")
            await bot.send_message(uid, f"➖ Администратор списал {amount} баллов. Баланс: {new}.")
    except ValueError as e:
        await msg.answer(f"❌ {e}")
        return
    except Exception as e:
        log.exception("admin pts: %s", e)
    await db.recalc_level(uid)
    await msg.answer("✅ Готово.", reply_markup=kb.kb_admin_back())


@router.callback_query(F.data.startswith("adm_age_toggle:"))
async def adm_age_toggle(cb: CallbackQuery, bot: Bot):
    if not _is_admin(cb.from_user.id):
        await cb.answer()
        return
    uid = int(cb.data.split(":")[1])
    u = await db.get_user(uid)
    new_val = not bool(u["age_verified"])
    await db.set_age_verified(uid, ADMIN_ID, new_val)
    try:
        await bot.send_message(
            uid,
            "✅ Возраст подтверждён администратором." if new_val
            else "⚠️ Подтверждение возраста снято администратором."
        )
    except Exception:
        pass
    await cb.answer("Готово")
    await _send_user_card(cb, uid)


@router.callback_query(F.data.startswith("adm_user_hist:"))
async def adm_user_hist(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        await cb.answer()
        return
    uid = int(cb.data.split(":")[1])
    rows = await db.get_history(uid, limit=30)
    if not rows:
        await cb.message.answer("История пуста.", reply_markup=kb.kb_admin_back())
        await cb.answer()
        return
    lines = [f"📜 История user <code>{uid}</code>:\n"]
    for r in rows:
        sign = "+" if r["amount"] > 0 else ""
        lines.append(f"{fmt_dt_iso(r['created_at'])} • {r['action']}: {sign}{r['amount']}"
                     + (f" — {esc(r['comment'])}" if r["comment"] else ""))
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n…обрезано"
    await cb.message.answer(text, reply_markup=kb.kb_admin_back())
    await cb.answer()


@router.callback_query(F.data == "adm_refresh_catalog")
async def adm_refresh_catalog(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        await cb.answer()
        return
    await cb.answer()
    try:
        await cb.message.edit_text("⏳ Загружаю прайс…")
        n_p = await catalog.refresh(force=True)
        await cb.message.edit_text("🔄 Нормализую категории…")
        await asyncio.sleep(0.4)
        gifts = await catalog.get_gifts()
        n_g = len(gifts)
        await cb.message.edit_text(
            f"✅ Готово: {n_p} товаров, {n_g} подарков.",
            reply_markup=kb.kb_admin_back(),
        )
    except Exception as e:
        log.exception("refresh: %s", e)
        await cb.message.edit_text(f"❌ Ошибка: <code>{esc(str(e))}</code>",
                                   reply_markup=kb.kb_admin_back())


@router.callback_query(F.data == "adm_gifts")
async def adm_gifts(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        await cb.answer()
        return
    gifts = await catalog.get_gifts()
    if not gifts:
        await cb.message.edit_text("Подарков нет.", reply_markup=kb.kb_admin_back())
        await cb.answer()
        return
    lines = ["🎁 <b>Список подарков</b>\n"]
    for g in gifts:
        lines.append(f"• <code>{esc(g['code'])}</code> — {esc(g['name'])} (L{g['min_level']}+)")
    await cb.message.edit_text("\n".join(lines), reply_markup=kb.kb_admin_back())
    await cb.answer()


@router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast(cb: CallbackQuery, state: FSMContext):
    if not _is_admin(cb.from_user.id):
        await cb.answer()
        return
    await state.set_state(Adm.broadcast_text)
    await cb.message.edit_text(
        "📢 Пришлите текст рассылки (HTML-теги поддерживаются):",
        reply_markup=kb.kb_admin_back()
    )
    await cb.answer()


@router.message(Adm.broadcast_text)
async def adm_broadcast_preview(msg: Message, state: FSMContext):
    if not _is_admin(msg.from_user.id):
        return
    await state.update_data(text=msg.html_text)
    await msg.answer("Превью:\n\n" + msg.html_text, reply_markup=kb.kb_broadcast_confirm())


@router.callback_query(F.data == "adm_bc_go")
async def adm_bc_go(cb: CallbackQuery, state: FSMContext, bot: Bot):
    if not _is_admin(cb.from_user.id):
        await cb.answer()
        return
    data = await state.get_data()
    await state.clear()
    text = data.get("text")
    if not text:
        await cb.answer("Нет текста", show_alert=True)
        return
    ids = await db.all_user_ids(only_with_notifications=True)
    await cb.message.edit_text(f"📢 Рассылка идёт ({len(ids)} получателей)…")
    ok = err = 0
    import asyncio
    for uid in ids:
        try:
            await bot.send_message(uid, text)
            ok += 1
        except Exception:
            err += 1
        await asyncio.sleep(0.05)  # ~20 msg/s
    await cb.message.answer(f"✅ Готово.\nДоставлено: {ok}\nОшибок: {err}",
                            reply_markup=kb.kb_admin_back())
