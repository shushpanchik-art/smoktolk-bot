"""U10c: bump_daily('start_clicks') инкрементит колонку в daily_stats."""
import datetime
import pytest
import db


@pytest.mark.asyncio
async def test_start_clicks_bump(tmp_db):
    await db.bump_daily("start_clicks")
    await db.bump_daily("start_clicks")
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    d = await db.get_daily(today)
    assert d["start_clicks"] == 2


@pytest.mark.asyncio
async def test_get_daily_default_has_start_clicks(tmp_db):
    d = await db.get_daily("1999-01-01")
    assert d["start_clicks"] == 0
