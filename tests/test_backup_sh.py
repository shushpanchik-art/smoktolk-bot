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
    lock_path = env["LOCK_FILE"]
    # захватываем lock через flock на длительное время
    holder = subprocess.Popen(
        ["flock", "-x", str(lock_path), "sleep", "10"],
    )
    try:
        time.sleep(0.3)  # дать flock время реально взять блокировку
        r = _run(cfg)
        assert "WARN" in r.stdout
        assert "lock" in r.stdout
        assert _backups(env["_backup_dir"]) == []
    finally:
        holder.terminate()
        holder.wait(timeout=5)


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
