"""Unit-тесты inline/reply-клавиатур. Проверяют тип и наличие ключевых callback_data."""
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

import keyboards as kb


def _callbacks(markup: InlineKeyboardMarkup) -> set[str]:
    """Собрать все callback_data из inline-клавиатуры."""
    out = set()
    for row in markup.inline_keyboard:
        for btn in row:
            if btn.callback_data:
                out.add(btn.callback_data)
    return out


def _texts(markup: InlineKeyboardMarkup) -> set[str]:
    return {btn.text for row in markup.inline_keyboard for btn in row}


def test_kb_accept_rules():
    m = kb.kb_accept_rules()
    assert isinstance(m, InlineKeyboardMarkup)
    assert {"show_rules_first", "accept_rules"} <= _callbacks(m)


def test_kb_share_phone():
    m = kb.kb_share_phone()
    assert isinstance(m, ReplyKeyboardMarkup)
    assert m.keyboard[0][0].request_contact is True


def test_kb_main_user_vs_admin():
    user_m = kb.kb_main(is_admin=False)
    admin_m = kb.kb_main(is_admin=True)
    assert isinstance(user_m, InlineKeyboardMarkup)
    # у админа кнопок не меньше, чем у обычного пользователя
    user_cbs = _callbacks(user_m)
    admin_cbs = _callbacks(admin_m)
    assert user_cbs <= admin_cbs
    assert len(admin_cbs) >= len(user_cbs)


def test_kb_back_main():
    assert "back_main" in _callbacks(kb.kb_back_main())


def test_kb_profile_states():
    verified = kb.kb_profile(age_verified=True, user_id=1)
    not_verified = kb.kb_profile(age_verified=False, user_id=1)
    assert isinstance(verified, InlineKeyboardMarkup)
    assert isinstance(not_verified, InlineKeyboardMarkup)


def test_kb_levels():
    assert isinstance(kb.kb_levels(), InlineKeyboardMarkup)


def test_kb_back_to_levels():
    assert isinstance(kb.kb_back_to_levels(), InlineKeyboardMarkup)


def test_kb_gifts_list():
    gifts = [{"code": "g1", "name": "Подарок 1", "min_level": 1}, {"code": "g2", "name": "Подарок 2", "min_level": 2}]
    m = kb.kb_gifts_list(gifts, available_codes={"g1"})
    assert isinstance(m, InlineKeyboardMarkup)


def test_kb_gift_confirm():
    m = kb.kb_gift_confirm("g1")
    assert isinstance(m, InlineKeyboardMarkup)
    assert any("g1" in c for c in _callbacks(m))


def test_kb_verify_start():
    assert isinstance(kb.kb_verify_start(), InlineKeyboardMarkup)


def test_kb_verify_admin():
    m = kb.kb_verify_admin(42)
    assert isinstance(m, InlineKeyboardMarkup)
    assert any("42" in c for c in _callbacks(m))


def test_kb_redeem_cancel():
    assert isinstance(kb.kb_redeem_cancel(), InlineKeyboardMarkup)


def test_kb_admin_main_order():
    """Проверяем новый порядок: статистика, отчёт, экспорт идут первыми."""
    m = kb.kb_admin_main()
    assert isinstance(m, InlineKeyboardMarkup)
    cbs = _callbacks(m)
    # все ключевые пункты присутствуют
    expected = {
        "adm_stats", "adm_today_report", "adm_export", "adm_users",
        "adm_verifs", "adm_gifts", "adm_broadcast", "adm_refresh_catalog",
        "adm_backup", "back_main",
    }
    assert expected <= cbs
    # первый ряд из 3 кнопок — статистика/отчёт/экспорт
    first_row = {b.callback_data for b in m.inline_keyboard[0]}
    assert first_row == {"adm_stats", "adm_today_report", "adm_export"}


def test_kb_admin_back():
    assert isinstance(kb.kb_admin_back(), InlineKeyboardMarkup)


def test_kb_admin_user_card():
    active = kb.kb_admin_user_card(user_id=7, username="user", deleted=False)
    deleted = kb.kb_admin_user_card(user_id=7, username="user", deleted=True)
    assert isinstance(active, InlineKeyboardMarkup)
    assert isinstance(deleted, InlineKeyboardMarkup)


def test_kb_admin_del_confirm():
    m = kb.kb_admin_del_confirm(7)
    assert isinstance(m, InlineKeyboardMarkup)
    assert any("7" in c for c in _callbacks(m))


def test_kb_broadcast_confirm():
    assert isinstance(kb.kb_broadcast_confirm(), InlineKeyboardMarkup)


def test_kb_delete_confirm():
    assert isinstance(kb.kb_delete_confirm(), InlineKeyboardMarkup)


def test_kb_restore():
    assert isinstance(kb.kb_restore(), InlineKeyboardMarkup)
