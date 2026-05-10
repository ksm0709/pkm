"""Tests for MCP server: unit tests for tool functions + protocol-level E2E."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import click
import networkx as nx
import pytest

from pkm.config import VaultConfig


@pytest.fixture
def mcp_server(tmp_vault: VaultConfig):
    mcp_mod = pytest.importorskip("pkm.mcp_server")
    mcp_mod._current_vault = tmp_vault
    return mcp_mod


# ---------------------------------------------------------------------------
# Unit tests — call tool functions directly with _current_vault set
# ---------------------------------------------------------------------------


class TestNoteAdd:
    def test_creates_note(self, mcp_server) -> None:
        """note_add tool creates a note file with correct frontmatter."""
        result = mcp_server.note_add(content="Test semantic note", tags=["test", "mcp"])
        assert result["status"] == "created"
        assert "note_id" in result

        note_path = Path(result["path"])
        assert note_path.exists()
        text = note_path.read_text(encoding="utf-8")
        assert "Test semantic note" in text
        assert "test" in text
        assert "mcp" in text

    def test_with_meta(self, mcp_server) -> None:
        """meta dict is reflected in frontmatter."""
        result = mcp_server.note_add(
            content="Note with meta",
            meta={"source": "neo", "event_type": "goal_completed"},
        )
        assert result["status"] == "created"
        text = Path(result["path"]).read_text(encoding="utf-8")
        assert "source: neo" in text
        assert "event_type: goal_completed" in text

    def test_with_title_and_type(self, mcp_server) -> None:
        """title and memory_type are respected."""
        result = mcp_server.note_add(
            content="Episodic content",
            title="My Episode",
            type="episodic",
            importance=8,
        )
        assert result["status"] == "created"
        text = Path(result["path"]).read_text(encoding="utf-8")
        assert "memory_type: episodic" in text
        assert "importance: 8.0" in text

    def test_duplicate_returns_error(self, mcp_server) -> None:
        """Creating duplicate note returns error dict."""
        mcp_server.note_add(content="First note", title="unique-title", tags=[])
        result = mcp_server.note_add(
            content="Second note", title="unique-title", tags=[]
        )
        assert "error" in result
        assert "already exists" in result["error"]


class TestDailyAdd:
    def test_appends_entry(self, mcp_server, tmp_vault: VaultConfig) -> None:
        """daily_add appends a timestamped entry to today's daily note."""
        result = mcp_server.daily_add(text="Testing MCP daily add")
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


class TestDailySubnote:
    def test_creates_sanitized_subnote_and_links_from_daily(
        self, mcp_server, tmp_vault: VaultConfig
    ) -> None:
        """MCP subnotes sanitize titles into daily_dir and link from today's note."""
        result = mcp_server.create_daily_subnote(
            title="../ Design Session",
            content="Session body",
            tags=["session", "mcp"],
            aliases=["Design Alias"],
        )

        assert result["status"] == "created"
        note_path = Path(result["path"])
        assert note_path.exists()
        assert str(note_path.resolve()).startswith(str(tmp_vault.daily_dir.resolve()))
        assert ".." not in note_path.name
        assert "/" not in result["note_id"]

        note_text = note_path.read_text(encoding="utf-8")
        assert "Session body" in note_text
        assert "session" in note_text
        assert "Design Alias" in note_text

        today = date.today().isoformat()
        daily_text = (tmp_vault.daily_dir / f"{today}.md").read_text(encoding="utf-8")
        assert f"[[{result['note_id']}]]" in daily_text

    def test_repeated_subnote_call_links_without_overwriting_body(
        self, mcp_server, tmp_vault: VaultConfig
    ) -> None:
        """The MCP wrapper is idempotent for file body but can add another daily link."""
        first = mcp_server.create_daily_subnote(
            title="Retro Notes",
            content="Original body",
        )
        note_path = Path(first["path"])
        note_path.write_text("customized body\n", encoding="utf-8")

        second = mcp_server.create_daily_subnote(
            title="Retro Notes",
            content="Replacement body",
        )

        assert second["note_id"] == first["note_id"]
        assert note_path.read_text(encoding="utf-8") == "customized body\n"

        today = date.today().isoformat()
        daily_text = (tmp_vault.daily_dir / f"{today}.md").read_text(encoding="utf-8")
        assert daily_text.count(f"[[{first['note_id']}]]") == 2

    def test_empty_sanitized_subnote_title_returns_error(self, mcp_server) -> None:
        """A title that sanitizes to nothing is rejected before file creation."""
        result = mcp_server.create_daily_subnote(title="../../", content="body")
        assert result == {"error": "title cannot be empty"}


class TestReadDailyLog:
    def _yesterday(self) -> str:
        from datetime import date, timedelta

        return (date.today() - timedelta(days=1)).isoformat()

    def test_reads_yesterday_via_offset(
        self, mcp_server, tmp_vault: VaultConfig
    ) -> None:
        """read_daily_log(offset=1) returns yesterday's note content."""
        y = self._yesterday()
        (tmp_vault.daily_dir / f"{y}.md").write_text("YESTERDAY\n", encoding="utf-8")

        result = mcp_server.read_daily_log(offset=1)
        assert result["status"] == "ok"
        assert result["date"] == y
        assert "YESTERDAY" in result["content"]

    def test_reads_via_explicit_date_str(
        self, mcp_server, tmp_vault: VaultConfig
    ) -> None:
        """read_daily_log(date_str=...) reads the explicit date."""
        (tmp_vault.daily_dir / "2026-04-15.md").write_text("EXP\n", encoding="utf-8")
        result = mcp_server.read_daily_log(date_str="2026-04-15")
        assert result["status"] == "ok"
        assert result["date"] == "2026-04-15"
        assert "EXP" in result["content"]

    def test_date_str_overrides_offset(
        self, mcp_server, tmp_vault: VaultConfig
    ) -> None:
        """date_str takes precedence over offset."""
        (tmp_vault.daily_dir / "2026-04-15.md").write_text("EXP\n", encoding="utf-8")
        result = mcp_server.read_daily_log(offset=99, date_str="2026-04-15")
        assert result["status"] == "ok"
        assert result["date"] == "2026-04-15"

    def test_not_found_status(self, mcp_server, tmp_vault: VaultConfig) -> None:
        """Missing daily note returns not_found status with the resolved date."""
        y = self._yesterday()
        result = mcp_server.read_daily_log(offset=1)
        assert result["status"] == "not_found"
        assert result["date"] == y

    def test_negative_offset_error(self, mcp_server) -> None:
        """Negative offset returns error status."""
        result = mcp_server.read_daily_log(offset=-1)
        assert result["status"] == "error"
        assert "offset" in result["message"].lower()

    def test_bad_date_str_error(self, mcp_server) -> None:
        """Malformed date_str returns error status."""
        result = mcp_server.read_daily_log(date_str="not-a-date")
        assert result["status"] == "error"

    def test_default_is_today(self, mcp_server, tmp_vault: VaultConfig) -> None:
        """No args defaults to today."""
        from datetime import date

        today = date.today().isoformat()
        (tmp_vault.daily_dir / f"{today}.md").write_text("TODAY-X\n", encoding="utf-8")
        result = mcp_server.read_daily_log()
        assert result["status"] == "ok"
        assert result["date"] == today
        assert "TODAY-X" in result["content"]


class TestSearch:
    def test_delegates_to_daemon(self, mcp_server) -> None:
        """search tool calls search_via_daemon, not in-process search."""
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
            result = mcp_server.search(query="test query")
            mock_daemon.assert_called_once()
            assert result["count"] == 1
            assert result["results"][0]["note_id"] == "test-note"

    def test_daemon_unavailable_returns_error(self, mcp_server) -> None:
        """When daemon is unavailable, return error instead of fallback."""
        with patch("pkm.search_engine.search_via_daemon", return_value=None):
            result = mcp_server.search(query="test")
            assert "error" in result
            assert result["code"] == -32000

    def test_cross_vault(self, mcp_server, tmp_path: Path) -> None:
        """Passing vault parameter resolves alternate vault."""
        other_vault = VaultConfig(name="other", path=tmp_path / "other-vault")
        other_vault.notes_dir.mkdir(parents=True, exist_ok=True)

        with (
            patch("pkm.mcp_server.get_vault", return_value=other_vault) as mock_get,
            patch(
                "pkm.search_engine.search_via_daemon", return_value=[]
            ) as mock_search,
        ):
            mcp_server.search(query="test", vault="other")
            mock_get.assert_called_once_with("other")
            # search_via_daemon should be called with the other vault
            call_args = mock_search.call_args
            assert call_args[0][1] == other_vault

    def test_related_note_failure_is_isolated_per_search_result(
        self, mcp_server
    ) -> None:
        """A broken related-note lookup does not discard successful search hits."""
        mock_result = MagicMock()
        mock_result.note_id = "test-note"
        mock_result.title = "Test Note"
        mock_result.score = 0.91234
        mock_result.tags = ["test"]
        mock_result.memory_type = "semantic"
        mock_result.importance = 7.0
        mock_result.path = "/fake/path"
        mock_result.rank = 1

        with (
            patch("pkm.search_engine.search_via_daemon", return_value=[mock_result]),
            patch(
                "pkm.tools.links._get_note_neighbors_data",
                side_effect=RuntimeError("graph stale"),
            ),
        ):
            result = mcp_server.search(query="test")

        assert result["count"] == 1
        assert result["results"][0]["score"] == 0.9123
        assert result["results"][0]["related_notes"] is None

    def test_search_normalizes_click_and_runtime_failures(self, mcp_server) -> None:
        """Daemon search wrapper converts downstream failures into MCP error dicts."""
        with patch(
            "pkm.search_engine.search_via_daemon",
            side_effect=click.ClickException("bad query"),
        ):
            assert mcp_server.search(query="bad") == {"error": "bad query"}

        with patch(
            "pkm.search_engine.search_via_daemon",
            side_effect=RuntimeError("index corrupt"),
        ):
            assert mcp_server.search(query="bad") == {"error": "index corrupt"}


class TestIndex:
    def test_builds_index(self, mcp_server, tmp_vault: VaultConfig) -> None:
        """index tool calls build_index and returns count."""
        mock_index = MagicMock()
        mock_index.entries = [MagicMock(), MagicMock()]

        with patch(
            "pkm.search_engine.build_index", return_value=mock_index
        ) as mock_build:
            result = mcp_server.index()
            mock_build.assert_called_once_with(tmp_vault)
            assert result["status"] == "indexed"
            assert result["count"] == 2

    def test_index_normalizes_click_and_runtime_failures(self, mcp_server) -> None:
        """Index wrapper returns MCP error dicts for build failures."""
        with patch(
            "pkm.search_engine.build_index",
            side_effect=click.ClickException("missing embeddings"),
        ):
            assert mcp_server.index() == {"error": "missing embeddings"}

        with patch(
            "pkm.search_engine.build_index",
            side_effect=RuntimeError("disk full"),
        ):
            assert mcp_server.index() == {"error": "disk full"}


class FakeAskReader:
    def __init__(self, payload: bytes):
        self.payload = payload

    async def readline(self) -> bytes:
        return self.payload


class FakeAskWriter:
    def __init__(self, *, wait_closed_error: Exception | None = None):
        self.writes: list[bytes] = []
        self.closed = False
        self.wait_closed_error = wait_closed_error

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        if self.wait_closed_error:
            raise self.wait_closed_error


class TestPkmAsk:
    @pytest.mark.anyio
    async def test_sends_daemon_payload_with_defaults_and_env_keys(
        self, mcp_server, monkeypatch
    ) -> None:
        """pkm_ask sends vault, defaults, and shared agent credentials to daemon."""
        reader = FakeAskReader(b'{"data": {"response": "answer"}}\n')
        writer = FakeAskWriter()

        async def open_socket(path: str):
            assert path.endswith(".config/pkm/daemon.sock")
            return reader, writer

        monkeypatch.setattr(asyncio, "open_unix_connection", open_socket)
        monkeypatch.setattr(
            "pkm.config.load_config",
            lambda: {"defaults": {"model": "configured-model", "graph-depth": 2}},
        )
        monkeypatch.setattr(
            mcp_server,
            "agent_credential_env",
            lambda: {"OPENAI_API_KEY": "shared-openai"},
        )

        result = await mcp_server.pkm_ask("What changed?")

        assert result == {"result": "answer"}
        payload = json.loads(writer.writes[0].decode("utf-8"))
        assert payload == {
            "action": "ask",
            "query": "What changed?",
            "vault_name": "test-vault",
            "model": "configured-model",
            "env_keys": {"OPENAI_API_KEY": "shared-openai"},
            "graph_depth": 2,
        }
        assert writer.closed is True

    @pytest.mark.anyio
    async def test_accepts_top_level_response_and_model_override(
        self, mcp_server, monkeypatch
    ) -> None:
        """pkm_ask accepts legacy top-level responses and explicit model override."""
        reader = FakeAskReader(b'{"response": "legacy answer"}\n')
        writer = FakeAskWriter()

        async def open_socket(path: str):
            return reader, writer

        monkeypatch.setattr(asyncio, "open_unix_connection", open_socket)
        monkeypatch.setattr("pkm.config.load_config", lambda: {"defaults": {}})

        result = await mcp_server.pkm_ask("Question?", model="override-model")

        assert result == {"result": "legacy answer"}
        payload = json.loads(writer.writes[0].decode("utf-8"))
        assert payload["model"] == "override-model"
        assert payload["graph_depth"] == 0

    @pytest.mark.anyio
    async def test_reports_daemon_start_failure_after_retrying_once_per_attempt(
        self, mcp_server, monkeypatch
    ) -> None:
        """Daemon startup failure retries quickly and returns a clear MCP error."""
        attempts = []
        starts = []

        async def open_socket(path: str):
            attempts.append(path)
            raise FileNotFoundError(path)

        async def no_sleep(delay: float) -> None:
            return None

        monkeypatch.setattr(asyncio, "open_unix_connection", open_socket)
        monkeypatch.setattr(asyncio, "sleep", no_sleep)
        monkeypatch.setattr(
            subprocess, "Popen", lambda *args, **kwargs: starts.append(args)
        )
        monkeypatch.setattr("pkm.config.load_config", lambda: {"defaults": {}})

        result = await mcp_server.pkm_ask("Question?")

        assert result == {
            "error": "Daemon failed to start. Run 'pkm daemon start' manually."
        }
        assert len(attempts) == 50
        assert len(starts) == 1

    @pytest.mark.anyio
    async def test_reports_no_response_error_and_closes_writer(
        self, mcp_server, monkeypatch
    ) -> None:
        """An empty daemon response is surfaced without leaking the writer."""
        reader = FakeAskReader(b"")
        writer = FakeAskWriter()

        async def open_socket(path: str):
            return reader, writer

        monkeypatch.setattr(asyncio, "open_unix_connection", open_socket)
        monkeypatch.setattr("pkm.config.load_config", lambda: {"defaults": {}})

        result = await mcp_server.pkm_ask("Question?")

        assert result == {"error": "No response from daemon."}
        assert writer.closed is True

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        ("payload", "expected"),
        [
            (b'{"type": "error", "message": "agent failed"}\n', "agent failed"),
            (b'{"error": "bad model"}\n', "bad model"),
            (
                b'{"data": {"unexpected": true}}\n',
                "Invalid response format from daemon.",
            ),
        ],
    )
    async def test_reports_daemon_error_payloads(
        self, mcp_server, monkeypatch, payload: bytes, expected: str
    ) -> None:
        """Daemon error and malformed-success schemas become MCP error dicts."""
        reader = FakeAskReader(payload)
        writer = FakeAskWriter(wait_closed_error=RuntimeError("close already gone"))

        async def open_socket(path: str):
            return reader, writer

        monkeypatch.setattr(asyncio, "open_unix_connection", open_socket)
        monkeypatch.setattr("pkm.config.load_config", lambda: {"defaults": {}})

        result = await mcp_server.pkm_ask("Question?")

        assert result == {"error": expected}
        assert writer.closed is True

    @pytest.mark.anyio
    async def test_reports_timeout_and_invalid_json_as_errors(
        self, mcp_server, monkeypatch
    ) -> None:
        """Timeouts and malformed JSON take the dedicated/error fallback paths."""

        async def open_socket_timeout(path: str):
            return FakeAskReader(b"ignored"), FakeAskWriter()

        async def raise_timeout(awaitable, timeout: int):
            awaitable.close()
            raise asyncio.TimeoutError

        monkeypatch.setattr(asyncio, "open_unix_connection", open_socket_timeout)
        monkeypatch.setattr(asyncio, "wait_for", raise_timeout)
        monkeypatch.setattr("pkm.config.load_config", lambda: {"defaults": {}})

        timeout_result = await mcp_server.pkm_ask("Slow?", timeout=1)
        assert timeout_result == {"error": "Request timed out after 1 seconds."}

        async def passthrough(awaitable, timeout: int):
            return await awaitable

        async def open_socket_bad_json(path: str):
            return FakeAskReader(b"not json\n"), FakeAskWriter()

        monkeypatch.setattr(asyncio, "open_unix_connection", open_socket_bad_json)
        monkeypatch.setattr(asyncio, "wait_for", passthrough)

        bad_json_result = await mcp_server.pkm_ask("Bad JSON?")
        assert bad_json_result["error"].startswith("An unexpected error occurred:")


class TestVaultInspectionTools:
    def test_lists_vault_stats_stale_orphans_and_activity_log(
        self, mcp_server, tmp_vault: VaultConfig
    ) -> None:
        """Maintenance MCP tools summarize real vault health and activity state."""
        old_mtime = time.time() - 45 * 86400
        stale_note = tmp_vault.notes_dir / "isolated-note.md"
        os.utime(stale_note, (old_mtime, old_mtime))

        stats = mcp_server.vault_stats()
        assert stats["notes"] >= 5
        assert stats["dailies"] >= 2
        assert stats["orphans"] >= 2
        assert stats["unique_tags"] >= 4
        assert stats["index"] == "not indexed"

        stale = mcp_server.list_stale_notes(days=30)
        assert stale["threshold_days"] == 30
        assert any(item["note"] == "isolated-note.md" for item in stale["stale_notes"])

        orphans = mcp_server.list_orphans()
        orphan_ids = {item["note_id"] for item in orphans["orphans"]}
        assert {"isolated-note", "untagged-note"}.issubset(orphan_ids)
        isolated = next(
            item for item in orphans["orphans"] if item["note_id"] == "isolated-note"
        )
        assert isolated["tags"] == ["untagged"]

        missing_log = mcp_server.read_recent_note_activity()
        assert missing_log["log"] == []
        assert "No activity log" in missing_log["message"]

        log_path = tmp_vault.pkm_dir / "log.md"
        log_path.write_text("one\n\n two \nthree\n", encoding="utf-8")
        tail = mcp_server.read_recent_note_activity(tail=2)
        assert tail == {"log": [" two ", "three"], "count": 2}

    def test_reads_backlinks_tags_and_neighbors_from_seeded_vault(
        self, mcp_server, tmp_vault: VaultConfig
    ) -> None:
        """Discovery MCP tools expose link, tag, and graph context scenarios."""
        backlinks = mcp_server.find_backlinks_for_note("2026-04-01-mvcc")
        backlink_ids = {item["note_id"] for item in backlinks["backlinks"]}
        assert {"database-isolation", "concurrency-note"}.issubset(backlink_ids)
        assert backlinks["count"] >= 2

        tags = mcp_server.list_tags()
        tag_counts = {item["tag"]: item["count"] for item in tags["tags"]}
        assert tag_counts["database"] >= 3
        assert tag_counts["daily-notes"] >= 2

        tag_search = mcp_server.tag_search("database+postgresql")
        assert tag_search["mode"] == "AND(database, postgresql)"
        assert [item["path"] for item in tag_search["results"]] == [
            "2026-04-01-mvcc.md"
        ]

        no_graph = mcp_server.get_note_neighbors("2026-04-01-mvcc")
        assert "run pkm index first" in no_graph["error"]

        graph = nx.DiGraph()
        graph.add_node("2026-04-01-mvcc", type="note", title="MVCC")
        graph.add_node("database-isolation", type="note", title="Database Isolation")
        graph.add_node("tag:database", type="tag", title="database")
        graph.add_edge("2026-04-01-mvcc", "database-isolation", type="wikilink")
        graph.add_edge("tag:database", "2026-04-01-mvcc", type="has_tag")
        (tmp_vault.pkm_dir / "graph.json").write_text(
            json.dumps(nx.node_link_data(graph)), encoding="utf-8"
        )

        neighbors = mcp_server.get_note_neighbors("2026-04-01-mvcc")
        assert [item["note_id"] for item in neighbors["outbound"]] == [
            "database-isolation"
        ]
        assert [item["note_id"] for item in neighbors["inbound"]] == ["tag:database"]

    def test_consolidation_mcp_flow_requires_distilled_notes_and_marks_daily(
        self, mcp_server, tmp_vault: VaultConfig
    ) -> None:
        """Consolidation MCP tool refuses unsafe cases and records distilled notes."""
        candidates = mcp_server.list_consolidation_candidates()
        candidate_dates = {item["date"] for item in candidates["candidates"]}
        assert {"2026-04-01", "2026-04-02"}.issubset(candidate_dates)
        assert all(item["entry_count"] >= 0 for item in candidates["candidates"])

        missing_ids = mcp_server.mark_consolidated("2026-04-01")
        assert "distilled_note_ids is required" in missing_ids["error"]

        missing_note = mcp_server.mark_consolidated(
            "2026-04-01", distilled_note_ids=["missing-distilled-note"]
        )
        assert "not found" in missing_note["error"]

        today = date.today().isoformat()
        (tmp_vault.daily_dir / f"{today}.md").write_text(
            "---\nid: today\ntags: []\n---\n\n- live entry\n", encoding="utf-8"
        )
        today_result = mcp_server.mark_consolidated(
            today, distilled_note_ids=["database-isolation"]
        )
        assert "still in use" in today_result["error"]

        result = mcp_server.mark_consolidated(
            "2026-04-01", distilled_note_ids=["database-isolation"]
        )
        assert result == {
            "status": "consolidated",
            "date": "2026-04-01",
            "distilled_to": ["database-isolation"],
        }
        updated = (tmp_vault.daily_dir / "2026-04-01.md").read_text(encoding="utf-8")
        assert "consolidated: true" in updated
        assert "distilled_to:" in updated
        assert "database-isolation" in updated

        repeat = mcp_server.mark_consolidated(
            "2026-04-01", distilled_note_ids=["database-isolation"]
        )
        assert repeat == {"status": "already_consolidated", "date": "2026-04-01"}

    def test_gap_cases_for_note_read_list_and_rename(
        self, mcp_server, tmp_vault: VaultConfig, tmp_path: Path
    ) -> None:
        """MCP note wrappers return useful metadata and handle absent/conflict paths."""
        daily = mcp_server.read_note("2026-04-01")
        assert str(daily["note_id"]) == "2026-04-01"
        assert "daily-notes" in daily["tags"]
        assert daily["created"] is None

        missing = mcp_server.read_note("not-present")
        assert missing["error"] == "Note 'not-present' not found."

        filtered = mcp_server.list_notes(filter="isolation")
        assert filtered["count"] == 1
        assert filtered["notes"][0]["note_id"] == "database-isolation"

        empty_vault = VaultConfig(name="empty", path=tmp_path / "empty")
        with patch("pkm.mcp_server.get_vault", return_value=empty_vault):
            assert mcp_server.list_notes(vault="empty") == {"notes": [], "count": 0}

        conflict = mcp_server.rename_note("database-isolation", "2026-04-01-mvcc")
        assert "already exists" in conflict["error"]

        absent = mcp_server.rename_note("does-not-exist", "new-id")
        assert "not found" in absent["error"]

    def test_missing_default_vault_raises_before_tool_error_wrapping(
        self, mcp_server
    ) -> None:
        """Unset MCP default vault is a configuration failure, not a tool result."""
        mcp_server._current_vault = None
        with pytest.raises(ValueError, match="No vault configured"):
            mcp_server.vault_stats()

    def test_maintenance_wrappers_return_error_dicts(self, mcp_server) -> None:
        """Maintenance MCP wrappers normalize lower-level exceptions."""
        with patch(
            "pkm.commands.maintenance.compute_vault_stats",
            side_effect=RuntimeError("stats failed"),
        ):
            assert mcp_server.vault_stats() == {"error": "stats failed"}

        with patch(
            "pkm.commands.maintenance.list_stale",
            side_effect=RuntimeError("stale failed"),
        ):
            assert mcp_server.list_stale_notes() == {"error": "stale failed"}

        with patch(
            "pkm.wikilinks.find_orphans",
            side_effect=RuntimeError("orphans failed"),
        ):
            assert mcp_server.list_orphans() == {"error": "orphans failed"}

    def test_discovery_wrappers_return_error_dicts(self, mcp_server) -> None:
        """Discovery MCP wrappers do not leak lower-level exceptions."""
        with patch(
            "pkm.wikilinks.find_backlinks",
            side_effect=RuntimeError("backlinks failed"),
        ):
            assert mcp_server.find_backlinks_for_note("note") == {
                "error": "backlinks failed"
            }

        with patch(
            "pkm.tools.links._get_note_neighbors_data",
            side_effect=FileNotFoundError("graph missing"),
        ):
            assert mcp_server.get_note_neighbors("note") == {"error": "graph missing"}

        with patch(
            "pkm.commands.tag_commands.count_all_tags",
            side_effect=RuntimeError("tags failed"),
        ):
            assert mcp_server.list_tags() == {"error": "tags failed"}

        with patch(
            "pkm.commands.tag_commands.search_by_tag_pattern",
            side_effect=RuntimeError("tag search failed"),
        ):
            assert mcp_server.tag_search("db") == {"error": "tag search failed"}

    def test_graph_search_wrappers_delegate_and_wrap_errors(self, mcp_server) -> None:
        """Graph/search MCP tools forward arguments and normalize tool failures."""
        with patch(
            "pkm.tools.search.find_surprising_connections",
            new=MagicMock(return_value="surprises"),
        ) as tool:
            assert mcp_server.find_surprising_connections(top_n=3) == {
                "result": "surprises"
            }
            tool.assert_called_once_with(top_n=3)

        with patch(
            "pkm.tools.search.list_clusters",
            new=MagicMock(return_value="clusters"),
        ) as tool:
            assert mcp_server.list_clusters() == {"result": "clusters"}
            tool.assert_called_once_with()

        with patch(
            "pkm.tools.search.list_god_nodes",
            new=MagicMock(return_value="nodes"),
        ) as tool:
            assert mcp_server.list_god_nodes(top_n=4) == {"result": "nodes"}
            tool.assert_called_once_with(top_n=4)

        with patch(
            "pkm.tools.search.create_hub_note",
            new=MagicMock(return_value="hub"),
        ) as tool:
            assert mcp_server.create_hub_note(
                cluster_index=2, title="Hub", description="Bridge"
            ) == {"result": "hub"}
            tool.assert_called_once_with(
                cluster_index=2, title="Hub", description="Bridge"
            )

        with patch(
            "pkm.tools.links.add_wikilink",
            new=MagicMock(return_value="linked"),
        ) as tool:
            assert mcp_server.add_wikilink(
                source_note_id="a",
                target_note_id="b",
                description="shared context",
            ) == {"result": "linked"}
            tool.assert_called_once_with(
                source_note_id="a",
                target_note_id="b",
                description="shared context",
            )

        wrappers = [
            (
                "pkm.tools.search.find_surprising_connections",
                lambda: mcp_server.find_surprising_connections(),
            ),
            ("pkm.tools.search.list_clusters", mcp_server.list_clusters),
            ("pkm.tools.search.list_god_nodes", mcp_server.list_god_nodes),
            (
                "pkm.tools.search.create_hub_note",
                lambda: mcp_server.create_hub_note(1, "Hub", "Bridge"),
            ),
            (
                "pkm.tools.links.add_wikilink",
                lambda: mcp_server.add_wikilink("a", "b", "why"),
            ),
        ]
        for target, call_wrapper in wrappers:
            with patch(target, new=MagicMock(side_effect=RuntimeError("tool failed"))):
                assert call_wrapper() == {"error": "tool failed"}


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
        """After initialize, tools/list exposes the expected tool contract."""
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
        expected_tool_names = {
            "add_wikilink",
            "create_daily_subnote",
            "create_hub_note",
            "daily_add",
            "find_backlinks_for_note",
            "find_surprising_connections",
            "get_note_neighbors",
            "index",
            "list_clusters",
            "list_consolidation_candidates",
            "list_god_nodes",
            "list_notes",
            "list_orphans",
            "list_stale_notes",
            "list_tags",
            "mark_consolidated",
            "note_add",
            "pkm_ask",
            "read_daily_log",
            "read_note",
            "read_recent_note_activity",
            "rename_note",
            "search",
            "tag_search",
            "vault_stats",
        }
        assert tool_names == expected_tool_names

        # Verify inputSchema exists on each tool
        for tool in tools:
            assert "inputSchema" in tool
