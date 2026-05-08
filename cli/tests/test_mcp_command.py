from __future__ import annotations

import json
from types import SimpleNamespace

from click.testing import CliRunner

from pkm.commands.mcp import mcp_cmd
from pkm.config import VaultConfig


def _runner() -> CliRunner:
    return CliRunner(mix_stderr=False)


def test_mcp_command_runs_server_with_context_or_named_vault(monkeypatch, tmp_path):
    """The MCP command starts the stdio server using ctx vault or explicit --vault."""
    ctx_vault = VaultConfig(name="ctx", path=tmp_path / "ctx")
    named_vault = VaultConfig(name="named", path=tmp_path / "named")
    calls = []

    monkeypatch.setattr("pkm.mcp_server.run_server", lambda vault: calls.append(vault))
    monkeypatch.setattr("pkm.config.get_vault", lambda name: named_vault)

    result = _runner().invoke(mcp_cmd, [], obj={"vault": ctx_vault})
    assert result.exit_code == 0
    assert calls[-1] == ctx_vault

    result = _runner().invoke(mcp_cmd, ["--vault", "named"], obj={"vault": ctx_vault})
    assert result.exit_code == 0
    assert calls[-1] == named_vault


def test_mcp_install_claude_handles_success_failure_and_missing_cli(monkeypatch):
    """Claude install reports CLI success, stderr failure, and missing executable."""
    run_results = iter(
        [
            SimpleNamespace(returncode=0, stderr=""),
            SimpleNamespace(returncode=1, stderr="nope"),
        ]
    )
    run_calls = []

    def fake_run(cmd, **kwargs):
        run_calls.append((cmd, kwargs))
        return next(run_results)

    monkeypatch.setattr("subprocess.run", fake_run)

    result = _runner().invoke(mcp_cmd, ["install", "claude", "claude"])
    assert result.exit_code == 0
    assert "Installed PKM MCP to Claude Code" in result.output
    assert "Failed to install to Claude Code" in result.stderr
    assert run_calls[0][0] == ["claude", "mcp", "add", "pkm", "--", "pkm", "mcp"]

    monkeypatch.setattr(
        "subprocess.run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError()),
    )
    result = _runner().invoke(mcp_cmd, ["install", "claude"])
    assert result.exit_code == 0
    assert "Claude Code CLI not found" in result.stderr


def test_mcp_install_codex_writes_server_once(monkeypatch, tmp_path):
    """Codex install appends the pkm MCP server and skips existing config."""
    home = tmp_path / "home"
    config_dir = home / ".codex"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.toml"
    config_path.write_text('model = "gpt"\n', encoding="utf-8")
    monkeypatch.setattr("pathlib.Path.home", lambda: home)

    result = _runner().invoke(mcp_cmd, ["install", "codex"])
    assert result.exit_code == 0
    assert "Installed PKM MCP to Codex" in result.output
    text = config_path.read_text(encoding="utf-8")
    assert "[mcp_servers.pkm]" in text
    assert 'args = ["mcp"]' in text

    result = _runner().invoke(mcp_cmd, ["install", "codex"])
    assert result.exit_code == 0
    assert "already configured" in result.output
    assert config_path.read_text(encoding="utf-8").count("[mcp_servers.pkm]") == 1

    config_path.unlink()
    result = _runner().invoke(mcp_cmd, ["install", "codex"])
    assert result.exit_code == 0
    assert "config.toml not found" in result.stderr


def test_mcp_install_opencode_writes_json_once(monkeypatch, tmp_path):
    """OpenCode install updates JSON config and treats missing/duplicate as warnings."""
    home = tmp_path / "home"
    config_dir = home / ".config" / "opencode"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "opencode.json"
    config_path.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
    monkeypatch.setattr("pathlib.Path.home", lambda: home)

    result = _runner().invoke(mcp_cmd, ["install", "opencode"])
    assert result.exit_code == 0
    assert "Installed PKM MCP to OpenCode" in result.output
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["mcp"]["pkm"] == {
        "type": "local",
        "command": ["pkm", "mcp"],
        "enabled": True,
    }

    result = _runner().invoke(mcp_cmd, ["install", "opencode"])
    assert result.exit_code == 0
    assert "already configured" in result.output

    config_path.unlink()
    result = _runner().invoke(mcp_cmd, ["install", "opencode"])
    assert result.exit_code == 0
    assert "opencode.json not found" in result.stderr


def test_mcp_install_defaults_to_all_targets_and_reports_unknown(monkeypatch, tmp_path):
    """No target expands to all known clients; unknown targets are stderr warnings."""
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "config.toml").write_text("", encoding="utf-8")
    (home / ".config" / "opencode").mkdir(parents=True)
    (home / ".config" / "opencode" / "opencode.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    monkeypatch.setattr(
        "subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stderr=""),
    )

    result = _runner().invoke(mcp_cmd, ["install"])
    assert result.exit_code == 0
    assert "Claude Code" in result.output
    assert "Codex" in result.output
    assert "OpenCode" in result.output

    result = _runner().invoke(mcp_cmd, ["install", "unknown"])
    assert result.exit_code == 0
    assert "Unknown target" in result.stderr
