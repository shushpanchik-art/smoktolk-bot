"""Soft-delete профиля: миграция + функции удаления/восстановления/очистки.

Импортируется в db.py. Все функции работают с тем же DB_PATH.
Алгоритм:
  1. Пользователь/админ инициирует удаление -> soft_delete_profile()
     (deleted_at = now, deleted_by = 'user'/'admin'). Баллы/уровень/покупки живы.
  2. Восстановление в любой момент до purge -> restore_profile().
  3. День +29: warn_before_purge_candidates() -> уведомление, флаг warned=1.
  4. День +30: purge_expired_profiles() -> обнуляем баллы/уровень/уведомления,
     сбрасываем rules_accepted_at. Сохраняем ФИО/phone/birthday/age_verified/покупки.
"""
import logging
from datetime import datetime, timezone, timedelta

import aiosqlite

log = logging.getLogger(__name__)

GRACE_DAYS = 30          # через сколько дней стираются баллы
WARN_DAYS = 29           # на какой день слать предупреждение

# новые колонки: имя -> SQL-определение для ALTER TABLE ADD COLUMN
_NEW_COLUMNS = {
    "deleted_at": "TEXT",
    "deleted_by": "TEXT",
    "purged_at": "TEXT",
    "warned_before_purge": "INTEGER DEFAULT 0",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def migrate_deletion_columns(db_path: str):
    """Идемпотентно добавляет колонки soft-delete в users, если их нет."""
    async with aiosqlite.connect(db_path) as conn:
        cur = await conn.execute("PRAGMA table_info(users)")
        existing = {row[1] for row in await cur.fetchall()}
        added = []
        for col, decl in _NEW_COLUMNS.items():
            if col not in existing:
                await conn.execute(f"ALTER TABLE users ADD COLUMN {col} {decl}")
                added.append(col)
        if added:
            await conn.commit()
            log.info("Deletion migration: added columns %s", added)


async def soft_delete_profile(db_path: str, user_id: int, by: str = "user"):
    """Помечает профиль на удаление. by = 'user' | 'admin'.
    Баллы/уровень/покупки НЕ трогаем — грейс-период GRACE_DAYS дней."""
    now = _now()
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "UPDATE users SET deleted_at=?, deleted_by=?, purged_at=NULL, "
            "warned_before_purge=0 WHERE user_id=?",
            (now, by, user_id),
        )
        await conn.execute(
            "INSERT INTO history (user_id, action, amount, comment, created_at) "
            "VALUES (?,?,?,?,?)",
            (user_id, "profile_delete", 0, f"инициировано: {by}", now),
        )
        await conn.commit()
    log.info("Profile %s soft-deleted by %s", user_id, by)


async def restore_profile(db_path: str, user_id: int) -> dict:
    """Восстанавливает профиль. Возвращает {'points_lost': bool}.
    Если purge уже был — баллы не вернуть (points_lost=True)."""
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT purged_at FROM users WHERE user_id=?", (user_id,)
        )
        row = await cur.fetchone()
        points_lost = bool(row and row["purged_at"])
        now = _now()
        await conn.execute(
            "UPDATE users SET deleted_at=NULL, deleted_by=NULL, "
            "warned_before_purge=0 WHERE user_id=?",
            (user_id,),
        )
        await conn.execute(
            "INSERT INTO history (user_id, action, amount, comment, created_at) "
            "VALUES (?,?,?,?,?)",
            (user_id, "profile_restore", 0,
             "после очистки баллов" if points_lost else "в грейс-период", now),
        )
        await conn.commit()
    log.info("Profile %s restored (points_lost=%s)", user_id, points_lost)
    return {"points_lost": points_lost}


async def warn_before_purge_candidates(db_path: str) -> list[int]:
    """Возвращает user_id, которым пора слать уведомление дня +WARN_DAYS
    (deleted_at достиг WARN_DAYS, ещё не предупреждён, ещё не очищен).
    Помечает их warned_before_purge=1, чтобы не слать повторно."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=WARN_DAYS)).isoformat()
    ids: list[int] = []
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT user_id FROM users WHERE deleted_at IS NOT NULL "
            "AND purged_at IS NULL AND warned_before_purge=0 AND deleted_at<=?",
            (cutoff,),
        )
        ids = [r["user_id"] for r in await cur.fetchall()]
        if ids:
            await conn.executemany(
                "UPDATE users SET warned_before_purge=1 WHERE user_id=?",
                [(i,) for i in ids],
            )
            await conn.commit()
    return ids


async def purge_expired_profiles(db_path: str) -> int:
    """Очищает баллы/уровень/уведомления у профилей, прошедших GRACE_DAYS.
    Сохраняет ФИО/phone/birthday/age_verified/покупки/историю.
    Сбрасывает rules_accepted_at (правила принять заново). Идемпотентно."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=GRACE_DAYS)).isoformat()
    purged = 0
    now = _now()
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT user_id, points FROM users WHERE deleted_at IS NOT NULL "
            "AND purged_at IS NULL AND deleted_at<=?",
            (cutoff,),
        )
        rows = await cur.fetchall()
        for r in rows:
            uid = r["user_id"]
            await conn.execute(
                "UPDATE users SET points=0, lifetime_points=0, level=1, "
                "notifications_enabled=0, rules_accepted_at=NULL, purged_at=? "
                "WHERE user_id=?",
                (now, uid),
            )
            await conn.execute(
                "INSERT INTO history (user_id, action, amount, comment, created_at) "
                "VALUES (?,?,?,?,?)",
                (uid, "profile_purge", -(r["points"] or 0),
                 f"очистка баллов после {GRACE_DAYS} дней", now),
            )
            purged += 1
        if purged:
            await conn.commit()
    if purged:
        log.info("Purged %d expired profiles", purged)
    return purged
