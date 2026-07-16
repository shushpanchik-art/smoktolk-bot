"""Все inline-клавиатуры. callback_data — осмысленные, без слешей."""
import catalog_norm
from aiogram.types import (InlineKeyboardMarkup,
                           ReplyKeyboardMarkup, KeyboardButton,
    CopyTextButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import LEVELS, BOT_USERNAME, CHANNEL_URL


def kb_accept_rules() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📜 Прочитать правила", callback_data="show_rules_first")
    b.button(text="✅ Принимаю правила", callback_data="accept_rules")
    b.adjust(1)
    return b.as_markup()


def kb_share_phone() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поделиться номером", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )


def kb_main(is_admin: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="👤 Профиль", callback_data="profile_main")
    b.button(text="⭐️ Мои уровни", callback_data="levels_main")
    b.button(text="🎁 Подарки", callback_data="gifts_main")
    b.button(text="🛍 Ассортимент", callback_data="catalog_main")
    b.button(text="👥 Пригласить друга", callback_data="referral_main")
    b.button(text="🏬 Магазины", callback_data="store_address")
    b.button(text="📢 Наш канал @SMOKTOLK", url=CHANNEL_URL)
    b.button(text="📜 Правила", callback_data="rules_main")
    b.button(text="🆘 Поддержка", callback_data="support_main")
    b.button(text="💸 Списать баллы", callback_data="redeem_start")
    if is_admin:
        b.button(text="🛠 Админ-панель", callback_data="admin_main")
    b.adjust(2, 2, 2, 2, 2, 1)
    return b.as_markup()


def kb_back_main() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="« В главное меню", callback_data="back_main")
    return b.as_markup()


def kb_profile(age_verified: bool, user_id: int | None = None) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if user_id is not None:
        b.button(text=f"\U0001F4CB Скопировать ID: {user_id}", copy_text=CopyTextButton(text=str(user_id)))
    b.button(text="📜 История операций", callback_data="profile_history")
    if not age_verified:
        b.button(text="🔞 Подтвердить возраст", callback_data="verify_start")
    b.button(text="🎂 Указать день рождения", callback_data="profile_set_bday")
    b.button(text="🔔 Уведомления", callback_data="profile_toggle_notify")
    b.button(text="🗑 Удалить профиль", callback_data="profile_delete")
    b.button(text="« Назад", callback_data="back_main")
    b.adjust(1)
    return b.as_markup()


def kb_levels() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for n in sorted(LEVELS.keys()):
        b.button(text=f"L{n} • {LEVELS[n].name}", callback_data=f"level_info:{n}")
    b.button(text="« Назад", callback_data="back_main")
    b.adjust(1)
    return b.as_markup()


def kb_back_to_levels() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="« К списку уровней", callback_data="levels_main")
    b.button(text="🏠 В меню", callback_data="back_main")
    b.adjust(1)
    return b.as_markup()


def kb_gifts_list(gifts: list[dict], available_codes: set[str]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for g in gifts:
        prefix = "✅" if g["code"] in available_codes else f"🔒 L{g['min_level']}"
        b.button(text=f"{prefix} {g['name']}", callback_data=f"gift_pick:{g['code']}")
    b.button(text="« Назад", callback_data="back_main")
    b.adjust(1)
    return b.as_markup()


def kb_gift_confirm(code: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🎁 Получить подарок", callback_data=f"gift_confirm:{code}")
    b.button(text="« К списку", callback_data="gifts_main")
    b.adjust(1)
    return b.as_markup()


def kb_catalog_categories(categories: list[str]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    rows = catalog_norm.category_rows(set(categories))
    counts = []
    for row in rows:
        for c in row:
            b.button(text=catalog_norm.category_title(c), callback_data=f"cat_cat:{c}")
        counts.append(len(row))
    b.button(text="« Назад", callback_data="back_main")
    counts.append(1)
    b.adjust(*counts)
    return b.as_markup()


def kb_catalog_products(products: list[dict], category: str, page: int, total_pages: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for p in products:
        b.button(text=p['name'], callback_data=f"cat_prod:{p['sku']}")
    nav = []
    if page > 0:
        nav.append(("« Стр.", f"cat_page:{category}:{page-1}"))
    nav.append((f"{page+1}/{total_pages}", "noop"))
    if page < total_pages - 1:
        nav.append(("Стр. »", f"cat_page:{category}:{page+1}"))
    for text, cd in nav:
        b.button(text=text, callback_data=cd)
    b.button(text="« К категориям", callback_data="catalog_main")
    rows = [1] * len(products) + [len(nav), 1]
    b.adjust(*rows)
    return b.as_markup()


def kb_product_back(category: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="« К категории", callback_data=f"cat_cat:{category}")
    b.button(text="🏠 В меню", callback_data="back_main")
    b.adjust(1)
    return b.as_markup()


def kb_referral_share(ref_code: str) -> InlineKeyboardMarkup:
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{ref_code}"
    b = InlineKeyboardBuilder()
    b.button(text="📤 Поделиться", switch_inline_query=f"Заходи в SMOKTOLK: {link}")
    b.button(text="« Назад", callback_data="back_main")
    b.adjust(1)
    return b.as_markup()


def kb_verify_start() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📷 Прислать фото документа", callback_data="verify_send_photo")
    b.button(text="« Отмена", callback_data="back_main")
    b.adjust(1)
    return b.as_markup()


def kb_verify_admin(req_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Подтвердить", callback_data=f"vrf_ok:{req_id}")
    b.button(text="❌ Отклонить", callback_data=f"vrf_no:{req_id}")
    b.button(text="⚠️ Запросить ещё", callback_data=f"vrf_again:{req_id}")
    b.adjust(2, 1)
    return b.as_markup()


def kb_redeem_cancel() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="« Отмена", callback_data="back_main")
    return b.as_markup()


def kb_admin_main() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📊 Статистика", callback_data="adm_stats")
    b.button(text="📈 Отчёт за сегодня", callback_data="adm_today_report")
    b.button(text="📤 Экспорт в CSV", callback_data="adm_export")
    b.button(text="👥 Пользователи", callback_data="adm_users")
    b.button(text="✅ Заявки на верификацию", callback_data="adm_verifs")
    b.button(text="🎁 Подарки", callback_data="adm_gifts")
    b.button(text="📢 Рассылка", callback_data="adm_broadcast")
    b.button(text="🔄 Обновить ассортимент", callback_data="adm_refresh_catalog")
    b.button(text="🖼 Картинки продукции", callback_data="adm_images")
    b.button(text="💾 Создать бэкап", callback_data="adm_backup")
    b.button(text="« В меню", callback_data="back_main")
    b.adjust(3, 2, 2, 2, 1, 1)
    return b.as_markup()


def kb_admin_back() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="« К админке", callback_data="admin_main")
    return b.as_markup()


def kb_admin_user_card(user_id: int, username: str | None = None, deleted: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"\U0001F4CB Скопировать ID: {user_id}", copy_text=CopyTextButton(text=str(user_id)))
    if username:
        b.button(text="\u2709\ufe0f Написать", url=f"https://t.me/{username}")
    b.button(text="➕ Начислить", callback_data=f"adm_pts_add:{user_id}")
    b.button(text="➖ Списать", callback_data=f"adm_pts_sub:{user_id}")
    b.button(text="🎂 Изменить ДР", callback_data=f"adm_bday_set:{user_id}")
    b.button(text="🔞 Тогл возраст", callback_data=f"adm_age_toggle:{user_id}")
    b.button(text="📜 История", callback_data=f"adm_user_hist:{user_id}")
    if deleted:
        b.button(text="♻️ Восстановить", callback_data=f"adm_restore:{user_id}")
    else:
        b.button(text="🗑 Удалить профиль", callback_data=f"adm_del:{user_id}")
    b.button(text="« К поиску", callback_data="adm_users")
    if username:
        b.adjust(2, 2, 1, 1, 1, 1, 1)
    else:
        b.adjust(1, 2, 1, 1, 1, 1, 1)
    return b.as_markup()


def kb_admin_del_confirm(user_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Да, удалить", callback_data=f"adm_del_yes:{user_id}")
    b.button(text="« Отмена", callback_data=f"adm_del_no:{user_id}")
    b.adjust(1)
    return b.as_markup()


def kb_broadcast_mode() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📢 Общая (всем)", callback_data="adm_bc_mode:all")
    b.button(text="🧪 Тестовая (по ID)", callback_data="adm_bc_mode:test")
    b.button(text="« К админке", callback_data="admin_main")
    b.adjust(1)
    return b.as_markup()


def kb_broadcast_confirm(mode: str = "all", count: int = 0) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if mode == "test":
        b.button(text=f"✅ Отправить тест ({count})", callback_data="adm_bc_go")
    else:
        b.button(text="✅ Разослать всем", callback_data="adm_bc_go")
    b.button(text="« Отмена", callback_data="admin_main")
    b.adjust(1)
    return b.as_markup()


def kb_catalog_makers(makers, category):
    b = InlineKeyboardBuilder()
    for i, m in enumerate(makers):
        b.button(text=m, callback_data=f"cat_mk:{category}:{i}")
    b.button(text="« К категориям", callback_data="catalog_main")
    rows = [2] * (len(makers) // 2)
    if len(makers) % 2:
        rows.append(1)
    rows += [1]
    b.adjust(*rows)
    return b.as_markup()


def kb_maker_products(products, category, maker_idx=0, page=0, total_pages=1):
    b = InlineKeyboardBuilder()
    for p in products:
        b.button(text=p["name"], callback_data=f"cat_prod:{p['sku']}:{category}:{maker_idx}:{page}")
    nav = []
    if page > 0:
        nav.append(("« Стр.", f"cat_mkp:{category}:{maker_idx}:{page-1}"))
    if total_pages > 1:
        nav.append((f"{page+1}/{total_pages}", "noop"))
    if page < total_pages - 1:
        nav.append(("Стр. »", f"cat_mkp:{category}:{maker_idx}:{page+1}"))
    for text, cd in nav:
        b.button(text=text, callback_data=cd)
    b.button(text="« К производителям", callback_data=f"cat_cat:{category}")
    rows = [1] * len(products)
    if nav:
        rows.append(len(nav))
    rows.append(1)
    b.adjust(*rows)
    return b.as_markup()


def kb_product_card(category, maker_idx=None, page=None):
    b = InlineKeyboardBuilder()
    b.button(text="☎️ Получить консультацию", callback_data="catalog_consult")
    if maker_idx is not None and page is not None:
        back = f"cat_mkp:{category}:{maker_idx}:{page}"
    else:
        back = f"cat_cat:{category}"
    b.button(text="« К товарам", callback_data=back)
    b.adjust(1, 1)
    return b.as_markup()


def kb_delete_confirm() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Да, удалить профиль", callback_data="profile_delete_yes")
    b.button(text="« Отмена", callback_data="profile_main")
    b.adjust(1)
    return b.as_markup()


def kb_restore() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="♻️ Восстановить профиль", callback_data="profile_restore")
    b.adjust(1)
    return b.as_markup()


def kb_restore_own():
    """Кнопка восстановления собственного удалённого профиля."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="♻️ Восстановить профиль",
                              callback_data="restore_own_profile")],
    ])
