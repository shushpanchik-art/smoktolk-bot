"""Тесты пересчёта уровня лояльности (db.recalc_level).

Логика recalc_level (db.py:329):
  - level=1, если age_verified == 0 (база, до подтверждения возраста);
  - иначе level=2 (база для верифицированных);
  - level повышается до 3/4/5, если ИЛИ lifetime_points >= порога,
    ИЛИ purchases_count_500 >= порога. Перебор от 5 к 3 (берётся самый высокий
    из достижимых уровней).

Пороги (из config.LEVELS):
    L3: 1500 баллов / 15 покупок ≥500 ₽
    L4: 4000 баллов / 40 покупок ≥500 ₽
    L5: 8000 баллов / 80 покупок ≥500 ₽

Тонкость: db.set_age_verified сам вызывает recalc_level. Чтобы тестировать
recalc_level изолированно, мы либо подготавливаем БД через высокоуровневые
функции и затем явно вызываем recalc_level, либо патчим поля напрямую через
aiosqlite (для случаев, где нужно жёстко зафиксировать состояние).
"""
import aiosqlite
import pytest

import db


pytestmark = pytest.mark.asyncio

ADMIN_ID = 1


async def _set_fields(user_id: int, **fields):
    """Прямая запись произвольных полей users (для подготовки сценариев)."""
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [user_id]
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(f"UPDATE users SET {sets} WHERE user_id=?", values)
        await conn.commit()


async def test_recalc_level_unverified_stays_L1(tmp_db):
    """Неверифицированный возраст → level=1, даже если баллы выше порога L5."""
    await db.create_user(user_id=5001, username="u", full_name="U")
    # Накачиваем lifetime_points выше любого порога — но age_verified=0.
    await _set_fields(5001, lifetime_points=99999, purchases_count_500=100)
    lvl = await db.recalc_level(5001)
    assert lvl == 1
    user = await db.get_user(5001)
    assert user["level"] == 1


async def test_recalc_level_verified_no_progress_is_L2(tmp_db):
    """Возраст подтверждён, прогресса нет → level=2."""
    await db.create_user(user_id=5002, username="u", full_name="U")
    await db.set_age_verified(5002, ADMIN_ID, True)
    # set_age_verified уже вызвал recalc_level. Перепроверим явно.
    lvl = await db.recalc_level(5002)
    assert lvl == 2
    user = await db.get_user(5002)
    assert user["level"] == 2


async def test_recalc_level_promotes_to_L3_by_points(tmp_db):
    """lifetime_points = 1500 (порог L3) → level=3."""
    await db.create_user(user_id=5003, username="u", full_name="U")
    await db.set_age_verified(5003, ADMIN_ID, True)
    await _set_fields(5003, lifetime_points=1500)
    lvl = await db.recalc_level(5003)
    assert lvl == 3


async def test_recalc_level_promotes_to_L3_by_purchases(tmp_db):
    """purchases_count_500 = 15 (порог L3) → level=3, даже при 0 баллов."""
    await db.create_user(user_id=5004, username="u", full_name="U")
    await db.set_age_verified(5004, ADMIN_ID, True)
    await _set_fields(5004, lifetime_points=0, purchases_count_500=15)
    lvl = await db.recalc_level(5004)
    assert lvl == 3


async def test_recalc_level_promotes_to_L4(tmp_db):
    """lifetime_points = 4000 (порог L4) → level=4."""
    await db.create_user(user_id=5005, username="u", full_name="U")
    await db.set_age_verified(5005, ADMIN_ID, True)
    await _set_fields(5005, lifetime_points=4000)
    lvl = await db.recalc_level(5005)
    assert lvl == 4


async def test_recalc_level_promotes_to_L5_by_points(tmp_db):
    """lifetime_points = 8000 (порог L5) → level=5."""
    await db.create_user(user_id=5006, username="u", full_name="U")
    await db.set_age_verified(5006, ADMIN_ID, True)
    await _set_fields(5006, lifetime_points=8000)
    lvl = await db.recalc_level(5006)
    assert lvl == 5


async def test_recalc_level_picks_highest_threshold(tmp_db):
    """lifetime_points сильно выше L5 → не застревает на L3/L4, выдаёт L5."""
    await db.create_user(user_id=5007, username="u", full_name="U")
    await db.set_age_verified(5007, ADMIN_ID, True)
    await _set_fields(5007, lifetime_points=10000, purchases_count_500=100)
    lvl = await db.recalc_level(5007)
    assert lvl == 5


async def test_recalc_level_nonexistent_user_returns_1(tmp_db):
    """recalc_level для несуществующего user_id → 1 (early return, без падений)."""
    lvl = await db.recalc_level(999999)
    assert lvl == 1
    user = await db.get_user(999999)
    assert user is None  # пользователь не создаётся


async def test_recalc_level_does_not_demote_inside_verified_range(tmp_db):
    """Тонкий контракт: если юзер уже L4, а пороги L4 (по points/purchases) не достигнуты,
    функция всё равно НЕ опустит ниже L2 (это инвариант verified-юзера).

    Текущая реализация: для verified юзера база = 2, далее перебор 5→4→3.
    Если ни один порог не достигнут — останется L2.
    Это фиксирует поведение: «понижение» возможно (например, после ручной корректировки).
    """
    await db.create_user(user_id=5008, username="u", full_name="U")
    await db.set_age_verified(5008, ADMIN_ID, True)
    # Сначала повысим до L4
    await _set_fields(5008, lifetime_points=4000)
    assert await db.recalc_level(5008) == 4
    # Теперь "сбросим" прогресс — должен вернуться к L2
    await _set_fields(5008, lifetime_points=0, purchases_count_500=0)
    assert await db.recalc_level(5008) == 2
