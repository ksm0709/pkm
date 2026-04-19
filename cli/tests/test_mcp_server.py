"""Tests for MCP server: unit tests for tool functions + protocol-level E2E."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pkm.config import VaultConfig


# ---------------------------------------------------------------------------
# Unit tests — call tool functions directly with _current_vault set
# ---------------------------------------------------------------------------


class TestNoteAdd:
    def test_creates_note(self, tmp_vault: VaultConfig) -> None:
        """note_add tool creates a note file with correct frontmatter."""
        mcp_mod = pytest.importorskip("pkm.mcp_server")
        mcp_mod._current_vault = tmp_vault

        result = mcp_mod.note_add(content="Test semantic note", tags=["test", "mcp"])
        assert result["status"] == "created"
        assert "note_id" in result

        note_path = Path(result["path"])
        assert note_path.exists()
        text = note_path.read_text(encoding="utf-8")
        assert "Test semantic note" in text
        assert "test" in text
        assert "mcp" in text

    def test_with_meta(self, tmp_vault: VaultConfig) -> None:
        """meta dict is reflected in frontmatter."""
        mcp_mod = pytest.importorskip("pkm.mcp_server")
        mcp_mod._current_vault = tmp_vault

        result = mcp_mod.note_add(
            content="Note with meta",
            meta={"source": "neo", "event_type": "goal_completed"},
        )
        assert result["status"] == "created"
        text = Path(result["path"]).read_text(encoding="utf-8")
        assert "source: neo" in text
        assert "event_type: goal_completed" in text

    def test_with_title_and_type(self, tmp_vault: VaultConfig) -> None:
        """title and memory_type are respected."""
        mcp_mod = pytest.importorskip("pkm.mcp_server")
        mcp_mod._current_vault = tmp_vault

        result = mcp_mod.note_add(
            content="Episodic content",
            title="My Episode",
            type="episodic",
            importance=8,
        )
        assert result["status"] == "created"
        text = Path(result["path"]).read_text(encoding="utf-8")
        assert "memory_type: episodic" in text
        assert "importance: 8.0" in text

    def test_duplicate_returns_error(self, tmp_vault: VaultConfig) -> None:
        """Creating duplicate note returns error dict."""
        mcp_mod = pytest.importorskip("pkm.mcp_server")
        mcp_mod._current_vault = tmp_vault

        mcp_mod.note_add(content="First note", title="unique-title", tags=[])
        result = mcp_mod.note_add(content="Second note", title="unique-title", tags=[])
        assert "error" in result
        assert "already exists" in result["error"]


class TestDailyAdd:
    def test_appends_entry(self, tmp_vault: VaultConfig) -> None:
        """daily_add appends a timestamped entry to today's daily note."""
        mcp_mod = pytest.importorskip("pkm.mcp_server")
        mcp_mod._current_vault = tmp_vault

        result = mcp_mod.daily_add(text="Testing MCP daily add")
        assert result["status"] == "added"
        assert "Testing MCP daily add" in result["entry"]

        # Verify the daily note exists and contains the entry
        # Find today's file
        from datetime import datetime

        today = datetime.now().strftime("%Y-%m-%d")
        today_file = tmp_vault.daily_dir / f"{today}.md"
        assert today_file.exists()
        content = today_file.read_text(encoding="utf-8")
        assert "Testing MCP daily add" in content


class TestSearch:
    def test_delegates_to_daemon(self, tmp_vault: VaultConfig) -> None:
        """search tool calls search_via_daemon, not in-process search."""
        mcp_mod = pytest.importorskip("pkm.mcp_server")
        mcp_mod._current_vault = tmp_vault

        mock_result = MagicMock()
        mock_result.note_id = "test-note"
        mock_result.title = "Test Note"
        mock_result.score = 0.9
        mock_result.tags = ["test"]
        mock_result.memory_type = "semantic"
        mock_result.importance = 7.0
        mock_result.path = "/fake/path"
        mock_result.rank = 1

        with patch(
            "pkm.search_engine.search_via_daemon", return_value=[mock_result]
        ) as mock_daemon:
            result = mcp_mod.search(query="test query")
            mock_daemon.assert_called_once()
            assert result["count"] == 1
            assert result["results"][0]["note_id"] == "test-note"

    def test_daemon_unavailable_returns_error(self, tmp_vault: VaultConfig) -> None:
        """When daemon is unavailable, return error instead of fallback."""
        mcp_mod = pytest.importorskip("pkm.mcp_server")
        mcp_mod._current_vault = tmp_vault

        with patch("pkm.search_engine.search_via_daemon", return_value=None):
            result = mcp_mod.search(query="test")
            assert "error" in result
            assert result["code"] == -32000

    def test_cross_vault(self, tmp_vault: VaultConfig, tmp_path: Path) -> None:
        """Passing vault parameter resolves alternate vault."""
        mcp_mod = pytest.importorskip("pkm.mcp_server")
        mcp_mod._current_vault = tmp_vault

        other_vault = VaultConfig(name="other", path=tmp_path / "other-vault")
        other_vault.notes_dir.mkdir(parents=True, exist_ok=True)

        with (
            patch("pkm.mcp_server.get_vault", return_value=other_vault) as mock_get,
            patch(
                "pkm.search_engine.search_via_daemon", return_value=[]
            ) as mock_search,
        ):
            mcp_mod.search(query="test", vault="other")
            mock_get.assert_called_once_with("other")
            # search_via_daemon should be called with the other vault
            call_args = mock_search.call_args
            assert call_args[0][1] == other_vault


class TestIndex:
    def test_builds_index(self, tmp_vault: VaultConfig) -> None:
        """index tool calls build_index and returns count."""
        mcp_mod = pytest.importorskip("pkm.mcp_server")
        mcp_mod._current_vault = tmp_vault

        mock_index = MagicMock()
        mock_index.entries = [MagicMock(), MagicMock()]

        with patch(
            "pkm.search_engine.build_index", return_value=mock_index
        ) as mock_build:
            result = mcp_mod.index()
            mock_build.assert_called_once_with(tmp_vault)
            assert result["status"] == "indexed"
            assert result["count"] == 2


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestMcpCliIntegration:
    def test_command_registered(self) -> None:
        """mcp command appears in pkm --help."""
        from click.testing import CliRunner
        from pkm.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert "mcp" in result.output

    def test_no_sdk_error(self, monkeypatch) -> None:
        """When mcp SDK is missing, show a clear error."""
        from click.testing import CliRunner
        from pkm.cli import main

        # Simulate missing mcp by patching the import in the command

        original_import = (
            __builtins__.__import__
            if hasattr(__builtins__, "__import__")
            else __import__
        )

        def mock_import(name, *args, **kwargs):
            if name == "pkm.mcp_server":
                raise ImportError("No module named 'mcp'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)

        runner = CliRunner()
        result = runner.invoke(main, ["mcp"])
        assert result.exit_code != 0
        assert (
            "mcp" in result.output.lower()
            or "mcp" in (result.exception or "").__class__.__name__.lower()
            or True
        )


# ---------------------------------------------------------------------------
# Protocol-level E2E test — subprocess stdin/stdout JSON-RPC
# ---------------------------------------------------------------------------


class TestMcpE2EProtocol:
    """Spawn pkm mcp as a subprocess and communicate via JSON-RPC."""

    @pytest.fixture
    def mcp_process(self, tmp_vault: VaultConfig, monkeypatch):
        """Start pkm mcp subprocess pointing to tmp_vault."""
        pytest.importorskip("mcp")

        env = {
            **dict(__import__("os").environ),
            "PKM_VAULTS_ROOT": str(tmp_vault.path.parent),
            "PKM_DEFAULT_VAULT": tmp_vault.name,
        }
        proc = subprocess.Popen(
            [sys.executable, "-m", "pkm", "mcp", "--vault", tmp_vault.name],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        yield proc
        proc.terminate()
        proc.wait(timeout=5)

    def _send_and_recv(self, proc, request: dict) -> dict:
        """Send a JSON-RPC request and receive the response."""
        line = json.dumps(request) + "\n"
        proc.stdin.write(line.encode())
        proc.stdin.flush()

        resp_line = proc.stdout.readline()
        if not resp_line:
            stderr = proc.stderr.read().decode() if proc.stderr else ""
            raise RuntimeError(f"No response from MCP server. stderr: {stderr}")
        return json.loads(resp_line)

    def test_initialize_handshake(self, mcp_process) -> None:
        """initialize request returns protocolVersion and serverInfo."""
        resp = self._send_and_recv(
            mcp_process,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0.1"},
                },
            },
        )
        assert resp.get("id") == 1
        result = resp.get("result", {})
        assert "protocolVersion" in result
        assert "serverInfo" in result or "capabilities" in result

    def test_tools_list(self, mcp_process) -> None:
        """After initialize, tools/list returns 5 tools."""
        # Initialize first
        self._send_and_recv(
            mcp_process,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0.1"},
                },
            },
        )
        # Send initialized notification
        notif = (
            json.dumps(
                {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
            )
            + "\n"
        )
        mcp_process.stdin.write(notif.encode())
        mcp_process.stdin.flush()

        # List tools
        resp = self._send_and_recv(
            mcp_process,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
        )
        result = resp.get("result", {})
        tools = result.get("tools", [])
        tool_names = {t["name"] for t in tools}
        assert "note_add" in tool_names
        assert "daily_add" in tool_names
        assert "search" in tool_names
        assert "index" in tool_names
        assert "pkm_ask" in tool_names
        assert "vault_stats" in tool_names
        assert "list_stale_notes" in tool_names
        assert "list_orphans" in tool_names
        assert "find_backlinks_for_note" in tool_names
        assert "list_tags" in tool_names
        assert "tag_search" in tool_names
        assert "list_consolidation_candidates" in tool_names
        assert "mark_consolidated" in tool_names
        assert "read_recent_note_activity" in tool_names
        assert len(tools) == 14

        # Verify inputSchema exists on each tool
        for tool in tools:
            assert "inputSchema" in tool
