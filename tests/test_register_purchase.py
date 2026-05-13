"""Тесты для регистрации покупок (db.register_purchase, db.purchase_exists).

Покрывают:
- базовую запись в purchases + обновление счётчиков users;
- логику purchases_count_500 (>= 500 ₽ — границы);
- накопление по нескольким покупкам;
- возврат purchase_id;
- индикатор purchase_exists после регистрации;
- уникальность receipt_id (UNIQUE constraint).
"""
import json

import pytest

import db


pytestmark = pytest.mark.asyncio


async def _make_user(user_id: int = 4001):
    """Хелпер: создать юзера и вернуть его словарь."""
    return await db.create_user(
        user_id=user_id, username=f"u{user_id}", full_name=f"User {user_id}"
    )


async def test_register_purchase_basic(tmp_db):
    """Чек на 1000 ₽: запись в purchases + апдейт счётчиков users."""
    await _make_user(4001)
    purchase_id = await db.register_purchase(
        user_id=4001,
        receipt_id="receipt-001",
        amount_rub=1000,
        points_earned=100,
        categories_json=json.dumps([{"category": "liquid", "amount": 1000}]),
        raw_payload_json=json.dumps({"source": "test"}),
    )
    assert purchase_id > 0

    user = await db.get_user(4001)
    assert user["total_spent"] == 1000
    assert user["purchases_count"] == 1
    assert user["purchases_count_500"] == 1  # 1000 >= 500
    assert user["last_purchase_date"] is not None
    assert user["last_activity"] is not None


async def test_register_purchase_below_500_does_not_bump_500_counter(tmp_db):
    """Чек на 499 ₽: purchases_count++, но purchases_count_500 НЕ растёт."""
    await _make_user(4002)
    await db.register_purchase(
        user_id=4002,
        receipt_id="receipt-002",
        amount_rub=499,
        points_earned=49,
        categories_json="[]",
        raw_payload_json="{}",
    )
    user = await db.get_user(4002)
    assert user["total_spent"] == 499
    assert user["purchases_count"] == 1
    assert user["purchases_count_500"] == 0


async def test_register_purchase_exactly_500_bumps_500_counter(tmp_db):
    """Граничный случай: чек ровно на 500 ₽ → purchases_count_500 += 1."""
    await _make_user(4003)
    await db.register_purchase(
        user_id=4003,
        receipt_id="receipt-003",
        amount_rub=500,
        points_earned=50,
        categories_json="[]",
        raw_payload_json="{}",
    )
    user = await db.get_user(4003)
    assert user["purchases_count"] == 1
    assert user["purchases_count_500"] == 1


async def test_register_purchase_accumulates(tmp_db):
    """Две покупки (700 + 300): total=1000, count=2, count_500=1."""
    await _make_user(4004)
    await db.register_purchase(
        user_id=4004, receipt_id="r-700", amount_rub=700,
        points_earned=70, categories_json="[]", raw_payload_json="{}",
    )
    await db.register_purchase(
        user_id=4004, receipt_id="r-300", amount_rub=300,
        points_earned=30, categories_json="[]", raw_payload_json="{}",
    )
    user = await db.get_user(4004)
    assert user["total_spent"] == 1000
    assert user["purchases_count"] == 2
    assert user["purchases_count_500"] == 1  # только 700, не 300


async def test_register_purchase_returns_distinct_ids(tmp_db):
    """Каждая регистрация возвращает уникальный положительный rowid."""
    await _make_user(4005)
    id1 = await db.register_purchase(
        user_id=4005, receipt_id="rid-a", amount_rub=600,
        points_earned=60, categories_json="[]", raw_payload_json="{}",
    )
    id2 = await db.register_purchase(
        user_id=4005, receipt_id="rid-b", amount_rub=800,
        points_earned=80, categories_json="[]", raw_payload_json="{}",
    )
    assert id1 > 0
    assert id2 > 0
    assert id1 != id2


async def test_purchase_exists_after_register(tmp_db):
    """purchase_exists возвращает True для зарегистрированного чека, False для прочих."""
    await _make_user(4006)
    assert await db.purchase_exists("does-not-exist") is False

    await db.register_purchase(
        user_id=4006, receipt_id="receipt-xyz", amount_rub=550,
        points_earned=55, categories_json="[]", raw_payload_json="{}",
    )
    assert await db.purchase_exists("receipt-xyz") is True
    assert await db.purchase_exists("other-receipt") is False


async def test_register_purchase_duplicate_receipt_raises(tmp_db):
    """UNIQUE-constraint на receipt_id: повторная регистрация падает.

    Защита от двойного начисления по одному чеку гарантируется именно тем,
    что в webhook.py перед вызовом register_purchase проверяется purchase_exists.
    Этот тест фиксирует контракт: на уровне БД дубликат отвергается.
    """
    import aiosqlite

    await _make_user(4007)
    await db.register_purchase(
        user_id=4007, receipt_id="dup-1", amount_rub=600,
        points_earned=60, categories_json="[]", raw_payload_json="{}",
    )
    with pytest.raises(aiosqlite.IntegrityError):
        await db.register_purchase(
            user_id=4007, receipt_id="dup-1", amount_rub=999,
            points_earned=99, categories_json="[]", raw_payload_json="{}",
        )
