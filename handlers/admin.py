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
import product_images
from config import ADMIN_ID, LEVELS
from utils import esc, fmt_dt_iso

router = Router()
log = logging.getLogger(__name__)


class Adm(StatesGroup):
    user_search = State()
    pts_amount = State()
    broadcast_text = State()
    broadcast_test_ids = State()
    img_upload = State()


def _is_admin(uid: int) -> bool:
    return uid == ADMIN_ID


@router.callback_query(F.data == "admin_main")
async def admin_main(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        await cb.answer("Доступ запрещён", show_alert=True)
        return
    await cb.message.edit_text("🛠 <b>Админ-панель</b>", reply_markup=kb.kb_admin_main())
    await cb.answer()


@router.callback_query(F.data == "adm_backup")
async def adm_backup(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        await cb.answer("Доступ запрещён", show_alert=True)
        return
    await cb.answer()
    await cb.message.edit_text("💾 Создаю бэкап…\nПодождите несколько секунд.")
    try:
        proc = await asyncio.create_subprocess_exec(
            "/opt/smoktolk/bot/backup.sh",
            cwd="/opt/smoktolk/bot",
            env={"BOT_DIR": "/opt/smoktolk/bot", "PATH": "/usr/local/bin:/usr/bin:/bin"},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
        except asyncio.TimeoutError:
            proc.kill()
            await cb.message.edit_text(
                "⚠️ Бэкап выполняется дольше 2 минут — прерван.",
                reply_markup=kb.kb_admin_back(),
            )
            return
        out = (out_b or b"").decode("utf-8", "replace").strip()
        tail = "\n".join(out.splitlines()[-8:]) or "(нет вывода)"
        if proc.returncode == 0:
            await cb.message.edit_text(
                f"✅ <b>Бэкап создан</b>\n\n<pre>{esc(tail)}</pre>",
                reply_markup=kb.kb_admin_back(),
            )
        else:
            log.error("adm_backup: exit=%s\n%s", proc.returncode, out)
            await cb.message.edit_text(
                f"❌ <b>Ошибка бэкапа</b> (код {proc.returncode})\n\n<pre>{esc(tail)}</pre>",
                reply_markup=kb.kb_admin_back(),
            )
    except Exception as e:
        log.exception("adm_backup failed")
        await cb.message.edit_text(
            f"❌ Не удалось запустить бэкап:\n<pre>{esc(str(e))}</pre>",
            reply_markup=kb.kb_admin_back(),
        )


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
            + (f"\n\n🗑 <b>УДАЛЁН</b> ({fmt_dt_iso(u['deleted_at'])}, by {esc(str(u['deleted_by'] or '—'))})" if u["deleted_at"] else "")
        )
        kbm = kb.kb_admin_user_card(user_id, u["username"], deleted=bool(u["deleted_at"]))
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

    async def _safe_edit(text, markup=None):
        try:
            await cb.message.edit_text(text, reply_markup=markup)
        except Exception:
            pass  # "message is not modified" и т.п.

    async def _progress(stage, extra):
        if stage == "download":
            await _safe_edit("⬇️ Скачиваю прайс из Google-таблицы…")
        elif stage == "parse":
            await _safe_edit("🔄 Разбираю и нормализую товары…")
        # 'done' обрабатываем ниже вручную (нужно ещё посчитать подарки)

    try:
        await _safe_edit("⏳ Подготовка…")
        n_p = await catalog.refresh(force=True, progress=_progress)
        gifts = await catalog.get_gifts()
        n_g = len(gifts)
        await _safe_edit(
            f"✅ Готово: {n_p} товаров, {n_g} подарков.",
            markup=kb.kb_admin_back(),
        )
    except Exception as e:
        log.exception("refresh: %s", e)
        await _safe_edit(
            f"❌ Ошибка: <code>{esc(str(e))}</code>",
            markup=kb.kb_admin_back(),
        )


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
    await state.clear()
    await cb.message.edit_text(
        "📢 <b>Рассылка</b>\n\nВыберите тип:",
        reply_markup=kb.kb_broadcast_mode()
    )
    await cb.answer()


@router.callback_query(F.data == "adm_bc_mode:all")
async def adm_bc_mode_all(cb: CallbackQuery, state: FSMContext):
    if not _is_admin(cb.from_user.id):
        await cb.answer()
        return
    await state.set_state(Adm.broadcast_text)
    await state.update_data(bc_mode="all", bc_ids=None, text=None, photo=None)
    await cb.message.edit_text(
        "📢 <b>Общая рассылка</b>\n\nПришлите текст (HTML-теги поддерживаются):",
        reply_markup=kb.kb_admin_back()
    )
    await cb.answer()


@router.callback_query(F.data == "adm_bc_mode:test")
async def adm_bc_mode_test(cb: CallbackQuery, state: FSMContext):
    if not _is_admin(cb.from_user.id):
        await cb.answer()
        return
    await state.set_state(Adm.broadcast_test_ids)
    await state.update_data(bc_mode="test", text=None, photo=None)
    await cb.message.edit_text(
        "🧪 <b>Тестовая рассылка</b>\n\n"
        "Пришлите ID пользователей.\n"
        "Можно через запятую, пробел или с новой строки.\n\n"
        "Например:\n<code>12345, 67890 111213</code>",
        reply_markup=kb.kb_admin_back()
    )
    await cb.answer()


@router.message(Adm.broadcast_test_ids)
async def adm_bc_test_ids(msg: Message, state: FSMContext):
    if not _is_admin(msg.from_user.id):
        return
    import re as _re
    raw = _re.split(r"[\s,]+", (msg.text or "").strip())
    ids = []
    bad = []
    for tok in raw:
        if not tok:
            continue
        if tok.lstrip("-").isdigit():
            ids.append(int(tok))
        else:
            bad.append(tok)
    # уникальные, сохраняя порядок
    seen = set()
    ids = [x for x in ids if not (x in seen or seen.add(x))]
    if not ids:
        await msg.answer(
            "❌ Не найдено ни одного корректного ID. Попробуйте ещё раз.",
            reply_markup=kb.kb_admin_back()
        )
        return
    await state.update_data(bc_ids=ids)
    await state.set_state(Adm.broadcast_text)
    warn = f"\n⚠️ Пропущено (не число): {esc(', '.join(bad))}" if bad else ""
    await msg.answer(
        f"✅ Принято ID: <b>{len(ids)}</b>{warn}\n\n"
        "Теперь пришлите текст рассылки (HTML-теги поддерживаются):",
        reply_markup=kb.kb_admin_back()
    )


@router.message(Adm.broadcast_text)
async def adm_broadcast_preview(msg: Message, state: FSMContext):
    if not _is_admin(msg.from_user.id):
        return
    data = await state.get_data()
    mode = data.get("bc_mode", "all")
    ids = data.get("bc_ids") or []
    photo = msg.photo[-1].file_id if msg.photo else None
    text = msg.html_text if (msg.text or msg.caption) else ""
    await state.update_data(text=text, photo=photo)
    if mode == "test":
        head = f"🧪 <b>Тестовая рассылка</b> — получателей: {len(ids)}\n\n"
    else:
        head = "📢 <b>Общая рассылка</b> (всем)\n\n"
    kbd = kb.kb_broadcast_confirm(mode=mode, count=len(ids))
    if photo:
        await msg.answer_photo(photo, caption=(head + text)[:1024], reply_markup=kbd)
    else:
        await msg.answer(head + "Превью:\n\n" + text, reply_markup=kbd)


@router.callback_query(F.data == "adm_bc_go")
async def adm_bc_go(cb: CallbackQuery, state: FSMContext, bot: Bot):
    if not _is_admin(cb.from_user.id):
        await cb.answer()
        return
    data = await state.get_data()
    await state.clear()
    text = data.get("text")
    photo = data.get("photo")
    mode = data.get("bc_mode", "all")
    if not text and not photo:
        await cb.answer("Нет текста", show_alert=True)
        return
    if mode == "test":
        ids = data.get("bc_ids") or []
        if not ids:
            await cb.answer("Нет ID", show_alert=True)
            return
        label = "🧪 Тестовая рассылка"
    else:
        ids = await db.all_user_ids(only_with_notifications=True)
        label = "📢 Рассылка"
    await cb.message.edit_text(f"{label} идёт ({len(ids)} получателей)…")
    ok = err = 0
    fails = []
    for uid in ids:
        try:
            if photo:
                await bot.send_photo(uid, photo, caption=text or None)
            else:
                await bot.send_message(uid, text)
            ok += 1
        except Exception:
            err += 1
            if mode == "test":
                fails.append(uid)
        await asyncio.sleep(0.05)  # ~20 msg/s
    report = f"✅ Готово.\nДоставлено: {ok}\nОшибок: {err}"
    if mode == "test" and fails:
        report += "\n\nНе доставлено:\n" + "\n".join(f"• <code>{u}</code>" for u in fails[:30])
    await cb.message.answer(report, reply_markup=kb.kb_admin_back())


# ============== УДАЛЕНИЕ / ВОССТАНОВЛЕНИЕ ПРОФИЛЯ (админ) ==============
@router.callback_query(F.data.startswith("adm_del:"))
async def adm_del(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        return await cb.answer("Нет доступа", show_alert=True)
    uid = int(cb.data.split(":")[1])
    await cb.message.edit_text(
        f"⚠️ Точно удалить профиль <code>{uid}</code>?\n\n"
        f"Профиль будет скрыт. Баллы/уровень сохраняются 30 дней "
        f"(грейс-период), затем физически удаляются. Можно восстановить.",
        reply_markup=kb.kb_admin_del_confirm(uid),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("adm_del_no:"))
async def adm_del_no(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        return await cb.answer("Нет доступа", show_alert=True)
    uid = int(cb.data.split(":")[1])
    await _send_user_card(cb, uid)
    await cb.answer("Отменено")


@router.callback_query(F.data.startswith("adm_del_yes:"))
async def adm_del_yes(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        return await cb.answer("Нет доступа", show_alert=True)
    uid = int(cb.data.split(":")[1])
    await db.soft_delete_profile(uid, by="admin")
    await _send_user_card(cb, uid)
    await cb.answer("Профиль удалён", show_alert=True)


@router.callback_query(F.data.startswith("adm_restore:"))
async def adm_restore(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        return await cb.answer("Нет доступа", show_alert=True)
    uid = int(cb.data.split(":")[1])
    res = await db.restore_profile(uid)
    await _send_user_card(cb, uid)
    if res.get("points_lost"):
        await cb.answer("Восстановлен, но баллы уже были очищены", show_alert=True)
    else:
        await cb.answer("Профиль восстановлен", show_alert=True)


@router.callback_query(F.data == "adm_images")
async def adm_images(cb: CallbackQuery, state: FSMContext):
    if not _is_admin(cb.from_user.id):
        await cb.answer()
        return
    n = await db.count_product_images()
    await state.set_state(Adm.img_upload)
    await cb.message.edit_text(
        "\U0001F5BC Загрузка картинок продукции\n\n"
        f"Сейчас в базе: <b>{n}</b> картинок.\n\n"
        "Пришлите Excel-файл (.xlsx). В нём должны быть колонки с "
        "<b>названием товара</b> и <b>ссылкой на картинку</b> (http/https).\n"
        "Названия должны точно совпадать с названиями в каталоге.\n\n"
        "Файл полностью заменяет текущие картинки.",
        reply_markup=kb.kb_admin_back(),
    )
    await cb.answer()


@router.message(Adm.img_upload, F.document)
async def adm_images_upload(msg: Message, state: FSMContext, bot: Bot):
    if not _is_admin(msg.from_user.id):
        await state.clear()
        return
    doc = msg.document
    fname = (doc.file_name or "").lower()
    if not fname.endswith(".xlsx"):
        await msg.answer("Нужен файл .xlsx. Пришлите ещё раз или нажмите «К админке».",
                         reply_markup=kb.kb_admin_back())
        return
    await state.clear()
    status = await msg.answer("\u23F3 Скачиваю и разбираю файл…")
    tmp = f"/tmp/product_images_{msg.from_user.id}.xlsx"
    try:
        file = await bot.get_file(doc.file_id)
        await bot.download_file(file.file_path, tmp)
        pairs, stats = product_images.parse_images_xlsx(tmp)
        if not pairs:
            detail = "; ".join(stats.get("sheets_tried", [])) or "нет данных"
            await status.edit_text(
                "\u274C Не удалось найти пары «название — ссылка».\n"
                f"<code>{esc(detail)}</code>",
                reply_markup=kb.kb_admin_back(),
            )
            return
        saved = await db.set_product_images(pairs)
        # проверим сколько совпало с каталогом
        products = await catalog.get_products()
        keys = {product_images.norm_key(p.get("raw_name") or p.get("name") or "")
                for p in products}
        matched = sum(1 for k, _ in pairs if k in keys)
        await status.edit_text(
            f"\u2705 Загружено картинок: <b>{saved}</b>.\n"
            f"Совпало с товарами каталога: <b>{matched}</b> из {len(products)}.",
            reply_markup=kb.kb_admin_back(),
        )
    except Exception as e:
        log.exception("adm_images_upload failed")
        await status.edit_text(
            f"\u274C Ошибка: <code>{esc(str(e))}</code>",
            reply_markup=kb.kb_admin_back(),
        )
    finally:
        try:
            import os
            os.remove(tmp)
        except Exception:
            pass


@router.message(Adm.img_upload)
async def adm_images_wrong(msg: Message):
    await msg.answer("Пришлите Excel-файл (.xlsx) как документ.",
                     reply_markup=kb.kb_admin_back())
