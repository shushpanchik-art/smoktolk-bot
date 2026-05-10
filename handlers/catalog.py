"""Просмотр ассортимента из Excel: категории → товары → карточка."""
from aiogram import Router, F
from aiogram.types import CallbackQuery

import catalog
import keyboards as kb
from utils import esc

router = Router()
PAGE_SIZE = 8


@router.callback_query(F.data == "catalog_main")
async def catalog_main(cb: CallbackQuery):
    products = await catalog.get_products()
    if not products:
        await cb.message.edit_text("🛍 Ассортимент пока не загружен.",
                                   reply_markup=kb.kb_back_main())
        await cb.answer()
        return
    cats = sorted({p["category"] for p in products})
    text = (
        "🛍 <b>Ассортимент</b>\n\n"
        "Цены и наличие — для информации. Покупка только в магазине.\n\n"
        "Выберите категорию:"
    )
    await cb.message.edit_text(text, reply_markup=kb.kb_catalog_categories(cats))
    await cb.answer()


@router.callback_query(F.data.startswith("cat_cat:"))
async def cat_category(cb: CallbackQuery):
    cat = cb.data.split(":", 1)[1]
    await _show_page(cb, cat, 0)


@router.callback_query(F.data.startswith("cat_page:"))
async def cat_page(cb: CallbackQuery):
    _, cat, page = cb.data.split(":")
    await _show_page(cb, cat, int(page))


async def _show_page(cb: CallbackQuery, cat: str, page: int):
    products = sorted(
        [p for p in await catalog.get_products() if p["category"] == cat],
        key=lambda x: x["name"].lower(),
    )
    if not products:
        await cb.answer("В этой категории пусто", show_alert=True)
        return
    total_pages = max(1, (len(products) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = products[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    text = f"<b>{esc(cat.capitalize())}</b> — {len(products)} товаров"
    await cb.message.edit_text(
        text, reply_markup=kb.kb_catalog_products(chunk, cat, page, total_pages)
    )
    await cb.answer()


@router.callback_query(F.data.startswith("cat_prod:"))
async def cat_product(cb: CallbackQuery):
    sku = cb.data.split(":", 1)[1]
    p = await catalog.get_product(sku)
    if not p:
        await cb.answer("Товар не найден", show_alert=True)
        return
    text = (
        f"<b>{esc(p['name'])}</b>\n\n"
        f"Категория: {esc(p['category'])}\n"
        f"Цена: <b>{p['price']} ₽</b>\n"
        f"Наличие: {esc(p.get('stock', 'уточняйте'))}\n\n"
        f"{esc(p.get('description', ''))}"
        f"\n\n<i>Покупка только в магазине после проверки документа (для 18+ категорий).</i>"
    )
    await cb.message.edit_text(text, reply_markup=kb.kb_product_back(p["category"]))
    await cb.answer()


@router.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery):
    await cb.answer()
