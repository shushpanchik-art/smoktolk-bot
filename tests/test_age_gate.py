"""U10c / 3.2: возрастной гейт каталога и метрика start_clicks."""
import catalog_norm


def test_free_categories_open():
    assert catalog_norm.is_age_restricted("kofe") is False
    assert catalog_norm.is_age_restricted("energetiki") is False
    assert catalog_norm.is_age_restricted("glicerin") is False
    assert catalog_norm.is_age_restricted("aromatizator") is False
    assert catalog_norm.is_age_restricted("raznoe") is False


def test_restricted_categories():
    assert catalog_norm.is_age_restricted("odnorazki") is True
    assert catalog_norm.is_age_restricted("zhidkosti") is True
    assert catalog_norm.is_age_restricted("ugol") is True


def test_kb_locks_restricted_for_unverified():
    import keyboards
    kb = keyboards.kb_catalog_categories(["odnorazki", "kofe"], age_verified=False)
    data = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any(cd and cd.startswith("cat_locked:odnorazki") for cd in data)
    assert any(cd and cd.startswith("cat_cat:kofe") for cd in data)
    assert any("\U0001F512" in t for t in texts)


def test_kb_no_lock_for_verified():
    import keyboards
    kb = keyboards.kb_catalog_categories(["odnorazki", "kofe"], age_verified=True)
    data = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert any(cd and cd.startswith("cat_cat:odnorazki") for cd in data)
    assert not any(cd and cd.startswith("cat_locked:") for cd in data)
