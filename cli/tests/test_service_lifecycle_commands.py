from __future__ import annotations

from types import SimpleNamespace

from click.testing import CliRunner

from pkm.commands.daemon import daemon_group
from pkm.commands.web import web_group


def _runner() -> CliRunner:
    return CliRunner(mix_stderr=False)


class FakeSocket:
    def __init__(self, connect_error: Exception | None = None):
        self.connect_error = connect_error
        self.timeout = None
        self.connected = False

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def connect(self, _path: str) -> None:
        if self.connect_error:
            raise self.connect_error
        self.connected = True

    def __enter__(self) -> "FakeSocket":
        return self

    def __exit__(self, *_exc) -> None:
        return None


def test_daemon_status_reports_running_stale_and_stopped(monkeypatch):
    """Daemon status reflects socket reachability and discovered PID state."""
    monkeypatch.setattr("pkm.commands.daemon._get_daemon_pid", lambda: 123)
    monkeypatch.setattr("pkm.commands.daemon._is_daemon_alive", lambda: True)
    result = _runner().invoke(daemon_group, ["status"])
    assert result.exit_code == 0
    assert "running" in result.output
    assert "PID 123" in result.output

    monkeypatch.setattr("pkm.commands.daemon._is_daemon_alive", lambda: False)
    result = _runner().invoke(daemon_group, ["status"])
    assert result.exit_code == 0
    assert "stale" in result.output

    monkeypatch.setattr("pkm.commands.daemon._get_daemon_pid", lambda: None)
    result = _runner().invoke(daemon_group, ["status"])
    assert result.exit_code == 0
    assert "stopped" in result.output
    assert "pkm daemon start" in result.output


def test_daemon_socket_and_pid_helpers_cover_success_and_fallback(monkeypatch):
    """Daemon helpers detect live sockets and fall back to pgrep when psutil is absent."""
    import builtins
    import pkm.commands.daemon as daemon_mod

    fake_socket = FakeSocket()
    monkeypatch.setattr("socket.socket", lambda *_args, **_kwargs: fake_socket)
    assert daemon_mod._is_daemon_alive() is True
    assert fake_socket.timeout == 1.0
    assert fake_socket.connected is True

    monkeypatch.setattr(
        "socket.socket",
        lambda *_args, **_kwargs: FakeSocket(connect_error=ConnectionRefusedError()),
    )
    assert daemon_mod._is_daemon_alive() is False

    original_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "psutil":
            raise ImportError("psutil missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    monkeypatch.setattr(
        "pkm.commands.daemon.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="456\n", returncode=0),
    )
    assert daemon_mod._get_daemon_pid() == 456


def test_daemon_start_stop_restart_and_logs(monkeypatch, tmp_path):
    """Lifecycle commands avoid duplicate starts, signal PIDs, restart, and show logs."""
    monkeypatch.setattr("pkm.commands.daemon.SOCKET_PATH", tmp_path / "daemon.sock")
    monkeypatch.setattr("pkm.commands.daemon.LOG_PATH", tmp_path / "daemon.log")

    monkeypatch.setattr("pkm.commands.daemon._is_daemon_alive", lambda: True)
    result = _runner().invoke(daemon_group, ["start"])
    assert result.exit_code == 0
    assert "already running" in result.output

    popen_calls = []
    monkeypatch.setattr("pkm.commands.daemon._is_daemon_alive", lambda: False)
    monkeypatch.setattr(
        "pkm.commands.daemon.subprocess.Popen",
        lambda *args, **kwargs: (
            popen_calls.append((args, kwargs)) or SimpleNamespace(pid=789)
        ),
    )
    result = _runner().invoke(daemon_group, ["start"])
    assert result.exit_code == 0
    assert "Daemon started" in result.output
    assert popen_calls[0][0][0][-2:] == ["-m", "pkm.daemon"]

    monkeypatch.setattr(
        "pkm.commands.daemon.subprocess.Popen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("blocked")),
    )
    result = _runner().invoke(daemon_group, ["start"])
    assert result.exit_code == 1
    assert "Failed to start daemon" in result.output

    monkeypatch.setattr("pkm.commands.daemon._get_daemon_pid", lambda: None)
    result = _runner().invoke(daemon_group, ["stop"])
    assert result.exit_code == 0
    assert "not running" in result.output

    kill_calls = []
    monkeypatch.setattr("pkm.commands.daemon._get_daemon_pid", lambda: 321)
    monkeypatch.setattr(
        "pkm.commands.daemon.os.kill",
        lambda pid, sig: kill_calls.append((pid, sig)),
    )
    result = _runner().invoke(daemon_group, ["stop"])
    assert result.exit_code == 0
    assert "Daemon stopped" in result.output
    assert kill_calls and kill_calls[0][0] == 321

    monkeypatch.setattr(
        "pkm.commands.daemon.os.kill",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError()),
    )
    result = _runner().invoke(daemon_group, ["stop"])
    assert result.exit_code == 1
    assert "Permission denied" in result.output

    alive_checks = iter([True, False, False])
    monkeypatch.setattr("pkm.commands.daemon._get_daemon_pid", lambda: None)
    monkeypatch.setattr(
        "pkm.commands.daemon._is_daemon_alive", lambda: next(alive_checks)
    )
    monkeypatch.setattr(
        "pkm.commands.daemon.subprocess.Popen",
        lambda *_args, **_kwargs: SimpleNamespace(pid=987),
    )
    monkeypatch.setattr("pkm.commands.daemon.time.sleep", lambda *_args: None)
    result = _runner().invoke(daemon_group, ["restart"])
    assert result.exit_code == 0

    result = _runner().invoke(daemon_group, ["logs"])
    assert result.exit_code == 0
    assert "No log file found" in result.output

    (tmp_path / "daemon.log").write_text("one\ntwo\nthree\n", encoding="utf-8")
    result = _runner().invoke(daemon_group, ["logs", "--lines", "2"])
    assert result.exit_code == 0
    assert "two" in result.output
    assert "three" in result.output
    assert "one" not in result.output

    exec_calls = []
    monkeypatch.setattr(
        "pkm.commands.daemon.os.execvp",
        lambda file, args: exec_calls.append((file, args)),
    )
    result = _runner().invoke(daemon_group, ["logs", "--follow"])
    assert result.exit_code == 0
    assert exec_calls == [
        ("tail", ["tail", "-n50", "-f", str(tmp_path / "daemon.log")])
    ]


def test_web_systemctl_commands_stream_output_and_exit_codes(monkeypatch):
    """Web service commands delegate to systemctl and preserve its status."""
    run_calls = []
    monkeypatch.setattr(
        "pkm.commands.web.web_unit_path",
        lambda: SimpleNamespace(exists=lambda: True),
    )

    def fake_run(cmd, **_kwargs):
        run_calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr("pkm.commands.web.subprocess.run", fake_run)

    for command, systemctl_args in [
        ("start", ["systemctl", "--user", "start", "pkm-web"]),
        ("stop", ["systemctl", "--user", "stop", "pkm-web"]),
        ("restart", ["systemctl", "--user", "restart", "pkm-web"]),
        ("status", ["systemctl", "--user", "status", "pkm-web", "--no-pager"]),
        ("enable", ["systemctl", "--user", "enable", "pkm-web"]),
    ]:
        result = _runner().invoke(web_group, [command])
        assert result.exit_code == 0
        assert "ok" in result.output
        assert run_calls[-1] == systemctl_args

    monkeypatch.setattr(
        "pkm.commands.web.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=5, stdout="", stderr="failed\n"
        ),
    )
    result = _runner().invoke(web_group, ["status"])
    assert result.exit_code == 5
    assert "failed" in result.stderr

    monkeypatch.setattr(
        "pkm.commands.web.subprocess.run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError()),
    )
    result = _runner().invoke(web_group, ["start"])
    assert result.exit_code == 127
    assert "systemctl not found" in result.stderr


def test_web_systemctl_commands_explain_missing_unit(monkeypatch, tmp_path):
    """Fresh installs need `pkm web setup` before service commands work."""
    run_calls = []
    unit_path = tmp_path / "pkm-web.service"

    monkeypatch.setattr("pkm.commands.web.web_unit_path", lambda: unit_path)
    monkeypatch.setattr(
        "pkm.commands.web.subprocess.run",
        lambda cmd, **_kwargs: run_calls.append(cmd),
    )

    result = _runner().invoke(web_group, ["start"])

    assert result.exit_code == 5
    assert "pkm-web.service is not installed" in result.output
    assert "pkm web setup" in result.output
    assert run_calls == []


def test_web_tunnel_happy_path_prints_detected_pwa_url(monkeypatch):
    """Web tunnel prints the detected PWA URL and uses quick-tunnel args."""

    class FakeTunnelProcess:
        def __init__(self, lines):
            self.stdout = iter(lines)

        def wait(self, timeout=None):
            return 0

    proc = FakeTunnelProcess(
        [
            "starting\n",
            "visit https://abc-123.trycloudflare.com now\n",
        ]
    )
    popen_calls = []
    monkeypatch.setattr(
        "pkm.commands.web.shutil.which", lambda _name: "/bin/cloudflared"
    )
    monkeypatch.setattr(
        "pkm.commands.web.subprocess.Popen",
        lambda *args, **kwargs: popen_calls.append((args, kwargs)) or proc,
    )

    result = _runner().invoke(web_group, ["tunnel", "--port", "9999"])
    assert result.exit_code == 0
    assert "PWA install URL" in result.output
    assert "https://abc-123.trycloudflare.com" in result.output
    assert popen_calls[0][0][0] == [
        "/bin/cloudflared",
        "tunnel",
        "--url",
        "http://127.0.0.1:9999",
    ]
