"""Просмотр ассортимента: категории - производители - товары - карточка."""
from aiogram import Router, F
from aiogram.types import CallbackQuery
import catalog
import keyboards as kb
import catalog_norm
import db
import product_images as _pimg
from utils import esc
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()


async def _edit_or_send(cb, text, reply_markup):
    """edit_text; если текущее сообщение — фото/нельзя редактировать, удалить и отправить новое."""
    try:
        await cb.message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        try:
            await cb.message.delete()
        except Exception:
            pass
        await cb.message.answer(text, reply_markup=reply_markup)


def _sorted_makers(products):
    s = {(p.get("manufacturer") or "Прочее").strip() or "Прочее" for p in products}
    return sorted(s, key=lambda x: x.lower())


@router.callback_query(F.data == "catalog_main")
async def catalog_main(cb: CallbackQuery):
    products = await catalog.get_products()
    if not products:
        await _edit_or_send(cb, "Ассортимент пока не загружен.", kb.kb_back_main())
        await cb.answer()
        return
    cats = sorted({p["category"] for p in products})
    user = await db.get_user(cb.from_user.id)
    age_ok = bool(user and user["age_verified"])
    text = "<b>Ассортимент</b>\n\nЦены и наличие - для информации.\n\nВыберите категорию:"
    await _edit_or_send(cb, text, kb.kb_catalog_categories(cats, age_verified=age_ok))
    await cb.answer()


@router.callback_query(F.data.startswith("cat_cat:"))
async def cat_category(cb: CallbackQuery):
    cat = cb.data.split(":", 1)[1]
    if catalog_norm.is_age_restricted(cat):
        user = await db.get_user(cb.from_user.id)
        if not (user and user["age_verified"]):
            await cb.answer("🔞 Раздел 18+. Нужно подтвердить возраст.", show_alert=True)
            return
    products = [p for p in await catalog.get_products() if p["category"] == cat]
    if not products:
        await cb.answer("В этой категории пусто", show_alert=True)
        return
    makers = _sorted_makers(products)
    title = catalog_norm.category_title(cat)
    text = f"<b>{esc(title)}</b>\n\nВыберите производителя:"
    await _edit_or_send(cb, text, kb.kb_catalog_makers(makers, cat))
    await cb.answer()


MAKER_PER_PAGE = 7


async def _show_maker(cb, cat, idx, page):
    all_in_cat = [p for p in await catalog.get_products() if p["category"] == cat]
    makers = _sorted_makers(all_in_cat)
    if idx < 0 or idx >= len(makers):
        await cb.answer("Производитель не найден", show_alert=True)
        return
    maker = makers[idx]
    products = sorted(
        [p for p in all_in_cat if ((p.get("manufacturer") or "Прочее").strip() or "Прочее") == maker],
        key=lambda x: x["name"].lower(),
    )
    total_pages = max(1, (len(products) + MAKER_PER_PAGE - 1) // MAKER_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    chunk = products[page * MAKER_PER_PAGE:(page + 1) * MAKER_PER_PAGE]
    title = catalog_norm.category_title(cat)
    text = f"<b>{esc(maker)}</b>\n<i>{esc(title)}</i>\n\nВыберите товар:"
    await _edit_or_send(cb, text, kb.kb_maker_products(chunk, cat, idx, page, total_pages))
    await cb.answer()


@router.callback_query(F.data.startswith("cat_mk:"))
async def cat_maker(cb: CallbackQuery):
    _, cat, idx = cb.data.split(":")
    await _show_maker(cb, cat, int(idx), 0)


@router.callback_query(F.data.startswith("cat_mkp:"))
async def cat_maker_page(cb: CallbackQuery):
    _, cat, idx, page = cb.data.split(":")
    await _show_maker(cb, cat, int(idx), int(page))


@router.callback_query(F.data.startswith("cat_prod:"))
async def cat_product(cb: CallbackQuery):
    parts = cb.data.split(":")
    sku = parts[1]
    bk_idx = int(parts[3]) if len(parts) > 3 else None
    bk_page = int(parts[4]) if len(parts) > 4 else None
    p = await catalog.get_product(sku)
    if not p:
        await cb.answer("Товар не найден", show_alert=True)
        return
    cat = p["category"]
    maker = (p.get("manufacturer") or "Прочее").strip() or "Прочее"
    lines = [f"<b>{esc(p['name'])}</b>", ""]
    lines.append(f"Производитель: {esc(maker)}")
    if p.get("price"):
        lines.append(f"Цена: {esc(str(p['price']))} ₽")
    st = p.get("stock")
    try:
        st_val = float(st)
    except (TypeError, ValueError):
        st_val = None
    if st_val is not None and st_val > 0:
        lines.append("✅ В наличии")
    else:
        lines.append("⏳ Ожидается поступление")
    if p.get("description"):
        lines += ["", esc(str(p["description"]))]
    text = "\n".join(lines)
    markup = kb.kb_product_card(cat, bk_idx, bk_page)
    img = await db.get_product_image(_pimg.norm_key(p.get("raw_name", "")))
    if img:
        try:
            await cb.message.delete()
        except Exception:
            pass
        try:
            await cb.message.answer_photo(img, caption=text, reply_markup=markup)
        except Exception:
            await cb.message.answer(text, reply_markup=markup)
    else:
        try:
            await cb.message.edit_text(text, reply_markup=markup)
        except Exception:
            try:
                await cb.message.delete()
            except Exception:
                pass
            await cb.message.answer(text, reply_markup=markup)
    await cb.answer()


@router.callback_query(F.data == "catalog_consult")
async def catalog_consult(cb: CallbackQuery):
    from config import SUPPORT_TEXT
    b = InlineKeyboardBuilder()
    b.button(text="« В каталог", callback_data="catalog_main")
    b.adjust(1)
    await _edit_or_send(cb, SUPPORT_TEXT, b.as_markup())
    await cb.answer()

@router.callback_query(F.data == "noop")
async def cat_noop(cb: CallbackQuery):
    await cb.answer()


@router.callback_query(F.data.startswith("cat_locked:"))
async def cat_locked(cb: CallbackQuery):
    text = (
        "🔞 <b>Раздел 18+</b>\n\n"
        "Этот раздел доступен после подтверждения возраста.\n"
        "Нажмите кнопку ниже, чтобы пройти верификацию."
    )
    b = InlineKeyboardBuilder()
    b.button(text="📷 Подтвердить возраст", callback_data="verify_start")
    b.button(text="« В каталог", callback_data="catalog_main")
    b.adjust(1)
    await _edit_or_send(cb, text, b.as_markup())
    await cb.answer()
