"""Тесты для scripts/backup_full_offsite_healthcheck.sh (PR #ops-offsite-full-tar).

Скрипт делает: `rclone lsl REMOTE/LATEST_NAME` → парсит mtime из 2-й и 3-й
колонки → сравнивает возраст с MAX_AGE_HOURS. MIN_SIZE проверки НЕТ
(её делает основной скрипт через "архив <1024 байт" check).

Формат rclone lsl:
    {SIZE:>9} {YYYY-MM-DD} {HH:MM:SS.NNNNNNNNN} {PATH}
Например:
    104857600 2026-05-15 08:30:00.123456789 smoktolk-full-latest.tar.gz

Покрытие:
1. happy path: свежий файл → exit 0, "OK: ... age="
2. файл не найден (lsl даёт "not found") → fail "не найден"
3. файл слишком старый → fail "слишком старый"
4. mtime в будущем (>1ч вперёд) → fail "в будущем"
5. rclone не установлен → fail "rclone не установлен"
6. rclone.conf нечитаем → fail "не читается"
7. lsl даёт пустой вывод → fail "не найден"
"""
import stat
import subprocess
import textwrap
from datetime import datetime, timedelta
from pathlib import Path



REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "backup_full_offsite_healthcheck.sh"


def _chmod_exec(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _make_stub(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    _chmod_exec(path)


def _make_notify_stub(bin_dir: Path) -> None:
    body = textwrap.dedent("""\
        #!/bin/bash
        : "${NOTIFY_LOG:?NOTIFY_LOG must be set}"
        echo "$1" >> "$NOTIFY_LOG"
        exit 0
    """)
    _make_stub(bin_dir / "notify_admin.sh", body)


def _make_rclone_stub(bin_dir: Path, *,
                      lsl_output: str = "",
                      lsl_rc: int = 0) -> None:
    """Stub `rclone lsl` — отдаёт фиксированный вывод. Скрипт всегда даёт
    rc=0 на rclone-вызов (из-за `|| true`), но проверяет stdout. Поэтому
    для случая 'файл не найден' возвращаем grep-able строку вроде
    'directory not found' или просто пусто."""
    # Используем base64-кодировку lsl_output, чтобы безопасно протащить
    # любые символы (двоеточия, точки, переводы строк) без эскейпинга.
    import base64
    encoded = base64.b64encode(lsl_output.encode("utf-8")).decode("ascii")
    body = textwrap.dedent(f"""\
        #!/bin/bash
        : "${{RCLONE_LOG:?RCLONE_LOG must be set}}"
        echo "rclone $*" >> "$RCLONE_LOG"
        cmd=""
        skip_next=0
        for arg in "$@"; do
            if [ "$skip_next" -eq 1 ]; then skip_next=0; continue; fi
            case "$arg" in
                --config|--timeout) skip_next=1 ;;
                --*) ;;
                *) cmd="$arg"; break ;;
            esac
        done
        case "$cmd" in
            lsl)
                echo '{encoded}' | base64 -d
                exit {lsl_rc}
                ;;
            *)
                echo "stub: unknown '$cmd'" >&2
                exit 1
                ;;
        esac
    """)
    _make_stub(bin_dir / "rclone", body)


def _build_env(tmp_path: Path, *, extra: dict | None = None) -> dict:
    bin_dir = tmp_path / "bin"
    rclone_conf = tmp_path / "rclone.conf"
    rclone_conf.write_text("[fake]\ntype=local\n")
    notify_log = tmp_path / "notify.log"
    rclone_log = tmp_path / "rclone.log"

    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "RCLONE_CONFIG": str(rclone_conf),
        "RCLONE_REMOTE": "fake:test",
        "LATEST_NAME": "smoktolk-full-latest.tar.gz",
        "MAX_AGE_HOURS": "30",
        "NOTIFY_SCRIPT": str(bin_dir / "notify_admin.sh"),
        "NOTIFY_LOG": str(notify_log),
        "RCLONE_LOG": str(rclone_log),
    }
    if extra:
        env.update(extra)
    return env


def _run(env: dict, *, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT)],
        env=env, capture_output=True, text=True, timeout=timeout,
    )


def _fmt_lsl(mtime: datetime, size: int = 104857600,
             name: str = "smoktolk-full-latest.tar.gz") -> str:
    """Эмуляция rclone lsl: '   SIZE YYYY-MM-DD HH:MM:SS.NNNNNNNNN PATH'."""
    return f"{size:>9} {mtime.strftime('%Y-%m-%d %H:%M:%S')}.000000000 {name}\n"


# =========================================================================

def test_01_happy_path_fresh_file(tmp_path: Path) -> None:
    """Свежий файл (1 час назад) → exit 0, 'OK: ... age='."""
    bin_dir = tmp_path / "bin"
    fresh = datetime.now() - timedelta(hours=1)
    _make_rclone_stub(bin_dir, lsl_output=_fmt_lsl(fresh))
    _make_notify_stub(bin_dir)
    env = _build_env(tmp_path)

    result = _run(env)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "OK:" in result.stdout
    assert "age=" in result.stdout

    # При успехе notify_admin.sh НЕ должен вызываться
    notify_log = tmp_path / "notify.log"
    assert not notify_log.exists() or notify_log.read_text().strip() == ""


def test_02_file_not_found(tmp_path: Path) -> None:
    """rclone отвечает 'directory not found' → fail + offsite-full-failed."""
    bin_dir = tmp_path / "bin"
    _make_rclone_stub(bin_dir,
                      lsl_output="2024/01/15 12:00:00 ERROR : directory not found\n")
    _make_notify_stub(bin_dir)
    env = _build_env(tmp_path)

    result = _run(env)
    assert result.returncode == 1
    assert "не найден" in result.stdout
    notify_log = (tmp_path / "notify.log").read_text()
    assert "offsite-full-failed" in notify_log


def test_03_file_too_old(tmp_path: Path) -> None:
    """Файл старше MAX_AGE_HOURS → fail 'слишком старый'."""
    bin_dir = tmp_path / "bin"
    old = datetime.now() - timedelta(hours=48)
    _make_rclone_stub(bin_dir, lsl_output=_fmt_lsl(old))
    _make_notify_stub(bin_dir)
    env = _build_env(tmp_path, extra={"MAX_AGE_HOURS": "30"})

    result = _run(env)
    assert result.returncode == 1, f"stdout={result.stdout}"
    assert "слишком старый" in result.stdout
    notify_log = (tmp_path / "notify.log").read_text()
    assert "offsite-full-failed" in notify_log


def test_04_mtime_in_future(tmp_path: Path) -> None:
    """mtime больше чем на час в будущем → fail 'в будущем' (TZ-баг)."""
    bin_dir = tmp_path / "bin"
    future = datetime.now() + timedelta(hours=5)
    _make_rclone_stub(bin_dir, lsl_output=_fmt_lsl(future))
    _make_notify_stub(bin_dir)
    env = _build_env(tmp_path)

    result = _run(env)
    assert result.returncode == 1, f"stdout={result.stdout}"
    assert "в будущем" in result.stdout
    notify_log = (tmp_path / "notify.log").read_text()
    assert "offsite-full-failed" in notify_log


def test_05_rclone_not_installed(tmp_path: Path) -> None:
    """rclone отсутствует в PATH → fail."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _make_notify_stub(bin_dir)
    shadow = tmp_path / "shadow"
    shadow.mkdir()
    for util in ("bash", "awk", "date", "cat", "head", "cut", "grep", "echo",
                 "wc", "stat", "find", "mkdir", "touch", "chown", "sleep",
                 "base64"):
        real = subprocess.run(["which", util], capture_output=True, text=True).stdout.strip()
        if real:
            (shadow / util).symlink_to(real)
    env = _build_env(tmp_path)
    env["PATH"] = f"{bin_dir}:{shadow}"

    result = _run(env)
    assert result.returncode == 1, f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    assert "rclone не установлен" in result.stdout
    notify_log = (tmp_path / "notify.log").read_text()
    assert "offsite-full-failed" in notify_log


def test_06_rclone_config_unreadable(tmp_path: Path) -> None:
    """rclone.conf отсутствует → fail 'не читается'."""
    bin_dir = tmp_path / "bin"
    _make_rclone_stub(bin_dir, lsl_output="")
    _make_notify_stub(bin_dir)
    env = _build_env(tmp_path)
    Path(env["RCLONE_CONFIG"]).unlink()

    result = _run(env)
    assert result.returncode == 1
    assert "не читается" in result.stdout
    notify_log = (tmp_path / "notify.log").read_text()
    assert "offsite-full-failed" in notify_log


def test_07_lsl_empty_output(tmp_path: Path) -> None:
    """rclone lsl даёт пустой вывод → fail 'не найден'."""
    bin_dir = tmp_path / "bin"
    _make_rclone_stub(bin_dir, lsl_output="")
    _make_notify_stub(bin_dir)
    env = _build_env(tmp_path)

    result = _run(env)
    assert result.returncode == 1
    assert "не найден" in result.stdout
    notify_log = (tmp_path / "notify.log").read_text()
    assert "offsite-full-failed" in notify_log
