"""Тесты: ДР указывается один раз, перезапись только force=True (admin)."""
import os
import tempfile
import importlib
import pytest


@pytest.fixture
async def fresh_db(monkeypatch):
    """Свежая SQLite в temp-файле + reload модулей db и config."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()

    # config.DB_PATH читается на этапе import db, поэтому подменяем
    # и перезагружаем оба модуля.
    import config as _cfg
    monkeypatch.setattr(_cfg, "DB_PATH", tmp.name, raising=True)

    import db as _db
    importlib.reload(_db)  # пересчитает `from config import DB_PATH`
    await _db.init_db()

    yield _db

    try:
        os.unlink(tmp.name)
    except OSError:
        pass


@pytest.mark.asyncio
async def test_birthday_can_be_set_once(fresh_db):
    db = fresh_db
    await db.create_user(user_id=111, username="x", full_name="X")
    await db.set_birthday(111, "1990-03-15")
    u = await db.get_user(111)
    assert u["birthday"] == "1990-03-15"


@pytest.mark.asyncio
async def test_birthday_second_set_rejected(fresh_db):
    db = fresh_db
    await db.create_user(user_id=222, username="y", full_name="Y")
    await db.set_birthday(222, "1990-03-15")
    with pytest.raises(db.BirthdayAlreadySetError):
        await db.set_birthday(222, "1991-04-16")
    u = await db.get_user(222)
    assert u["birthday"] == "1990-03-15"


@pytest.mark.asyncio
async def test_birthday_admin_force_overwrites(fresh_db):
    db = fresh_db
    await db.create_user(user_id=333, username="z", full_name="Z")
    await db.set_birthday(333, "1990-03-15")
    await db.set_birthday(333, "1991-04-16", force=True)
    u = await db.get_user(333)
    assert u["birthday"] == "1991-04-16"
