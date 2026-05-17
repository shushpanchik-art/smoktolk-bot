"""Общие фикстуры pytest: временная БД через подмену db.DB_PATH."""
import pytest_asyncio

import db


@pytest_asyncio.fixture
async def tmp_db(tmp_path, monkeypatch):
    """Временная sqlite-БД на каждый тест."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_file))
    await db.init()
    yield str(db_file)


@pytest_asyncio.fixture
async def sample_user(tmp_db):
    """Стандартный тестовый юзер: level=1, age_verified=0."""
    user = await db.create_user(
        user_id=1001,
        username="testuser",
        full_name="Test User"
    )
    return user
