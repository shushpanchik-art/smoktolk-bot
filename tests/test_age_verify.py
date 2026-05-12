"""Тесты для верификации возраста (db.set_age_verified)."""
import pytest

import db


pytestmark = pytest.mark.asyncio

ADMIN_ID = 1


async def test_new_user_not_verified(tmp_db):
    user = await db.create_user(user_id=2001, username="newbie", full_name="Newbie")
    assert user["age_verified"] == 0


async def test_set_age_verified_true(tmp_db):
    await db.create_user(user_id=2002, username="adult", full_name="Adult")
    await db.set_age_verified(2002, ADMIN_ID, True)
    user = await db.get_user(2002)
    assert user["age_verified"] == 1
    assert user["age_verified_by"] == ADMIN_ID
    assert user["age_verified_at"] is not None


async def test_set_age_verified_false_revokes(tmp_db):
    await db.create_user(user_id=2003, username="kid", full_name="Kid")
    await db.set_age_verified(2003, ADMIN_ID, True)
    await db.set_age_verified(2003, ADMIN_ID, False)
    user = await db.get_user(2003)
    assert user["age_verified"] == 0
    assert user["age_verified_at"] is None


async def test_set_age_verified_nonexistent_user(tmp_db):
    await db.set_age_verified(9999, ADMIN_ID, True)
    user = await db.get_user(9999)
    assert user is None


async def test_age_verified_persists_after_points(tmp_db):
    await db.create_user(user_id=2004, username="persist", full_name="Persist")
    await db.set_age_verified(2004, ADMIN_ID, True)
    await db.add_points(2004, 50, "test")
    user = await db.get_user(2004)
    assert user["age_verified"] == 1
    assert user["points"] == 50


async def test_set_age_verified_records_admin(tmp_db):
    await db.create_user(user_id=2005, username="auditme", full_name="AuditMe")
    await db.set_age_verified(2005, admin_id=777, value=True)
    user = await db.get_user(2005)
    assert user["age_verified_by"] == 777
