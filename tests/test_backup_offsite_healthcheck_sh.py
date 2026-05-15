"""Тесты для scripts/backup_offsite_healthcheck.sh (PR #ops-offsite-yandex-disk).

Стратегия идентична test_backup_offsite_sh.py:
- Запускаем настоящий backup_offsite_healthcheck.sh через subprocess.
- Подменяем `rclone` и `notify_admin.sh` stub-скриптами в tmp_path/bin,
  ставим bin первым в $PATH.
- ENV-override'ы (RCLONE_CONFIG, MAX_AGE_HOURS, ...) задаём через subprocess env.
- Проверяем поведение: exit-code, текст лога, факт/отсутствие notify-вызова.

Покрытие:
  01 happy path (свежий файл)
  02 граница MAX_AGE_HOURS-1ч → OK
  03 граница MAX_AGE_HOURS+1ч → FAIL + notify
  04 rclone сказал "not found" → FAIL
  05 rclone вернул пусто → FAIL
  06 mtime в будущем (>1ч) → FAIL (TZ misconfig guard)
  07 mtime — мусор, не парсится → FAIL
  08 rclone config нечитаем → FAIL
  09 rclone отсутствует в PATH → FAIL
  10 age=0 (mtime ровно сейчас) → OK
"""
import os
import stat
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
HC_SH = REPO_ROOT / "scripts" / "backup_offsite_healthcheck.sh"


# =========================================================================
# Helpers
# =========================================================================

def _chmod_exec(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _make_stub(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    _chmod_exec(path)


def _make_rclone_stub(bin_dir: Path, mtime_str: str, size: int = 3637) -> Path:
    """rclone stub, отдающий заданный mtime в формате `lsl`.

    `mtime_str` — строка вида '2026-05-14 23:50:12' (как настоящий rclone в MSK).
    Логирует все вызовы в RCLONE_LOG.
    """
    rclone_log = bin_dir / "rclone.log"
    body = f"""#!/usr/bin/env bash
echo "rclone $*" >> "{rclone_log}"
# Имитируем `rclone lsl <remote>/<file>`:
# Игнорируем флаги, последний аргумент — путь.
# Формат выхода: "    SIZE  YYYY-MM-DD HH:MM:SS.NNNNNNNNN NAME"
for arg in "$@"; do :; done
# $arg — последний аргумент (путь к файлу на remote)
fname="$(basename "$arg")"
printf '%9d %s.000000000 %s\\n' {size} "{mtime_str}" "$fname"
exit 0
"""
    stub = bin_dir / "rclone"
    _make_stub(stub, body)
    return rclone_log


def _make_rclone_stub_raw(bin_dir: Path, raw_output: str, exit_code: int = 0) -> Path:
    """rclone stub, выдающий ровно `raw_output` (для негативных кейсов)."""
    rclone_log = bin_dir / "rclone.log"
    body = f"""#!/usr/bin/env bash
echo "rclone $*" >> "{rclone_log}"
cat <<'OUT'
{raw_output}
OUT
exit {exit_code}
"""
    stub = bin_dir / "rclone"
    _make_stub(stub, body)
    return rclone_log


def _make_notify_stub(bin_dir: Path) -> Path:
    """notify_admin.sh stub: пишет в NOTIFY_LOG все вызовы."""
    notify_log = bin_dir / "notify.log"
    body = f"""#!/usr/bin/env bash
echo "notify_admin.sh $*" >> "{notify_log}"
exit 0
"""
    stub = bin_dir / "notify_admin.sh"
    _make_stub(stub, body)
    return notify_log


def _rclone_calls(env_setup: dict) -> list[str]:
    p = env_setup["bin_dir"] / "rclone.log"
    if not p.exists():
        return []
    return [line for line in p.read_text().splitlines() if line.strip()]


def _notify_events(env_setup: dict) -> list[str]:
    p = env_setup["notify_log"]
    if not p.exists():
        return []
    events = []
    for line in p.read_text().splitlines():
        # формат: "notify_admin.sh offsite-failed"
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0].endswith("notify_admin.sh"):
            events.append(parts[1])
    return events


def _run_script(env_setup: dict, expect_rc: int | None = None, extra_env: dict | None = None
               ) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PATH"] = f"{env_setup['bin_dir']}:{env.get('PATH', '')}"
    env["RCLONE_CONFIG"] = str(env_setup["rclone_config"])
    env["RCLONE_REMOTE"] = "yandex:smoktolk-backup"
    env["LATEST_NAME"] = "smoktolk-latest.db.gz"
    env["NOTIFY_SCRIPT"] = str(env_setup["bin_dir"] / "notify_admin.sh")
    env["MAX_AGE_HOURS"] = "30"
    if extra_env:
        env.update(extra_env)

    proc = subprocess.run(
        ["bash", str(HC_SH)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if expect_rc is not None:
        assert proc.returncode == expect_rc, (
            f"Expected rc={expect_rc}, got {proc.returncode}.\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return proc


# =========================================================================
# Fixtures
# =========================================================================

@pytest.fixture
def env_setup(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    rclone_config = tmp_path / "rclone.conf"
    rclone_config.write_text("[yandex]\ntype = webdav\n", encoding="utf-8")

    notify_log = _make_notify_stub(bin_dir)

    return {
        "tmp": tmp_path,
        "bin_dir": bin_dir,
        "rclone_config": rclone_config,
        "notify_log": notify_log,
    }


def _now_minus(hours: float) -> str:
    """Возвращает datetime - hours в локальной TZ (как отдаёт rclone)."""
    dt = datetime.now() - timedelta(hours=hours)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# =========================================================================
# Tests
# =========================================================================

def test_01_happy_path_fresh_file(env_setup):
    """Свежий файл (1ч назад) → OK, exit 0, notify не звался."""
    _make_rclone_stub(env_setup["bin_dir"], _now_minus(1.0))
    proc = _run_script(env_setup, expect_rc=0)
    assert "OK:" in proc.stdout
    assert "smoktolk-latest.db.gz" in proc.stdout
    assert _notify_events(env_setup) == []
    # rclone должен быть позван ровно 1 раз — на lsl
    calls = _rclone_calls(env_setup)
    assert len(calls) == 1
    assert "lsl" in calls[0]


def test_02_age_just_below_limit(env_setup):
    """Возраст 29ч (MAX_AGE_HOURS=30) → OK."""
    _make_rclone_stub(env_setup["bin_dir"], _now_minus(29.0))
    proc = _run_script(env_setup, expect_rc=0)
    assert "OK:" in proc.stdout
    assert _notify_events(env_setup) == []


def test_03_age_just_above_limit(env_setup):
    """Возраст 31ч (MAX_AGE_HOURS=30) → FAIL + offsite-failed."""
    _make_rclone_stub(env_setup["bin_dir"], _now_minus(31.0))
    proc = _run_script(env_setup, expect_rc=1)
    assert "FAIL:" in proc.stdout
    assert "слишком старый" in proc.stdout
    assert _notify_events(env_setup) == ["offsite-failed"]


def test_04_file_not_found(env_setup):
    """rclone сказал 'not found' → FAIL + offsite-failed."""
    _make_rclone_stub_raw(
        env_setup["bin_dir"],
        "2026/05/15 10:00:00 ERROR : object not found",
        exit_code=3,
    )
    proc = _run_script(env_setup, expect_rc=1)
    assert "FAIL:" in proc.stdout
    assert "не найден" in proc.stdout or "не найден" in proc.stdout
    assert _notify_events(env_setup) == ["offsite-failed"]


def test_05_empty_rclone_output(env_setup):
    """rclone вернул пустой stdout → FAIL."""
    _make_rclone_stub_raw(env_setup["bin_dir"], "", exit_code=0)
    proc = _run_script(env_setup, expect_rc=1)
    assert "FAIL:" in proc.stdout
    assert _notify_events(env_setup) == ["offsite-failed"]


def test_06_mtime_in_future(env_setup):
    """mtime на 5 часов в будущем (broken TZ/NTP) → FAIL."""
    future = (datetime.now() + timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")
    _make_rclone_stub(env_setup["bin_dir"], future)
    proc = _run_script(env_setup, expect_rc=1)
    assert "FAIL:" in proc.stdout
    assert "будущем" in proc.stdout
    assert _notify_events(env_setup) == ["offsite-failed"]


def test_07_unparseable_mtime(env_setup):
    """rclone выдал строку, где mtime — мусор → FAIL."""
    # Структура lsl сломана: вместо даты — буквы. `date -d` вернёт 0.
    _make_rclone_stub_raw(
        env_setup["bin_dir"],
        "      3637 ZZZZ-XX-YY QQ:QQ:QQ.000000000 smoktolk-latest.db.gz",
        exit_code=0,
    )
    proc = _run_script(env_setup, expect_rc=1)
    assert "FAIL:" in proc.stdout
    assert _notify_events(env_setup) == ["offsite-failed"]


def test_08_rclone_config_unreadable(env_setup):
    """rclone.conf не существует → FAIL до вызова rclone."""
    proc = _run_script(
        env_setup, expect_rc=1,
        extra_env={"RCLONE_CONFIG": "/nonexistent/rclone.conf"},
    )
    assert "FAIL:" in proc.stdout
    assert "rclone config" in proc.stdout
    # rclone-stub НЕ должен был быть вызван
    assert _rclone_calls(env_setup) == []
    assert _notify_events(env_setup) == ["offsite-failed"]


def test_09_rclone_not_in_path(env_setup, tmp_path):
    """В PATH нет rclone → FAIL ('rclone не установлен').

    Изолированный PATH: создаём sandbox-каталог, в который кладём симлинки
    только на разрешённые утилиты (date/awk/head/cut/grep/sed/cat/basename),
    а также наш notify_admin.sh stub. rclone намеренно отсутствует.
    Это гарантирует, что `command -v rclone` вернёт false ВНЕ зависимости
    от того, установлен ли системный rclone в /usr/bin.
    """
    sandbox = tmp_path / "sandbox_bin"
    sandbox.mkdir()
    # Минимальный набор утилит для работы healthcheck-скрипта.
    for util in ("date", "awk", "head", "cut", "grep", "sed", "cat",
                 "basename", "printf", "echo", "sh", "bash"):
        # Ищем в стандартных местах
        for candidate in (f"/usr/bin/{util}", f"/bin/{util}"):
            if os.path.exists(candidate):
                (sandbox / util).symlink_to(candidate)
                break
    # Кладём наш notify_admin.sh stub в sandbox
    notify_log = sandbox / "notify.log"
    (sandbox / "notify_admin.sh").write_text(
        f'#!/usr/bin/env bash\necho "notify_admin.sh $*" >> "{notify_log}"\nexit 0\n'
    )
    _chmod_exec(sandbox / "notify_admin.sh")

    env = {
        "PATH": str(sandbox),  # ТОЛЬКО sandbox — rclone сюда не положили
        "RCLONE_CONFIG": str(env_setup["rclone_config"]),
        "RCLONE_REMOTE": "yandex:smoktolk-backup",
        "LATEST_NAME": "smoktolk-latest.db.gz",
        "NOTIFY_SCRIPT": str(sandbox / "notify_admin.sh"),
        "MAX_AGE_HOURS": "30",
    }

    proc = subprocess.run(
        ["bash", str(HC_SH)],
        env=env, capture_output=True, text=True, timeout=10,
    )
    assert proc.returncode == 1, (
        f"Expected rc=1, got {proc.returncode}.\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    assert "rclone не установлен" in proc.stdout, (
        f"Ожидали 'rclone не установлен', получили:\n{proc.stdout}"
    )
    # Проверяем, что notify был вызван
    assert notify_log.exists(), "notify_admin.sh не был вызван"
    notify_lines = notify_log.read_text().strip().splitlines()
    assert any("offsite-failed" in line for line in notify_lines), (
        f"Не нашли offsite-failed в notify-логе: {notify_lines}"
    )


def test_10_age_exactly_zero(env_setup):
    """mtime ровно сейчас → age=0ч → OK."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _make_rclone_stub(env_setup["bin_dir"], now)
    proc = _run_script(env_setup, expect_rc=0)
    assert "age=0" in proc.stdout
    assert _notify_events(env_setup) == []
