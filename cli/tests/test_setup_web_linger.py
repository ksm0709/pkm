"""Tests for `pkm setup --web` Linger gate (F4-6)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from pkm.cli import main


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _fake_loginctl(linger_value: str):
    """Return a fake subprocess.run that emulates loginctl output."""

    def fake_run(cmd, *args, **kwargs):
        result = MagicMock()
        result.returncode = 0
        if isinstance(cmd, (list, tuple)) and len(cmd) > 0 and cmd[0] == "loginctl":
            result.stdout = f"Linger={linger_value}\n"
            result.stderr = ""
        else:
            result.stdout = ""
            result.stderr = ""
        return result

    return fake_run


def test_web_setup_aborts_when_linger_no_and_user_declines(
    mock_home: Path, runner: CliRunner, monkeypatch
) -> None:
    """Linger=no + user declines confirm -> exit non-zero, no token, no unit."""
    monkeypatch.setenv("USER", "testuser")
    monkeypatch.setattr("pkm.commands.setup.subprocess.run", _fake_loginctl("no"))
    # click.confirm reads from stdin; "n\n" declines.
    result = runner.invoke(main, ["setup", "--web"], input="n\n")

    assert result.exit_code != 0, result.output
    token_path = mock_home / ".config" / "pkm" / "web-token"
    unit_path = mock_home / ".config" / "systemd" / "user" / "pkm-web.service"
    assert not token_path.exists(), "token must NOT be written when aborting"
    assert not unit_path.exists(), "unit must NOT be written when aborting"


def test_web_setup_writes_token_and_unit_when_linger_yes(
    mock_home: Path, runner: CliRunner, monkeypatch
) -> None:
    """Linger=yes -> token (chmod 600) + unit file are written."""
    monkeypatch.setenv("USER", "testuser")
    monkeypatch.setattr("pkm.commands.setup.subprocess.run", _fake_loginctl("yes"))

    result = runner.invoke(main, ["setup", "--web"], input="secret\nsecret\n")

    assert result.exit_code == 0, result.output

    token_path = mock_home / ".config" / "pkm" / "web-token"
    password_path = mock_home / ".config" / "pkm" / "web-password"
    unit_path = mock_home / ".config" / "systemd" / "user" / "pkm-web.service"
    assert token_path.exists(), "token file must be written"
    assert password_path.exists(), "password hash file must be written"
    assert unit_path.exists(), "systemd unit must be written"

    # Token mode is 0o600
    mode = token_path.stat().st_mode & 0o777
    assert mode == 0o600, f"expected 0o600, got {oct(mode)}"

    # Token contents: 64 hex chars (32 bytes)
    token = token_path.read_text(encoding="utf-8").strip()
    assert len(token) == 64
    int(token, 16)  # raises if not hex

    # Password hash is stored, never the cleartext password.
    password_hash = password_path.read_text(encoding="utf-8").strip()
    assert password_hash.startswith("pbkdf2_sha256$")
    assert "secret" not in password_hash
    assert (password_path.stat().st_mode & 0o777) == 0o600

    # Unit content sanity
    unit_text = unit_path.read_text(encoding="utf-8")
    assert "[Service]" in unit_text
    assert "ExecStart=%h/.local/bin/pkm daemon run" in unit_text
    assert "--project" not in unit_text
    assert "--extra" not in unit_text
    assert "Environment=PKM_DAEMON_KEEPALIVE=1" in unit_text
    assert "Environment=PKM_WORKER_SANDBOX_PROFILE=trusted-native" in unit_text
    assert "pkm daemon run" in unit_text
    assert "WantedBy=default.target" in unit_text

    # Token printed for the user to copy
    assert "PKM_WEB_TOKEN=" in result.output


def test_web_setup_command_starts_unit_after_writing_auth(
    mock_home: Path, runner: CliRunner, monkeypatch
) -> None:
    """`pkm web setup` runs the full first-time service installation flow."""
    run_calls: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        run_calls.append(list(cmd))
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        if isinstance(cmd, (list, tuple)) and len(cmd) > 0 and cmd[0] == "loginctl":
            result.stdout = "Linger=yes\n"
        return result

    monkeypatch.setenv("USER", "testuser")
    monkeypatch.setattr("pkm.commands.setup.subprocess.run", fake_run)
    monkeypatch.setattr("pkm.commands.web.subprocess.run", fake_run)

    result = runner.invoke(main, ["web", "setup"], input="secret\nsecret\n")

    assert result.exit_code == 0, result.output
    assert (mock_home / ".config" / "pkm" / "web-token").exists()
    assert (mock_home / ".config" / "pkm" / "web-password").exists()
    assert (mock_home / ".config" / "systemd" / "user" / "pkm-web.service").exists()
    assert ["systemctl", "--user", "daemon-reload"] in run_calls
    assert ["systemctl", "--user", "enable", "--now", "pkm-web"] in run_calls
    assert "Reloading and starting pkm-web.service" in result.output
    assert "pkm-web.service enabled and started" in result.output
    assert "Next steps:" not in result.output


def test_web_setup_reset_rewrites_password_hash_and_invalidates_sessions(
    mock_home: Path, runner: CliRunner, monkeypatch
) -> None:
    """`--reset` updates password state and writes a reset marker after hashing."""
    monkeypatch.setenv("USER", "testuser")
    monkeypatch.setattr("pkm.commands.setup.subprocess.run", _fake_loginctl("yes"))

    first = runner.invoke(main, ["setup", "--web"], input="secret\nsecret\n")
    assert first.exit_code == 0, first.output

    password_path = mock_home / ".config" / "pkm" / "web-password"
    reset_path = mock_home / ".config" / "pkm" / "web-session-reset"
    initial_hash = password_path.read_text(encoding="utf-8")

    second = runner.invoke(
        main,
        ["setup", "--web", "--reset"],
        input="new secret\nnew secret\n",
    )
    assert second.exit_code == 0, second.output
    assert password_path.read_text(encoding="utf-8") != initial_hash
    assert reset_path.exists()
    assert "Browser login password reset" in second.output


def test_web_setup_port_option_writes_web_config(
    mock_home: Path, runner: CliRunner, monkeypatch
) -> None:
    """`pkm setup --web --port` persists the daemon port in [web]."""
    import tomllib
    import pkm.config as config_mod

    config_path = mock_home / ".config" / "pkm" / "config"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", config_path)
    monkeypatch.setenv("USER", "testuser")
    monkeypatch.setattr("pkm.commands.setup.subprocess.run", _fake_loginctl("yes"))

    result = runner.invoke(
        main, ["setup", "--web", "--port", "8123"], input="secret\nsecret\n"
    )

    assert result.exit_code == 0, result.output
    with config_path.open("rb") as f:
        saved = tomllib.load(f)
    assert saved["web"]["port"] == "8123"


def test_web_setup_rejects_invalid_port(
    mock_home: Path, runner: CliRunner, monkeypatch
) -> None:
    """Invalid web ports fail before private files are written."""
    monkeypatch.setenv("USER", "testuser")
    monkeypatch.setattr("pkm.commands.setup.subprocess.run", _fake_loginctl("yes"))

    result = runner.invoke(
        main, ["setup", "--web", "--port", "70000"], input="secret\nsecret\n"
    )

    assert result.exit_code == 1
    assert "--port must be an integer" in result.output
    assert not (mock_home / ".config" / "pkm" / "web-token").exists()


def test_sync_existing_web_unit_only_refreshes_installed_unit(
    mock_home: Path,
) -> None:
    """Update migrations refresh stale installed units without creating new ones."""
    from pkm.commands.setup import sync_existing_web_unit

    unit_path = mock_home / ".config" / "systemd" / "user" / "pkm-web.service"
    assert sync_existing_web_unit() is None
    assert not unit_path.exists()

    unit_path.parent.mkdir(parents=True)
    unit_path.write_text(
        "ExecStart=%h/.local/bin/uv run --project %h/repos/pkm-webapp/cli --extra search --extra web pkm daemon run\n",
        encoding="utf-8",
    )

    assert sync_existing_web_unit() == unit_path
    unit_text = unit_path.read_text(encoding="utf-8")
    assert "ExecStart=%h/.local/bin/pkm daemon run" in unit_text
    assert "pkm-webapp" not in unit_text
    assert "--project" not in unit_text
    assert "--extra" not in unit_text


def test_web_command_group_registered(runner: CliRunner) -> None:
    """`pkm web --help` should list service and tunnel commands."""
    result = runner.invoke(main, ["web", "--help"])
    assert result.exit_code == 0, result.output
    out = result.output.lower()
    assert "setup" in out
    assert "start" in out
    assert "stop" in out
    assert "restart" in out
    assert "status" in out
    assert "tunnel" in out


def test_web_tunnel_requires_cloudflared(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`pkm web tunnel` should fail closed when cloudflared is unavailable."""
    monkeypatch.setattr("pkm.commands.web.shutil.which", lambda _name: None)

    result = runner.invoke(main, ["web", "tunnel"])

    assert result.exit_code != 0
    assert "cloudflared is not installed" in result.output
    assert "trycloudflare.com" in result.output


def test_web_tunnel_builds_cloudflared_quick_tunnel_command() -> None:
    """The quick tunnel target should point at the local daemon web server."""
    from pkm.commands.web import _cloudflared_quick_tunnel_args

    assert _cloudflared_quick_tunnel_args(7420) == [
        "tunnel",
        "--url",
        "http://127.0.0.1:7420",
    ]


def test_web_in_vault_free_commands() -> None:
    from pkm.cli import VAULT_FREE_COMMANDS

    assert "web" in VAULT_FREE_COMMANDS
