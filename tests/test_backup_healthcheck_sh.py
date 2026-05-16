"""
Tests for scripts/backup_healthcheck.sh

Покрывает граничные случаи MAX_AGE_HOURS логики:
- свежий файл (<MAX_AGE_HOURS) → OK
- ровно на границе → OK / FAIL
- файл старше MAX_AGE_HOURS → FAIL
- BACKUP_DIR не существует → FAIL
- пустой BACKUP_DIR → FAIL
- файлы с неподходящим именем игнорируются
- safety-net сценарий: файл 6-дневной давности в режиме MAX_AGE=192 → OK

Запуск:
    pytest tests/test_backup_healthcheck_sh.py -v
"""
from __future__ import annotations

import os
import stat
import subprocess
import time
from pathlib import Path

import pytest

HEALTHCHECK_SH = Path(__file__).parent.parent / "scripts" / "backup_healthcheck.sh"


@pytest.fixture
def env_setup(tmp_path: Path) -> dict:
    """
    Готовит:
      - backup_dir: пустой каталог под бэкапы
      - bin_dir: каталог со stub-скриптом notify_admin.sh (логирует вызовы в файл)
      - notify_log: путь к логу вызовов notify_admin.sh
    """
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    notify_log = tmp_path / "notify.log"

    notify_stub = bin_dir / "notify_admin.sh"
    notify_stub.write_text(
        f'#!/bin/sh\necho "EVENT=$1 MSG=$2" >> {notify_log}\nexit 0\n',
        encoding="utf-8",
    )
    notify_stub.chmod(0o755)

    return {
        "tmp": tmp_path,
        "backup_dir": backup_dir,
        "notify_stub": notify_stub,
        "notify_log": notify_log,
    }


def _run(env_setup: dict, max_age_hours: int = 192) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["BACKUP_DIR"] = str(env_setup["backup_dir"])
    env["MAX_AGE_HOURS"] = str(max_age_hours)
    env["NOTIFY_SCRIPT"] = str(env_setup["notify_stub"])
    return subprocess.run(
        ["bash", str(HEALTHCHECK_SH)],
        env=env,
        capture_output=True,
        text=True,
    )


def _make_backup(env_setup: dict, name: str, age_hours: float) -> Path:
    """Создаёт файл с указанным mtime (часы назад)."""
    f = env_setup["backup_dir"] / name
    f.write_bytes(b"x" * 1024)
    mtime = time.time() - age_hours * 3600
    os.utime(f, (mtime, mtime))
    return f


def _notify_events(env_setup: dict) -> list[str]:
    """Список событий, отправленных в notify_admin.sh."""
    log_path = env_setup["notify_log"]
    if not log_path.exists():
        return []
    events = []
    for line in log_path.read_text().splitlines():
        if line.startswith("EVENT="):
            events.append(line.split()[0].split("=", 1)[1])
    return events


# ============================== TESTS ==============================

def test_01_happy_path_fresh_backup(env_setup):
    """Свежий бэкап (1 час назад) → exit 0, OK в stdout, нет уведомлений."""
    _make_backup(env_setup, "smoktolk_20260516_040000.db", age_hours=1)
    r = _run(env_setup)
    assert r.returncode == 0, r.stderr
    assert "OK: свежий бэкап найден" in r.stdout
    assert _notify_events(env_setup) == []


def test_02_safety_net_window_ok(env_setup):
    """
    Safety-net сценарий: последний бэкап 5 дней назад, БД не менялась.
    MAX_AGE_HOURS=192 → 5*24=120 ч < 192 ч → OK, нет алерта.
    Это главный фикс данного PR.
    """
    _make_backup(env_setup, "smoktolk_20260511_040000.db", age_hours=120)
    r = _run(env_setup, max_age_hours=192)
    assert r.returncode == 0, r.stderr
    assert "OK" in r.stdout
    assert _notify_events(env_setup) == []


def test_03_just_below_limit_ok(env_setup):
    """Файл 191 ч (< 192) → OK."""
    _make_backup(env_setup, "smoktolk_20260508_040000.db", age_hours=191)
    r = _run(env_setup, max_age_hours=192)
    assert r.returncode == 0


def test_04_just_above_limit_fails(env_setup):
    """Файл 193 ч (> 192) → FAIL + backup-failed."""
    _make_backup(env_setup, "smoktolk_20260508_040000.db", age_hours=193)
    r = _run(env_setup, max_age_hours=192)
    assert r.returncode == 1
    assert "FAIL: нет бэкапа младше" in r.stdout
    assert "backup-failed" in _notify_events(env_setup)


def test_05_empty_backup_dir_fails(env_setup):
    """Пустой каталог → FAIL + алерт."""
    r = _run(env_setup)
    assert r.returncode == 1
    assert "backup-failed" in _notify_events(env_setup)


def test_06_backup_dir_missing_fails(env_setup):
    """BACKUP_DIR не существует → FAIL с особым сообщением."""
    env_setup["backup_dir"].rmdir()
    r = _run(env_setup)
    assert r.returncode == 1
    assert "BACKUP_DIR не существует" in r.stdout
    assert "backup-failed" in _notify_events(env_setup)


def test_07_unrelated_files_ignored(env_setup):
    """
    Файлы не подходящие под smoktolk_*.db не считаются за бэкап.
    Только .last_dump.sha256 и какой-то README — должен быть FAIL.
    """
    (env_setup["backup_dir"] / ".last_dump.sha256").write_text("deadbeef")
    (env_setup["backup_dir"] / "README.txt").write_text("readme")
    r = _run(env_setup)
    assert r.returncode == 1
    assert "backup-failed" in _notify_events(env_setup)


def test_08_multiple_files_picks_fresh(env_setup):
    """Старый + свежий файлы → OK (find находит свежий)."""
    _make_backup(env_setup, "smoktolk_20260301_040000.db", age_hours=1000)
    _make_backup(env_setup, "smoktolk_20260516_040000.db", age_hours=2)
    r = _run(env_setup)
    assert r.returncode == 0
    assert _notify_events(env_setup) == []
