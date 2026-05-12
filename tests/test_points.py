"""Тесты начисления и списания баллов (db.add_points / db.spend_points)."""
import pytest

import db


pytestmark = pytest.mark.asyncio


async def test_add_points_basic(tmp_db):
    await db.create_user(user_id=3001, username="u1", full_name="U1")
    new_balance = await db.add_points(3001, 100, "purchase")
    assert new_balance == 100
    user = await db.get_user(3001)
    assert user["points"] == 100
    assert user["lifetime_points"] == 100


async def test_add_points_accumulates(tmp_db):
    await db.create_user(user_id=3002, username="u2", full_name="U2")
    await db.add_points(3002, 50, "r1")
    await db.add_points(3002, 70, "r2", comment="bonus")
    user = await db.get_user(3002)
    assert user["points"] == 120
    assert user["lifetime_points"] == 120


async def test_spend_points_basic(tmp_db):
    await db.create_user(user_id=3003, username="u3", full_name="U3")
    await db.add_points(3003, 200, "earn")
    await db.spend_points(3003, 50, "redeem")
    user = await db.get_user(3003)
    assert user["points"] == 150
    assert user["lifetime_points"] == 200


async def test_history_records_actions(tmp_db):
    await db.create_user(user_id=3004, username="u4", full_name="U4")
    await db.add_points(3004, 100, "purchase", comment="order #1")
    await db.add_points(3004, 30, "bonus")
    history = await db.get_history(3004)
    assert len(history) >= 2
    actions = [h["action"] for h in history]
    assert "purchase" in actions
    assert "bonus" in actions


async def test_add_points_zero(tmp_db):
    await db.create_user(user_id=3005, username="u5", full_name="U5")
    balance = await db.add_points(3005, 0, "noop")
    assert balance == 0
    user = await db.get_user(3005)
    assert user["points"] == 0
