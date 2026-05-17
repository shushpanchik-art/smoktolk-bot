"""Тесты для scripts/backup_offsite.sh (PR #ops-offsite-yandex-disk).

Стратегия:
- Запускаем настоящий backup_offsite.sh через subprocess.
- Подменяем `rclone` и `notify_admin.sh` stub-скриптами в tmp_path/bin,
  ставим bin первым в $PATH.
- Stub'ы логируют все вызовы в файлы (RCLONE_LOG, NOTIFY_LOG) — по ним
  проверяем поведение скрипта.

Покрытие (см. backup_offsite.sh, шаги 1-6):
1.  happy path: gzip → copyto×2 → hashsum (unsupported) → delete → lsf → recovered
2.  нет локального бэкапа → die, failed
3.  rclone не установлен → die, failed
4.  rclone.conf нечитаем → die, failed
5.  пустой файл бэкапа → die, failed
6.  copyto (history) падает → die, failed
7.  copyto (latest) падает → die, failed
8.  hashsum mismatch → die, failed
9.  hashsum UNSUPPORTED → OK, лог "sverka skipped"
10. concurrent flock → exit 0 без rclone и без notify
(11-12 — в следующем коммите)
"""
import stat
import subprocess
import textwrap
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
BACKUP_OFFSITE_SH = REPO_ROOT / "scripts" / "backup_offsite.sh"


# =========================================================================
# Helpers
# =========================================================================

def _chmod_exec(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _make_stub(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    _chmod_exec(path)


def _make_rclone_stub(bin_dir: Path, *,
                      copyto_history_rc: int = 0,
                      copyto_latest_rc: int = 0,
                      hashsum_output: str = "",
                      delete_rc: int = 0,
                      lsf_output: str = "smoktolk_20260514_040000.db.gz\n") -> None:
    """
    Stub rclone. Логирует команды в $RCLONE_LOG как "<cmd> | <full args>".
    Различает первый/второй вызов copyto через файл-счётчик.
    """
    body = textwrap.dedent(f"""\
        #!/bin/bash
        : "${{RCLONE_LOG:?RCLONE_LOG must be set}}"

        # Находим первое позиционное слово (cmd), пропуская флаги с/без значений.
        cmd=""
        skip_next=0
        for arg in "$@"; do
            if [ "$skip_next" -eq 1 ]; then
                skip_next=0
                continue
            fi
            case "$arg" in
                --config|--timeout|--contimeout|--low-level-retries|--retries|--bwlimit|--stats|--include|--min-age)
                    skip_next=1
                    ;;
                --*)
                    ;;
                *)
                    cmd="$arg"
                    break
                    ;;
            esac
        done

        echo "$cmd | $*" >> "$RCLONE_LOG"

        cnt_file="${{RCLONE_LOG}}.copyto_count"

        case "$cmd" in
            copyto)
                n=0
                [ -f "$cnt_file" ] && n=$(cat "$cnt_file")
                n=$((n+1))
                echo "$n" > "$cnt_file"
                if [ "$n" -eq 1 ]; then exit {copyto_history_rc}; else exit {copyto_latest_rc}; fi
                ;;
            hashsum)
                [ -n "{hashsum_output}" ] && echo "{hashsum_output}"
                exit 0
                ;;
            delete)
                exit {delete_rc}
                ;;
            lsf)
                printf '%s' "{lsf_output}"
                exit 0
                ;;
            *)
                echo "stub rclone: unknown cmd '$cmd'" >&2
                exit 2
                ;;
        esac
    """)
    _make_stub(bin_dir / "rclone", body)


def _make_notify_stub(bin_dir: Path, *, rc: int = 0, executable: bool = True) -> None:
    """Stub notify_admin.sh — логирует событие в $NOTIFY_LOG."""
    body = textwrap.dedent(f"""\
        #!/bin/bash
        : "${{NOTIFY_LOG:?NOTIFY_LOG must be set}}"
        echo "notify_admin.sh $*" >> "$NOTIFY_LOG"
        exit {rc}
    """)
    p = bin_dir / "notify_admin.sh"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    if executable:
        _chmod_exec(p)
    else:
        p.chmod(0o644)  # явно убираем +x


def _make_backup(backup_dir: Path,
                 name: str = "smoktolk_20260514_040000.db",
                 content: bytes = b"SQLite format 3\x00" + b"X" * 4096) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    p = backup_dir / name
    p.write_bytes(content)
    return p


def _make_rclone_config(rclone_cfg_dir: Path) -> Path:
    rclone_cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg = rclone_cfg_dir / "rclone.conf"
    cfg.write_text("[yandex_native]\ntype = yandex\n",
                   encoding="utf-8")
    cfg.chmod(0o600)
    return cfg


@pytest.fixture
def env_setup(tmp_path: Path):
    """Изолированное окружение для одного теста."""
    backup_dir = tmp_path / "backups"
    staging_dir = tmp_path / "offsite-staging"
    rclone_cfg_dir = tmp_path / "rclone-cfg"
    bin_dir = tmp_path / "bin"

    backup_dir.mkdir(parents=True, exist_ok=True)
    staging_dir.mkdir(parents=True, exist_ok=True)
    bin_dir.mkdir(parents=True, exist_ok=True)

    rclone_cfg = _make_rclone_config(rclone_cfg_dir)

    rclone_log = tmp_path / "rclone_calls.log"
    notify_log = tmp_path / "notify_calls.log"
    rclone_log.touch()
    notify_log.touch()

    return {
        "tmp": tmp_path,
        "backup_dir": backup_dir,
        "staging_dir": staging_dir,
        "rclone_cfg": rclone_cfg,
        "bin_dir": bin_dir,
        "rclone_log": rclone_log,
        "notify_log": notify_log,
    }


def _run_script(env_setup: dict, *, expect_rc: int = 0,
                extra_env: dict | None = None, timeout: int = 30):
    env = {
        "PATH": f"{env_setup['bin_dir']}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME": str(env_setup["tmp"]),
        "LANG": "C",
        "BACKUP_DIR": str(env_setup["backup_dir"]),
        "STAGING_DIR": str(env_setup["staging_dir"]),
        "RCLONE_CONFIG": str(env_setup["rclone_cfg"]),
        "RCLONE_REMOTE": "yandex_native:test-backup",
        "OFFSITE_RETENTION_DAYS": "30",
        "NOTIFY_SCRIPT": str(env_setup["bin_dir"] / "notify_admin.sh"),
        "RCLONE_LOG": str(env_setup["rclone_log"]),
        "NOTIFY_LOG": str(env_setup["notify_log"]),
    }
    if extra_env:
        env.update({k: str(v) for k, v in extra_env.items()})

    # Используем абсолютный /bin/bash, а не "/usr/bin/env bash",
    # чтобы запуск самого bash не зависел от PATH — это позволяет
    # тесту "rclone не установлен" (test_03) подать PATH без /usr/bin.
    proc = subprocess.run(
        ["/bin/bash", str(BACKUP_OFFSITE_SH)],
        env=env, capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != expect_rc:
        pytest.fail(
            f"rc={proc.returncode} (expected {expect_rc})\n"
            f"--- STDOUT ---\n{proc.stdout}\n"
            f"--- STDERR ---\n{proc.stderr}\n"
            f"--- RCLONE_LOG ---\n{env_setup['rclone_log'].read_text()}\n"
            f"--- NOTIFY_LOG ---\n{env_setup['notify_log'].read_text()}\n"
        )
    return proc


def _rclone_calls(env_setup: dict) -> list[str]:
    text = env_setup["rclone_log"].read_text()
    return [line.split(" | ", 1)[0] for line in text.strip().splitlines() if line]


def _notify_events(env_setup: dict) -> list[str]:
    text = env_setup["notify_log"].read_text()
    out = []
    for line in text.strip().splitlines():
        parts = line.split()
        if len(parts) >= 2:
            out.append(parts[1])
    return out


# =========================================================================
# Tests
# =========================================================================

def test_01_happy_path(env_setup):
    """Локальный бэкап есть, rclone OK, hashsum пустой (WebDAV без hash) → успех."""
    _make_backup(env_setup["backup_dir"])
    _make_rclone_stub(env_setup["bin_dir"])
    _make_notify_stub(env_setup["bin_dir"])

    proc = _run_script(env_setup, expect_rc=0)

    assert _rclone_calls(env_setup) == ["copyto", "copyto", "hashsum", "delete", "lsf"]
    assert _notify_events(env_setup) == ["offsite-recovered"]
    assert "OK: offsite backup complete" in proc.stdout
    # staging очищен trap'ом EXIT
    leftovers = list(env_setup["staging_dir"].glob("*.gz*"))
    assert leftovers == [], f"в staging остались файлы: {leftovers}"


def test_02_no_local_backup(env_setup):
    """BACKUP_DIR пуст → die на шаге 1, offsite-failed."""
    _make_rclone_stub(env_setup["bin_dir"])
    _make_notify_stub(env_setup["bin_dir"])

    proc = _run_script(env_setup, expect_rc=1)

    assert "нет файлов smoktolk_*.db" in proc.stdout
    assert _rclone_calls(env_setup) == []
    assert "offsite-failed" in _notify_events(env_setup)


def test_03_rclone_not_installed(env_setup):
    """rclone отсутствует в PATH → die, offsite-failed."""
    _make_backup(env_setup["backup_dir"])
    _make_notify_stub(env_setup["bin_dir"])
    # rclone-stub НЕ создаём, и обрезаем PATH до одного только bin_dir.
    # bash сам запустится через абсолютный /bin/bash (см. _run_script),
    # так что урезанный PATH не мешает интерпретатору.
    proc = _run_script(env_setup, expect_rc=1,
                       extra_env={"PATH": str(env_setup["bin_dir"])})
    assert "rclone не установлен" in proc.stdout
    assert "offsite-failed" in _notify_events(env_setup)


def test_04_rclone_config_unreadable(env_setup):
    """RCLONE_CONFIG не существует → die."""
    _make_backup(env_setup["backup_dir"])
    _make_rclone_stub(env_setup["bin_dir"])
    _make_notify_stub(env_setup["bin_dir"])

    proc = _run_script(
        env_setup, expect_rc=1,
        extra_env={"RCLONE_CONFIG": "/nonexistent/rclone.conf"},
    )
    assert "не могу прочитать" in proc.stdout
    assert _rclone_calls(env_setup) == []
    assert "offsite-failed" in _notify_events(env_setup)


def test_05_empty_backup_file(env_setup):
    """Последний smoktolk_*.db существует, но 0 байт → die."""
    p = env_setup["backup_dir"] / "smoktolk_20260514_040000.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"")

    _make_rclone_stub(env_setup["bin_dir"])
    _make_notify_stub(env_setup["bin_dir"])

    proc = _run_script(env_setup, expect_rc=1)
    assert "последний бэкап пустой" in proc.stdout
    assert "offsite-failed" in _notify_events(env_setup)


def test_06_copyto_history_fails(env_setup):
    """Первая загрузка (история) падает → die до latest/hashsum."""
    _make_backup(env_setup["backup_dir"])
    _make_rclone_stub(env_setup["bin_dir"], copyto_history_rc=1)
    _make_notify_stub(env_setup["bin_dir"])

    proc = _run_script(env_setup, expect_rc=1)
    assert "rclone copyto (history) упал" in proc.stdout
    assert _rclone_calls(env_setup) == ["copyto"]
    assert "offsite-failed" in _notify_events(env_setup)


def test_07_copyto_latest_fails(env_setup):
    """Вторая загрузка (latest) падает → die после первой успешной."""
    _make_backup(env_setup["backup_dir"])
    _make_rclone_stub(env_setup["bin_dir"],
                      copyto_history_rc=0, copyto_latest_rc=1)
    _make_notify_stub(env_setup["bin_dir"])

    proc = _run_script(env_setup, expect_rc=1)
    assert "rclone copyto (latest) упал" in proc.stdout
    assert _rclone_calls(env_setup) == ["copyto", "copyto"]
    assert "offsite-failed" in _notify_events(env_setup)


def test_08_hashsum_mismatch(env_setup):
    """Remote sha256 ≠ local → die (integrity FAIL)."""
    _make_backup(env_setup["backup_dir"])
    fake_hash = "deadbeef" * 8  # 64 hex символа
    _make_rclone_stub(
        env_setup["bin_dir"],
        hashsum_output=f"{fake_hash}  smoktolk_20260514_040000.db.gz",
    )
    _make_notify_stub(env_setup["bin_dir"])

    proc = _run_script(env_setup, expect_rc=1)
    assert "integrity FAIL" in proc.stdout
    assert "offsite-failed" in _notify_events(env_setup)
    # copyto×2 успели пройти, hashsum вернул mismatch — до delete/lsf не дошло.
    assert _rclone_calls(env_setup) == ["copyto", "copyto", "hashsum"]


def test_09_hashsum_unsupported(env_setup):
    """
    Если rclone вернул UNSUPPORTED — скрипт пишет 'sverka skipped' и идёт дальше.
    Это нормальное поведение для Яндекс.Диска через WebDAV.
    """
    _make_backup(env_setup["backup_dir"])
    _make_rclone_stub(
        env_setup["bin_dir"],
        hashsum_output="UNSUPPORTED  smoktolk_20260514_040000.db.gz",
    )
    _make_notify_stub(env_setup["bin_dir"])

    proc = _run_script(env_setup, expect_rc=0)
    assert "sverka skipped" in proc.stdout
    assert "OK: offsite backup complete" in proc.stdout
    assert _notify_events(env_setup) == ["offsite-recovered"]


def test_10_concurrent_lock(env_setup):
    """
    Если flock на $STAGING_DIR/.offsite.lock уже взят — скрипт мирно выходит
    с rc=0, БЕЗ вызовов rclone и БЕЗ notify_admin.
    """
    _make_backup(env_setup["backup_dir"])
    _make_rclone_stub(env_setup["bin_dir"])
    _make_notify_stub(env_setup["bin_dir"])

    lock_path = env_setup["staging_dir"] / ".offsite.lock"
    # Держим flock в фоне, пока спим.
    holder = subprocess.Popen(
        ["flock", "-n", str(lock_path), "-c", "sleep 10"],
    )
    try:
        # Подождём, пока flock реально захватит файл.
        for _ in range(40):
            if lock_path.exists():
                break
            time.sleep(0.05)
        # Дать flock-у немного времени реально взять lock (не только создать файл).
        time.sleep(0.2)

        proc = _run_script(env_setup, expect_rc=0)
        assert "предыдущий запуск offsite ещё работает" in proc.stdout
        assert _rclone_calls(env_setup) == []
        assert _notify_events(env_setup) == []
    finally:
        holder.terminate()
        try:
            holder.wait(timeout=5)
        except subprocess.TimeoutExpired:
            holder.kill()
            holder.wait()
