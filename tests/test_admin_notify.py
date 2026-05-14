"""Тесты services.admin_notify: формат и устойчивость к сбоям."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from aiogram.exceptions import TelegramAPIError

from services import admin_notify
from services.admin_notify import (
    _fmt_user,
    _fmt_referrer,
    notify_admin_new_user,
)


def test_fmt_user_with_username():
    u = {"user_id": 123, "full_name": "Иван Иванов", "username": "ivan"}
    text = _fmt_user(u)
    assert "Иван Иванов" in text
    assert "@ivan" in text
    assert "<code>123</code>" in text
    assert "Новый пользователь" in text


def test_fmt_user_without_username():
    u = {"user_id": 456, "full_name": "Без юзернейма", "username": None}
    text = _fmt_user(u)
    assert "без username" in text
    assert "<code>456</code>" in text


def test_fmt_user_html_escape():
    u = {"user_id": 1, "full_name": "<script>alert(1)</script>", "username": "x&y"}
    text = _fmt_user(u)
    assert "<script>" not in text
    assert "&lt;script&gt;" in text
    assert "x&amp;y" in text


def test_fmt_referrer_none():
    assert _fmt_referrer(None) == "—"


def test_fmt_referrer_with_data():
    r = {"user_id": 999, "full_name": "Реферер", "username": "ref"}
    text = _fmt_referrer(r)
    assert "Реферер" in text
    assert "@ref" in text
    assert "<code>999</code>" in text


@pytest.mark.asyncio
async def test_notify_admin_new_user_calls_send_message(monkeypatch):
    monkeypatch.setattr(admin_notify, "ADMIN_ID", 777)
    bot = MagicMock()
    bot.send_message = AsyncMock()

    user = {"user_id": 100, "full_name": "Test", "username": "tu"}
    ok = await notify_admin_new_user(bot, user, referrer=None)

    assert ok is True
    bot.send_message.assert_awaited_once()
    args, kwargs = bot.send_message.call_args
    assert args[0] == 777
    assert "Test" in args[1]
    assert "@tu" in args[1]
    assert "Реферер: —" in args[1]
    assert kwargs.get("parse_mode") == "HTML"


@pytest.mark.asyncio
async def test_notify_admin_new_user_with_referrer(monkeypatch):
    monkeypatch.setattr(admin_notify, "ADMIN_ID", 777)
    bot = MagicMock()
    bot.send_message = AsyncMock()

    user = {"user_id": 100, "full_name": "Newbie", "username": None}
    ref = {"user_id": 50, "full_name": "Old", "username": "old"}

    await notify_admin_new_user(bot, user, referrer=ref)

    text = bot.send_message.call_args[0][1]
    assert "Old" in text
    assert "@old" in text
    assert "<code>50</code>" in text


@pytest.mark.asyncio
async def test_notify_admin_swallows_telegram_error(monkeypatch):
    monkeypatch.setattr(admin_notify, "ADMIN_ID", 777)
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=TelegramAPIError(
        method=MagicMock(), message="forbidden"
    ))

    user = {"user_id": 1, "full_name": "X", "username": None}
    ok = await notify_admin_new_user(bot, user)
    assert ok is False


@pytest.mark.asyncio
async def test_notify_admin_empty_user(monkeypatch):
    monkeypatch.setattr(admin_notify, "ADMIN_ID", 777)
    bot = MagicMock()
    bot.send_message = AsyncMock()
    ok = await notify_admin_new_user(bot, {})
    bot.send_message.assert_not_awaited()
    assert ok is False
