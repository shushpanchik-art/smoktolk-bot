"""Тесты для backup.sh через subprocess.

Скрипт snapshot'ит SQLite и ротирует бэкапы. Тестируем поведение
через ENV-переменные (BOT_DIR/DB_PATH/BACKUP_DIR/...).
"""
import os
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest

BACKUP_SH = Path(__file__).resolve().parent.parent / "backup.sh"


# ---------- helpers ----------

def _make_db(path: Path, payload: str = "hello") -> None:
    """Создать минимальную sqlite-БД с одной записью."""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
    con.execute("INSERT INTO t (v) VALUES (?)", (payload,))
    con.commit()
    con.close()


def _run(env_overrides: dict, expect_rc: int = 0) -> subprocess.CompletedProcess:
    """Запустить backup.sh с заданными ENV. Базовый env минимален."""
    env = {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME": str(env_overrides.get("BOT_DIR", "/tmp")),
        "LANG": "C",
    }
    env.update({k: str(v) for k, v in env_overrides.items()})
    r = subprocess.run(
        ["/usr/bin/env", "bash", str(BACKUP_SH)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == expect_rc, (
        f"rc={r.returncode}\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"
    )
    return r


def _backups(backup_dir: Path) -> list[Path]:
    return sorted(backup_dir.glob("smoktolk_*.db"))


@pytest.fixture
def env(tmp_path):
    """Стандартный изолированный env для одного теста."""
    bot_dir = tmp_path / "bot"
    backup_dir = tmp_path / "backups"
    db_path = bot_dir / "data" / "smoktolk.db"
    _make_db(db_path, "v1")
    return {
        "BOT_DIR": bot_dir,
        "DB_PATH": db_path,
        "BACKUP_DIR": backup_dir,
        "RETENTION_DAYS": 30,
        "MAX_TOTAL_BYTES": 5_368_709_120,
        "SAFETY_NET_DAYS": 7,
        "LOCK_FILE": backup_dir / ".backup.lock",
        "_tmp": tmp_path,
        "_db": db_path,
        "_backup_dir": backup_dir,
    }


# ---------- tests ----------

def test_first_run_creates_backup_and_hash(env):
    """Первый запуск на пустом каталоге создаёт .db и .last_dump.sha256."""
    r = _run({k: v for k, v in env.items() if not k.startswith("_")})
    backups = _backups(env["_backup_dir"])
    assert len(backups) == 1, r.stdout + r.stderr
    assert (env["_backup_dir"] / ".last_dump.sha256").is_file()
    assert "backup ok" in r.stdout


def test_second_run_no_changes_skips(env):
    """Повторный запуск без изменений БД → бэкап не создаётся."""
    cfg = {k: v for k, v in env.items() if not k.startswith("_")}
    _run(cfg)
    time.sleep(1.1)  # чтобы DATE в имени файла гарантированно отличался
    r = _run(cfg)
    backups = _backups(env["_backup_dir"])
    assert len(backups) == 1
    assert "skipped" in r.stdout
    assert "no data changes" in r.stdout


def test_db_change_triggers_new_backup(env):
    """Изменение БД → новый бэкап появляется."""
    cfg = {k: v for k, v in env.items() if not k.startswith("_")}
    _run(cfg)
    time.sleep(1.1)
    # модифицируем БД
    con = sqlite3.connect(str(env["_db"]))
    con.execute("INSERT INTO t (v) VALUES ('v2')")
    con.commit()
    con.close()
    r = _run(cfg)
    backups = _backups(env["_backup_dir"])
    assert len(backups) == 2, r.stdout
    assert "backup ok" in r.stdout


def test_safety_net_forces_backup_when_old(env):
    """Если последний бэкап старше SAFETY_NET_DAYS — бэкап делается даже без изменений."""
    cfg = {k: v for k, v in env.items() if not k.startswith("_")}
    cfg["SAFETY_NET_DAYS"] = 3
    _run(cfg)
    backups = _backups(env["_backup_dir"])
    assert len(backups) == 1
    # состарим единственный бэкап на 10 дней
    old_ts = time.time() - 10 * 86400
    os.utime(backups[0], (old_ts, old_ts))
    time.sleep(1.1)
    r = _run(cfg)
    backups = _backups(env["_backup_dir"])
    assert len(backups) == 2, r.stdout
    assert "safety-net" in r.stdout


def test_retention_removes_old_files(env):
    """Файлы старше RETENTION_DAYS удаляются, последний остаётся."""
    cfg = {k: v for k, v in env.items() if not k.startswith("_")}
    cfg["RETENTION_DAYS"] = 5
    cfg["SAFETY_NET_DAYS"] = 9999  # отключаем safety-net, чтобы не плодить лишние
    _run(cfg)
    backups = _backups(env["_backup_dir"])
    assert len(backups) == 1
    # делаем старый "лишний" бэкап вручную и состариваем его
    old = env["_backup_dir"] / "smoktolk_20200101_000000.db"
    old.write_bytes(b"old")
    old_ts = time.time() - 100 * 86400
    os.utime(old, (old_ts, old_ts))
    # запускаем снова — БД не менялась, но retention должен прибить старый файл
    time.sleep(1.1)
    r = _run(cfg)
    remaining = _backups(env["_backup_dir"])
    assert old not in remaining, r.stdout
    assert len(remaining) >= 1
    assert "retention" in r.stdout


def test_lock_prevents_parallel_run(env):
    """Захваченный lock-файл → второй процесс выходит с WARN."""
    cfg = {k: v for k, v in env.items() if not k.startswith("_")}
    env["_backup_dir"].mkdir(parents=True, exist_ok=True)
    import fcntl
    lock_path = env["LOCK_FILE"]
    # захватываем lock прямо из питона — надёжно, не зависит от shell пользователя
    lock_fd = open(str(lock_path), "w")
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        r = _run(cfg)
        assert "WARN" in r.stdout
        assert "lock" in r.stdout
        assert _backups(env["_backup_dir"]) == []
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()


def test_missing_db_fails(env, tmp_path):
    """Несуществующая БД → exit != 0 и сообщение об ошибке."""
    cfg = {k: v for k, v in env.items() if not k.startswith("_")}
    cfg["DB_PATH"] = tmp_path / "no_such.db"
    r = _run(cfg, expect_rc=1)
    assert "ERROR" in r.stdout
    assert "ne naydena" in r.stdout or "not" in r.stdout.lower()


def test_log_format_has_timestamp(env):
    """Каждая строка лога начинается с '[YYYY-MM-DD HH:MM:SS TZ]'."""
    cfg = {k: v for k, v in env.items() if not k.startswith("_")}
    r = _run(cfg)
    for line in r.stdout.splitlines():
        if not line.strip():
            continue
        assert line.startswith("["), f"bad line: {line!r}"
        # после ']' идёт пробел и текст
        assert "] " in line, f"bad line: {line!r}"




# ---------- fsync durability tests ----------




def test_fsync_logged_after_successful_backup(env):
    """После создания бэкапа лог содержит 'fsynced' — подтверждение, что
    code path с sync(1) выполнился. Реальную durability проверить в юнит-
    тесте невозможно (нет power loss), но отсутствие маркера = регрессия:
    кто-то удалил sync, что снова делает бэкап уязвимым к power loss.
    """
    cfg = {k: v for k, v in env.items() if not k.startswith("_")}
    r = _run(cfg)
    assert "fsynced" in r.stdout, (
        "Маркер 'fsynced' отсутствует в логе — возможно, sync(1) удалён.\n"
        f"STDOUT:\n{r.stdout}"
    )




def test_fsync_not_logged_on_skip(env):
    """При skipped (нет изменений) бэкап не создаётся → sync не нужен → маркера 'fsynced' нет."""
    cfg = {k: v for k, v in env.items() if not k.startswith("_")}
    _run(cfg)
    time.sleep(1.1)
    r = _run(cfg)
    # При skip log "backup ok ... fsynced" не должен появиться
    assert "skipped" in r.stdout
    # Ищем именно "fsynced" в строке backup ok — если маркер где-то ещё
    # (например, в комментариях скрипта) — это другой контекст.
    ok_lines = [line for line in r.stdout.splitlines() if "backup ok" in line]
    assert ok_lines == [], f"unexpected 'backup ok' lines on skip: {ok_lines}"




def test_backup_file_durable_and_valid_after_sync(env):
    """После sync файл .db реально лежит на диске и является валидным SQLite.
    Это smoke-тест на то, что sync(1) не повредил данные (sync — read-only
    операция относительно содержимого, но проверяем явно).
    """
    cfg = {k: v for k, v in env.items() if not k.startswith("_")}
    _run(cfg)
    backups = _backups(env["_backup_dir"])
    assert len(backups) == 1
    # Файл существует, не пустой, открывается как SQLite, содержит наши данные
    backup_path = backups[0]
    assert backup_path.stat().st_size > 0, "backup is empty"
    con = sqlite3.connect(str(backup_path))
    try:
        rows = con.execute("SELECT v FROM t").fetchall()
    finally:
        con.close()
    assert rows == [("v1",)], f"backup data mismatch: {rows}"
