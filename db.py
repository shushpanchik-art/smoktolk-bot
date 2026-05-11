"""Вся работа с БД. Только async, через aiosqlite. Никаких глобальных кэшей."""
import aiosqlite
import logging
import secrets
import string
from datetime import datetime, timezone, timedelta
from typing import Optional

from config import DB_PATH, LEVELS, POINTS_TTL_DAYS, REFERRAL_MIN_PURCHASE

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_ref_code() -> str:
    return "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))


# ============== INIT ==============
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    phone TEXT,
    birthday TEXT,
    age_verified INTEGER DEFAULT 0,
    age_verified_at TEXT,
    age_verified_by INTEGER,
    gosuslugi_verified INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    points INTEGER DEFAULT 0,
    lifetime_points INTEGER DEFAULT 0,
    total_spent INTEGER DEFAULT 0,
    purchases_count INTEGER DEFAULT 0,
    purchases_count_500 INTEGER DEFAULT 0,
    last_purchase_date TEXT,
    last_activity TEXT,
    referral_code TEXT UNIQUE,
    referrer_id INTEGER,
    referral_reward_paid INTEGER DEFAULT 0,
    rules_accepted_at TEXT,
    notifications_enabled INTEGER DEFAULT 1,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    amount INTEGER NOT NULL,
    comment TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_user ON history(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    receipt_id TEXT UNIQUE NOT NULL,
    amount_rub INTEGER NOT NULL,
    points_earned INTEGER NOT NULL,
    categories_json TEXT,
    raw_payload_json TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_purchases_user ON purchases(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS gifts_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    gift_code TEXT NOT NULL,
    gift_name TEXT NOT NULL,
    qr_token TEXT UNIQUE NOT NULL,
    backup_code TEXT NOT NULL,
    level_at_moment INTEGER,
    redeemed INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    redeemed_at TEXT
);

CREATE TABLE IF NOT EXISTS verification_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    photo_file_id TEXT,
    birthday_input TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT NOT NULL,
    processed_at TEXT,
    admin_id INTEGER
);

CREATE TABLE IF NOT EXISTS redemptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    qr_token TEXT UNIQUE NOT NULL,
    backup_code TEXT NOT NULL,
    points_amount INTEGER NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at TEXT NOT NULL,
    used_at TEXT,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gift_cooldowns (
    user_id INTEGER PRIMARY KEY,
    last_gift_at TEXT
);

CREATE TABLE IF NOT EXISTS daily_stats (
    date TEXT PRIMARY KEY,
    new_users INTEGER DEFAULT 0,
    age_verified INTEGER DEFAULT 0,
    purchases_count INTEGER DEFAULT 0,
    purchases_sum INTEGER DEFAULT 0,
    points_earned INTEGER DEFAULT 0,
    points_spent INTEGER DEFAULT 0,
    points_burned INTEGER DEFAULT 0,
    gifts_redeemed INTEGER DEFAULT 0
);
"""


async def init():
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.executescript(SCHEMA)
        await conn.commit()
    log.info("DB initialized: %s", DB_PATH)


# ============== USERS ==============
async def get_user(user_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_user_by_phone(phone: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM users WHERE phone=?", (phone,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_user_by_ref_code(code: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM users WHERE referral_code=?", (code,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def create_user(user_id: int, username: str, full_name: str, referrer_id: Optional[int] = None) -> dict:
    now = _now()
    # уникальный реф-код
    for _ in range(10):
        code = _gen_ref_code()
        if not await get_user_by_ref_code(code):
            break
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """INSERT INTO users (user_id, username, full_name, referral_code, referrer_id,
               last_activity, created_at) VALUES (?,?,?,?,?,?,?)""",
            (user_id, username, full_name, code, referrer_id, now, now)
        )
        await conn.commit()
    log.info("User created: %s (referrer=%s)", user_id, referrer_id)
    return await get_user(user_id)


async def update_user_meta(user_id: int, username: str, full_name: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE users SET username=?, full_name=?, last_activity=? WHERE user_id=?",
            (username, full_name, _now(), user_id)
        )
        await conn.commit()


async def touch_activity(user_id: int):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE users SET last_activity=? WHERE user_id=?", (_now(), user_id))
        await conn.commit()


async def set_phone(user_id: int, phone: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE users SET phone=? WHERE user_id=?", (phone, user_id))
        await conn.commit()


async def set_birthday(user_id: int, bday: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE users SET birthday=? WHERE user_id=?", (bday, user_id))
        await conn.commit()


async def accept_rules(user_id: int):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE users SET rules_accepted_at=? WHERE user_id=?", (_now(), user_id))
        await conn.commit()


async def set_age_verified(user_id: int, admin_id: int, value: bool = True):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE users SET age_verified=?, age_verified_at=?, age_verified_by=? WHERE user_id=?",
            (1 if value else 0, _now() if value else None, admin_id, user_id)
        )
        await conn.commit()
    if value:
        await recalc_level(user_id)


# ============== POINTS / HISTORY ==============
async def add_history(user_id: int, action: str, amount: int, comment: str = ""):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO history (user_id, action, amount, comment, created_at) VALUES (?,?,?,?,?)",
            (user_id, action, amount, comment, _now())
        )
        await conn.commit()


async def add_points(user_id: int, points: int, action: str, comment: str = "") -> int:
    """Положительное добавление баллов. Возвращает новый баланс."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE users SET points = points + ?, lifetime_points = lifetime_points + ? WHERE user_id=?",
            (points, max(points, 0), user_id)
        )
        await conn.execute(
            "INSERT INTO history (user_id, action, amount, comment, created_at) VALUES (?,?,?,?,?)",
            (user_id, action, points, comment, _now())
        )
        await conn.commit()
        cur = await conn.execute("SELECT points FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
    log.info("Points +%d to user %s (%s): new balance %s", points, user_id, action, row[0])
    return row[0]


async def spend_points(user_id: int, points: int, action: str, comment: str = "") -> int:
    """Списание баллов. Возвращает новый баланс. Кидает ValueError если недостаточно."""
    user = await get_user(user_id)
    if not user or user["points"] < points:
        have = user['points'] if user else 0
        raise ValueError(f"Insufficient points: have {have}, need {points}")
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE users SET points = points - ? WHERE user_id=?",
            (points, user_id)
        )
        await conn.execute(
            "INSERT INTO history (user_id, action, amount, comment, created_at) VALUES (?,?,?,?,?)",
            (user_id, action, -points, comment, _now())
        )
        await conn.commit()
        cur = await conn.execute("SELECT points FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
    log.info("Points -%d from user %s (%s): new balance %s", points, user_id, action, row[0])
    return row[0]


async def get_history(user_id: int, limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM history WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


# ============== PURCHASES ==============
async def purchase_exists(receipt_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute("SELECT 1 FROM purchases WHERE receipt_id=?", (receipt_id,))
        return await cur.fetchone() is not None


async def register_purchase(user_id: int, receipt_id: str, amount_rub: int,
                            points_earned: int, categories_json: str,
                            raw_payload_json: str) -> int:
    now = _now()
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO purchases (user_id, receipt_id, amount_rub, points_earned,
               categories_json, raw_payload_json, created_at) VALUES (?,?,?,?,?,?,?)""",
            (user_id, receipt_id, amount_rub, points_earned, categories_json, raw_payload_json, now)
        )
        purchase_id = cur.lastrowid
        await conn.execute(
            """UPDATE users SET total_spent = total_spent + ?,
               purchases_count = purchases_count + 1,
               purchases_count_500 = purchases_count_500 + ?,
               last_purchase_date=?, last_activity=? WHERE user_id=?""",
            (amount_rub, 1 if amount_rub >= 500 else 0, now, now, user_id)
        )
        await conn.commit()
    return purchase_id


async def get_last_purchase_before(user_id: int, before_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM purchases WHERE user_id=? AND id<? ORDER BY id DESC LIMIT 1",
            (user_id, before_id)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def count_purchases(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM purchases WHERE user_id=?", (user_id,))
        return (await cur.fetchone())[0]


# ============== LEVEL ==============
async def recalc_level(user_id: int) -> int:
    user = await get_user(user_id)
    if not user:
        return 1
    new_level = 1
    if user["age_verified"]:
        new_level = 2
        for n in (5, 4, 3):
            lvl = LEVELS[n]
            if (user["lifetime_points"] >= lvl.min_lifetime_points
                    or user["purchases_count_500"] >= lvl.min_purchases_500):
                new_level = n
                break
    if new_level != user["level"]:
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute("UPDATE users SET level=? WHERE user_id=?", (new_level, user_id))
            await conn.commit()
        log.info("User %s level: %s -> %s", user_id, user["level"], new_level)
    return new_level


# ============== VERIFICATION REQUESTS ==============
async def create_verification_request(user_id: int, photo_file_id: Optional[str],
                                      birthday_input: Optional[str]) -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO verification_requests (user_id, photo_file_id, birthday_input, created_at)
               VALUES (?,?,?,?)""",
            (user_id, photo_file_id, birthday_input, _now())
        )
        await conn.commit()
        return cur.lastrowid


async def get_verification_request(req_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM verification_requests WHERE id=?", (req_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_pending_verifications() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM verification_requests WHERE status='pending' ORDER BY created_at"
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def update_verification_status(req_id: int, status: str, admin_id: int):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE verification_requests SET status=?, processed_at=?, admin_id=? WHERE id=?",
            (status, _now(), admin_id, req_id)
        )
        await conn.commit()


# ============== GIFTS ==============
async def get_last_gift_at(user_id: int) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute("SELECT last_gift_at FROM gift_cooldowns WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else None


async def create_gift_request(user_id: int, gift_code: str, gift_name: str,
                              level: int) -> tuple[str, str]:
    qr_token = secrets.token_urlsafe(24)
    backup_code = "".join(secrets.choice(string.digits) for _ in range(6))
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """INSERT INTO gifts_log (user_id, gift_code, gift_name, qr_token, backup_code,
               level_at_moment, created_at) VALUES (?,?,?,?,?,?,?)""",
            (user_id, gift_code, gift_name, qr_token, backup_code, level, _now())
        )
        await conn.commit()
    return qr_token, backup_code


async def get_gift_by_token(qr_token: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM gifts_log WHERE qr_token=?", (qr_token,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def mark_gift_redeemed(qr_token: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE gifts_log SET redeemed=1, redeemed_at=? WHERE qr_token=?",
            (_now(), qr_token)
        )
        cur = await conn.execute("SELECT user_id FROM gifts_log WHERE qr_token=?", (qr_token,))
        row = await cur.fetchone()
        if row:
            user_id = row[0]
            await conn.execute(
                """INSERT INTO gift_cooldowns (user_id, last_gift_at) VALUES (?,?)
                   ON CONFLICT(user_id) DO UPDATE SET last_gift_at=excluded.last_gift_at""",
                (user_id, _now())
            )
        await conn.commit()


# ============== REDEMPTIONS (списание баллов через QR) ==============
async def create_redemption(user_id: int, points: int, ttl_minutes: int) -> tuple[str, str]:
    qr_token = secrets.token_urlsafe(24)
    backup_code = "".join(secrets.choice(string.digits) for _ in range(6))
    expires = (datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)).isoformat()
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """INSERT INTO redemptions (user_id, qr_token, backup_code, points_amount,
               created_at, expires_at) VALUES (?,?,?,?,?,?)""",
            (user_id, qr_token, backup_code, points, _now(), expires)
        )
        await conn.commit()
    return qr_token, backup_code


async def get_redemption_by_token(qr_token: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM redemptions WHERE qr_token=?", (qr_token,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def mark_redemption_used(qr_token: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE redemptions SET status='used', used_at=? WHERE qr_token=?",
            (_now(), qr_token)
        )
        await conn.commit()


# ============== REFERRALS ==============
async def get_referrals(user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT user_id, full_name, age_verified, purchases_count, referral_reward_paid "
            "FROM users WHERE referrer_id=?", (user_id,)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def try_pay_referral_reward(user_id: int) -> Optional[int]:
    """Если у user_id есть referrer и условия выполнены — выплачивает и возвращает referrer_id."""
    user = await get_user(user_id)
    if not user or not user["referrer_id"] or user["referral_reward_paid"]:
        return None
    if not user["age_verified"]:
        return None
    if user["total_spent"] < REFERRAL_MIN_PURCHASE:
        return None
    if user["purchases_count"] < 1:
        return None
    referrer = await get_user(user["referrer_id"])
    if not referrer:
        return None
    from config import REFERRAL_REWARD_REFERRER, REFERRAL_REWARD_INVITEE
    await add_points(referrer["user_id"], REFERRAL_REWARD_REFERRER, "referral",
                     f"за приглашение user {user_id}")
    await add_points(user_id, REFERRAL_REWARD_INVITEE, "welcome", "приветственный за реферал")
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE users SET referral_reward_paid=1 WHERE user_id=?", (user_id,))
        await conn.commit()
    log.info("Referral reward paid: referrer=%s, invitee=%s", referrer["user_id"], user_id)
    return referrer["user_id"]


# ============== ADMIN STATS ==============
async def admin_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM users")
        total = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM users WHERE age_verified=1")
        verified = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM users WHERE purchases_count>0")
        with_purchases = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COALESCE(SUM(points),0) FROM users")
        total_points = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COALESCE(SUM(total_spent),0) FROM users")
        total_spent = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM verification_requests WHERE status='pending'")
        pending = (await cur.fetchone())[0]
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        cur = await conn.execute("SELECT COUNT(*) FROM users WHERE last_activity>=?", (week_ago,))
        active_week = (await cur.fetchone())[0]
    return {
        "total_users": total, "verified": verified, "with_purchases": with_purchases,
        "total_points": total_points, "total_spent": total_spent,
        "pending_verifications": pending, "active_week": active_week,
    }


async def find_users(query: str, limit: int = 20) -> list[dict]:
    q = f"%{query}%"
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT * FROM users WHERE
               CAST(user_id AS TEXT) LIKE ? OR phone LIKE ? OR username LIKE ? OR full_name LIKE ?
               ORDER BY last_activity DESC LIMIT ?""",
            (q, q, q, q, limit)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def all_user_ids(only_with_notifications: bool = True) -> list[int]:
    async with aiosqlite.connect(DB_PATH) as conn:
        if only_with_notifications:
            cur = await conn.execute("SELECT user_id FROM users WHERE notifications_enabled=1")
        else:
            cur = await conn.execute("SELECT user_id FROM users")
        return [r[0] for r in await cur.fetchall()]


async def toggle_notifications(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute("SELECT notifications_enabled FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        new_val = 0 if row[0] else 1
        await conn.execute("UPDATE users SET notifications_enabled=? WHERE user_id=?",
                           (new_val, user_id))
        await conn.commit()
    return bool(new_val)


# ============== BURN POINTS ==============
async def burn_inactive_points() -> int:
    """Сжигает баллы пользователей, у которых last_purchase_date старше POINTS_TTL_DAYS."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=POINTS_TTL_DAYS)).isoformat()
    burned_total = 0
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT user_id, points FROM users WHERE points>0 AND last_purchase_date IS NOT NULL "
            "AND last_purchase_date < ?", (cutoff,)
        )
        rows = await cur.fetchall()
        for r in rows:
            await conn.execute("UPDATE users SET points=0 WHERE user_id=?", (r["user_id"],))
            await conn.execute(
                "INSERT INTO history (user_id, action, amount, comment, created_at) VALUES (?,?,?,?,?)",
                (r["user_id"], "burn", -r["points"], f"сгорание после {POINTS_TTL_DAYS} дней", _now())
            )
            burned_total += r["points"]
        await conn.commit()
    if burned_total:
        log.info("Burned %d points from %d users", burned_total, len(rows))
    return burned_total


# ============== DAILY STATS ==============
async def bump_daily(field: str, delta: int = 1, date: Optional[str] = None):
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    allowed = {"new_users", "age_verified", "purchases_count", "purchases_sum",
               "points_earned", "points_spent", "points_burned", "gifts_redeemed"}
    if field not in allowed:
        return
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("INSERT OR IGNORE INTO daily_stats (date) VALUES (?)", (date,))
        # SECURITY: field валидируется whitelist `allowed` выше (CWE-89 mitigated); значения через ?-placeholder
        await conn.execute(f"UPDATE daily_stats SET {field}={field}+? WHERE date=?", (delta, date))  # nosec B608
        await conn.commit()


async def get_daily(date: str) -> dict:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM daily_stats WHERE date=?", (date,))
        row = await cur.fetchone()
        if row:
            return dict(row)
    return {"date": date, "new_users": 0, "age_verified": 0, "purchases_count": 0,
            "purchases_sum": 0, "points_earned": 0, "points_spent": 0,
            "points_burned": 0, "gifts_redeemed": 0}


# Алиас для совместимости с bot.py
init_db = init



# ============== USERS ARCHIVE & EXPORT ==============

async def list_all_users(active_only: bool = False, since_days: int = None):
    """Все пользователи (для CSV-экспорта)."""
    where = []
    params = []
    if active_only:
        where.append("(is_active IS NULL OR is_active=1)")
    if since_days is not None:
        where.append("created_at >= datetime(\"now\", ?)")
        params.append(f"-{int(since_days)} days")
    sql = "SELECT user_id, username, first_name, last_name, phone, points, level, age_verified, is_active, created_at FROM users"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC"
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(sql, params) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def count_users(active_only: bool = False, since_days: int = None):
    """Подсчёт пользователей."""
    where = []
    params = []
    if active_only:
        where.append("(is_active IS NULL OR is_active=1)")
    if since_days is not None:
        where.append("created_at >= datetime(\"now\", ?)")
        params.append(f"-{int(since_days)} days")
    sql = "SELECT COUNT(*) FROM users"
    if where:
        sql += " WHERE " + " AND ".join(where)
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(sql, params) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def mark_user_blocked(user_id: int):
    """Помечает, что пользователь заблокировал бота (НЕ удаляет!)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE users SET is_active=0, blocked_at=datetime(\"now\") WHERE user_id=?",
            (user_id,)
        )
        await conn.commit()


async def mark_user_active(user_id: int):
    """Восстанавливает is_active=1 (если пользователь снова написал боту)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE users SET is_active=1, blocked_at=NULL WHERE user_id=?",
            (user_id,)
        )
        await conn.commit()


async def make_users_snapshot(snapshot_date: str = None):
    """Создаёт снапшот всех пользователей (для рассылок и истории).
    Вызывается ежедневно из tasks.py.
    """
    from datetime import date
    if not snapshot_date:
        snapshot_date = date.today().isoformat()
    
    async with aiosqlite.connect(DB_PATH) as conn:
        # вставляем все строки из users
        await conn.execute("""
            INSERT OR IGNORE INTO users_archive
                (user_id, username, first_name, last_name, phone,
                 points, level, age_verified, is_active, snapshot_date)
            SELECT user_id, username, first_name, last_name, phone,
                   points, level, age_verified,
                   COALESCE(is_active, 1), ?
            FROM users
        """, (snapshot_date,))
        await conn.commit()
        async with conn.execute(
            "SELECT COUNT(*) FROM users_archive WHERE snapshot_date=?",
            (snapshot_date,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def admin_adjust_points(user_id: int, delta: int, reason: str, admin_id: int):
    """Ручная корректировка баллов админом.
    delta > 0 — начисление; delta < 0 — списание.
    Возвращает (старый_баланс, новый_баланс).
    """
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT points FROM users WHERE user_id=?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            raise ValueError(f"Пользователь {user_id} не найден")
        old_balance = row["points"] or 0
        new_balance = max(0, old_balance + delta)  # не уходим в минус
        await conn.execute(
            "UPDATE users SET points=? WHERE user_id=?",
            (new_balance, user_id)
        )
        # запись в history (если таблица есть)
        try:
            op_type = "admin_add" if delta >= 0 else "admin_sub"
            await conn.execute("""
                INSERT INTO history (user_id, op_type, amount, balance_after, comment, created_at)
                VALUES (?, ?, ?, ?, ?, datetime("now"))
            """, (user_id, op_type, abs(delta), new_balance,
                  f"Admin {admin_id}: {reason}"))
        except Exception:
            pass
        await conn.commit()
        return old_balance, new_balance
