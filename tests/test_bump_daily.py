"""Тесты для db.bump_daily — счётчики дневной статистики."""
import pytest
from datetime import datetime, timezone

import db


pytestmark = pytest.mark.asyncio


async def test_bump_daily_creates_row_for_today(tmp_db):
    await db.bump_daily("new_users")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stats = await db.get_daily(today)
    assert stats["new_users"] == 1


async def test_bump_daily_increments_existing(tmp_db):
    await db.bump_daily("new_users")
    await db.bump_daily("new_users")
    await db.bump_daily("new_users")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stats = await db.get_daily(today)
    assert stats["new_users"] == 3


async def test_bump_daily_custom_delta(tmp_db):
    await db.bump_daily("purchases_sum", delta=500)
    await db.bump_daily("purchases_sum", delta=1500)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stats = await db.get_daily(today)
    assert stats["purchases_sum"] == 2000


async def test_bump_daily_custom_date(tmp_db):
    await db.bump_daily("new_users", date="2025-01-15")
    stats = await db.get_daily("2025-01-15")
    assert stats["new_users"] == 1
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_stats = await db.get_daily(today)
    assert today_stats["new_users"] == 0


async def test_bump_daily_invalid_field_silently_ignored(tmp_db):
    await db.bump_daily("__evil_field__")
    await db.bump_daily("DROP TABLE users")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stats = await db.get_daily(today)
    assert stats["new_users"] == 0
    assert stats["purchases_count"] == 0


async def test_bump_daily_independent_fields(tmp_db):
    await db.bump_daily("new_users", delta=2)
    await db.bump_daily("purchases_count", delta=5)
    await db.bump_daily("points_earned", delta=100)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stats = await db.get_daily(today)
    assert stats["new_users"] == 2
    assert stats["purchases_count"] == 5
    assert stats["points_earned"] == 100
    assert stats["points_spent"] == 0
