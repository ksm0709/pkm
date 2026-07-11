from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

from click.testing import CliRunner

import pkm.commands.update as update_mod
from pkm.commands.update import update_cmd


REAL_QUIESCE = getattr(update_mod, "_quiesce_running_web_service", None)
REAL_RESTART = getattr(update_mod, "_restart_web_service", None)


def _make_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    cli_dir = repo / "cli"
    cli_dir.mkdir(parents=True)
    (cli_dir / "pyproject.toml").write_text("[project]\nname = 'pkm'\n")
    (repo / ".git").mkdir()
    return repo, cli_dir


def test_restart_reloads_unit_before_start(monkeypatch) -> None:
    calls: list[list[str]] = []

    def run(cmd, **_kwargs):
        command = list(cmd)
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(update_mod.subprocess, "run", run)

    assert REAL_RESTART is not None
    REAL_RESTART()

    assert calls == [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "start", "pkm-web.service"],
        ["systemctl", "--user", "is-active", "--quiet", "pkm-web.service"],
    ]


def test_quiesce_stops_and_verifies_active_user_service(monkeypatch) -> None:
    assert REAL_QUIESCE is not None
    calls: list[list[str]] = []
    responses = iter((0, 0, 3))

    monkeypatch.setattr(update_mod.shutil, "which", lambda _name: "/bin/systemctl")

    def run(cmd, **_kwargs):
        calls.append(list(cmd))
        return SimpleNamespace(returncode=next(responses), stdout="", stderr="")

    monkeypatch.setattr(update_mod.subprocess, "run", run)

    assert REAL_QUIESCE() is True
    assert calls == [
        ["systemctl", "--user", "is-active", "--quiet", "pkm-web.service"],
        ["systemctl", "--user", "stop", "pkm-web.service"],
        ["systemctl", "--user", "is-active", "--quiet", "pkm-web.service"],
    ]


def test_update_stops_live_queue_writer_before_fresh_process_scrub(
    monkeypatch, tmp_path: Path
) -> None:
    repo, cli_dir = _make_repo(tmp_path)
    queue_path = tmp_path / "task_queue.json"
    writer_script = (
        "from pathlib import Path\n"
        "import sys,time\n"
        "path=Path(sys.argv[1])\n"
        "while True:\n"
        " path.write_text('legacy queued payload', encoding='utf-8')\n"
        " time.sleep(0.01)\n"
    )
    writer = subprocess.Popen([sys.executable, "-c", writer_script, str(queue_path)])
    deadline = time.monotonic() + 5
    while not queue_path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert queue_path.exists()

    events: list[str] = []

    def quiesce() -> bool:
        events.append("stop")
        writer.terminate()
        writer.wait(timeout=5)
        return True

    def restart() -> None:
        events.append("restart")

    def fresh_post_update(_executable: Path, _prev_version: str) -> None:
        events.append("post-update")
        assert writer.poll() is not None
        queue_path.unlink(missing_ok=True)
        time.sleep(0.05)
        assert not queue_path.exists()

    monkeypatch.setattr(update_mod, "_quiesce_running_web_service", quiesce)
    monkeypatch.setattr(update_mod, "_restart_web_service", restart)
    monkeypatch.setattr(update_mod, "_run_fresh_post_update", fresh_post_update)
    monkeypatch.setattr(update_mod, "_extra_installed", lambda _probe: False)
    monkeypatch.setattr(update_mod, "load_config", lambda: {})
    monkeypatch.setattr(update_mod, "find_local_cli_dir", lambda: cli_dir)
    monkeypatch.setattr(update_mod, "_resolve_current_pkm_executable", lambda: Path("/installed/bin/pkm"))
    monkeypatch.setattr("pkm.__version__", "2.96.1")

    def run(cmd, **_kwargs):
        command = list(cmd)
        if command == ["git", "-C", str(repo), "branch", "--show-current"]:
            return SimpleNamespace(returncode=0, stdout="main\n", stderr="")
        if command[:4] == ["git", "-C", str(repo), "pull"]:
            events.append("source-update")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[:3] == ["uv", "tool", "install"]:
            events.append("install")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command == ["/installed/bin/pkm", "--version"]:
            return SimpleNamespace(returncode=0, stdout="pkm v3.0.0\n", stderr="")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(update_mod.subprocess, "run", run)
    result = CliRunner().invoke(update_cmd, [])

    if writer.poll() is None:
        writer.terminate()
        writer.wait(timeout=5)

    assert result.exit_code == 0, result.output
    assert events == ["stop", "source-update", "install", "post-update", "restart"]
    assert not queue_path.exists()


def test_failed_update_leaves_previously_active_service_stopped(
    monkeypatch, tmp_path: Path
) -> None:
    repo, cli_dir = _make_repo(tmp_path)
    events: list[str] = []

    monkeypatch.setattr(update_mod, "_quiesce_running_web_service", lambda: events.append("stop") or True)
    monkeypatch.setattr(update_mod, "_restart_web_service", lambda: events.append("restart"))
    monkeypatch.setattr(update_mod, "find_local_cli_dir", lambda: cli_dir)
    monkeypatch.setattr(update_mod, "_resolve_current_pkm_executable", lambda: Path("/installed/bin/pkm"))
    monkeypatch.setattr("pkm.__version__", "2.96.1")

    def run(cmd, **_kwargs):
        command = list(cmd)
        if command == ["git", "-C", str(repo), "pull", "--ff-only"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="failed")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(update_mod.subprocess, "run", run)
    result = CliRunner().invoke(update_cmd, [])

    assert result.exit_code == 1
    assert events == ["stop"]
    assert "service remains stopped" in result.output
    assert "systemctl --user daemon-reload" in result.output
    assert "systemctl --user start pkm-web.service" in result.output


def test_update_docs_require_v2966_forward_bridge() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    docs = (repo_root / "docs" / "cli" / "pkm-update.md").read_text(
        encoding="utf-8"
    )

    assert "v2.96.6" in docs
    assert "forward-migration bridge" in docs
    assert "v2.96.1` remains the temporary rollback target only" in docs
    assert "restarts it only after" in docs
