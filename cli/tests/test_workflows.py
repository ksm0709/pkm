"""Tests for pkm.workflows — WorkflowConfig, load_workflows, jitter, hook resolution."""

from __future__ import annotations

import json
import socket
import hashlib
from pathlib import Path


from pkm.workflows import (
    WorkflowConfig,
    load_workflows,
    jitter_minutes,
    resolve_hook,
    sync_installed_workflow_defaults,
    sync_stale_global_workflow_defaults,
)
from pkm.workflows.history import append_workflow_history, read_workflow_history


# ---------------------------------------------------------------------------
# WorkflowConfig loading
# ---------------------------------------------------------------------------


def test_load_workflows_returns_bundled_defaults_when_no_global(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    configs = load_workflows()
    # Bundled default_workflows.json provides at least zettelkasten_maintenance
    ids = [c.id for c in configs]
    assert "zettelkasten_maintenance" in ids
    assert "daily_task_summary" not in ids
    by_id = {workflow.id: workflow for workflow in configs}
    assert by_id["zettelkasten_maintenance"].enabled is False
    assert by_id["zettelkasten_maintenance"].model == "auto"


def test_load_workflows_allows_full_user_defined_daily_task_summary(
    tmp_path, monkeypatch
):
    """Removing the bundled summary workflow must not reserve or break the id."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cfg_dir = tmp_path / ".config" / "pkm"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "workflow.json").write_text(
        json.dumps(
            [
                {
                    "id": "daily_task_summary",
                    "schedule_hour": 8,
                    "jitter_type": "md5_hostname_suffix:summary",
                    "marker_file": "summary-last-run",
                    "system_prompt_template": "custom summary",
                    "pre_hook": "pkm.workflows.hooks:build_daily_summary",
                    "post_hook": None,
                }
            ]
        ),
        encoding="utf-8",
    )

    by_id = {workflow.id: workflow for workflow in load_workflows()}

    assert by_id["daily_task_summary"].system_prompt_template == "custom summary"
    assert by_id["daily_task_summary"].pre_hook == (
        "pkm.workflows.hooks:build_daily_summary"
    )
    assert by_id["daily_task_summary"].enabled is False


def test_load_workflows_skips_partial_legacy_removed_workflow_override(
    tmp_path, monkeypatch
):
    """Partial overrides for removed bundled workflows should not crash loading."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    vault_dir = tmp_path / "vault"
    override_path = vault_dir / ".pkm" / "workflow.json"
    override_path.parent.mkdir(parents=True)
    override_path.write_text(
        json.dumps([{"id": "daily_task_summary", "enabled": False}]),
        encoding="utf-8",
    )

    configs = load_workflows(vault_path=vault_dir)
    ids = {workflow.id for workflow in configs}

    assert "zettelkasten_maintenance" in ids
    assert "daily_task_summary" not in ids


def test_load_workflows_global(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cfg_dir = tmp_path / ".config" / "pkm"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "workflow.json").write_text(
        json.dumps(
            [
                {
                    "id": "test_wf",
                    "schedule_hour": 3,
                    "jitter_type": "md5_hostname",
                    "marker_file": "test-last-run",
                    "system_prompt_template": "Hello {name}",
                    "pre_hook": None,
                    "post_hook": None,
                }
            ]
        )
    )
    configs = load_workflows()
    by_id = {c.id: c for c in configs}
    # test_wf from global should be present
    assert "test_wf" in by_id
    assert by_id["test_wf"].schedule_hour == 3
    assert by_id["test_wf"].system_prompt_template == "Hello {name}"
    assert by_id["test_wf"].pre_hook is None
    # Bundled defaults are also present as baseline
    assert "zettelkasten_maintenance" in by_id


def test_vault_override_merge(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cfg_dir = tmp_path / ".config" / "pkm"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "workflow.json").write_text(
        json.dumps(
            [
                {
                    "id": "wf_a",
                    "schedule_hour": 2,
                    "jitter_type": "md5_hostname",
                    "marker_file": "wf-a-run",
                    "system_prompt_template": "global prompt",
                },
                {
                    "id": "wf_b",
                    "schedule_hour": 8,
                    "jitter_type": "md5_hostname",
                    "marker_file": "wf-b-run",
                    "system_prompt_template": "global b",
                },
            ]
        )
    )

    vault_dir = tmp_path / "vault"
    vault_wf_dir = vault_dir / ".pkm"
    vault_wf_dir.mkdir(parents=True)
    (vault_wf_dir / "workflow.json").write_text(
        json.dumps(
            [
                {
                    "id": "wf_a",
                    "schedule_hour": 10,
                    "jitter_type": "md5_hostname",
                    "marker_file": "wf-a-run",
                    "system_prompt_template": "vault override",
                    "model": "gpt-4o-mini",
                },
                {
                    "id": "wf_c",
                    "schedule_hour": 12,
                    "jitter_type": "md5_hostname",
                    "marker_file": "wf-c-run",
                    "system_prompt_template": "vault only",
                },
            ]
        )
    )

    configs = load_workflows(vault_path=vault_dir)
    by_id = {c.id: c for c in configs}

    assert by_id["wf_a"].schedule_hour == 10
    assert by_id["wf_a"].system_prompt_template == "vault override"
    assert by_id["wf_a"].model == "gpt-4o-mini"
    assert by_id["wf_b"].system_prompt_template == "global b"
    assert "wf_c" in by_id


# ---------------------------------------------------------------------------
# jitter_minutes
# ---------------------------------------------------------------------------


def test_jitter_md5_hostname():
    config = WorkflowConfig(
        id="x",
        schedule_hour=2,
        jitter_type="md5_hostname",
        marker_file="m",
        system_prompt_template="",
    )
    result = jitter_minutes(config)
    hostname = socket.gethostname()
    expected = int(hashlib.md5(hostname.encode()).hexdigest(), 16) % 30
    assert result == expected
    assert 0 <= result < 30


def test_jitter_md5_hostname_suffix():
    config = WorkflowConfig(
        id="x",
        schedule_hour=8,
        jitter_type="md5_hostname_suffix:summary",
        marker_file="m",
        system_prompt_template="",
    )
    result = jitter_minutes(config)
    hostname = socket.gethostname()
    expected = int(hashlib.md5((hostname + "summary").encode()).hexdigest(), 16) % 30
    assert result == expected
    assert 0 <= result < 30


# ---------------------------------------------------------------------------
# resolve_hook
# ---------------------------------------------------------------------------


def test_resolve_hook_none():
    assert resolve_hook(None) is None


def test_resolve_hook_returns_callable():
    fn = resolve_hook("pkm.workflows.hooks:build_daily_summary")
    assert callable(fn)


def test_zettelkasten_default_repairs_malformed_notes_at_end(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    configs = load_workflows()
    by_id = {c.id: c for c in configs}

    assert by_id["zettelkasten_maintenance"].post_hook == (
        "pkm.workflows.hooks:repair_malformed_notes"
    )


def test_zettelkasten_default_prefers_patch_note_for_partial_edits(
    tmp_path, monkeypatch
):
    """Default zettelkasten prompt steers agents away from full-note rewrites."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    configs = load_workflows()
    prompt = {c.id: c for c in configs}["zettelkasten_maintenance"].system_prompt_template

    assert "patch_note" in prompt
    assert "Prefer patch_note for partial edits" in prompt
    assert "update_note only for intentional full-body replacement" in prompt


def test_zettelkasten_default_uses_relation_aware_neighbor_workflow(
    tmp_path, monkeypatch
):
    """Default daemon workflow matches the graph-native relations contract."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    configs = load_workflows()
    prompt = {c.id: c for c in configs}["zettelkasten_maintenance"].system_prompt_template

    assert "get_graph_context" not in prompt
    assert "get_note_neighbors" in prompt
    assert "&relation [[target]] - reason" in prompt
    assert "daily/ are promotion candidates only" in prompt
    assert "notes/ are canonical graph relations" in prompt
    assert "create_daily_subnote" in prompt


def test_sync_stale_global_workflow_defaults_updates_old_zettelkasten_prompt(
    tmp_path, monkeypatch
):
    """pkm update can repair an old copied default prompt without losing schedule."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cfg_dir = tmp_path / ".config" / "pkm"
    cfg_dir.mkdir(parents=True)
    workflow_path = cfg_dir / "workflow.json"
    workflow_path.write_text(
        json.dumps(
            [
                {
                    "id": "zettelkasten_maintenance",
                    "schedule_hour": 4,
                    "jitter_type": "md5_hostname_suffix:local",
                    "marker_file": "zettelkasten-last-run",
                    "system_prompt_template": (
                        "0. CLUSTER DRIFT REVIEW\n"
                        "Call find_surprising_connections(top_n=15), "
                        "create_hub_note(), and get_graph_context."
                    ),
                    "pre_hook": None,
                    "post_hook": None,
                }
            ]
        ),
        encoding="utf-8",
    )

    synced = sync_stale_global_workflow_defaults()

    assert synced == workflow_path
    updated = json.loads(workflow_path.read_text(encoding="utf-8"))[0]
    assert updated["schedule_hour"] == 4
    assert updated["jitter_type"] == "md5_hostname_suffix:local"
    assert updated["post_hook"] == "pkm.workflows.hooks:repair_malformed_notes"
    assert updated["enabled"] is False
    assert "get_graph_context" not in updated["system_prompt_template"]
    assert "get_note_neighbors" in updated["system_prompt_template"]
    assert "&relation [[target]] - reason" in updated["system_prompt_template"]
    assert list(cfg_dir.glob("workflow.json.bak-*"))


def test_sync_stale_global_workflow_defaults_preserves_custom_prompts(
    tmp_path, monkeypatch
):
    """Only recognizable old bundled defaults are automatically rewritten."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cfg_dir = tmp_path / ".config" / "pkm"
    cfg_dir.mkdir(parents=True)
    workflow_path = cfg_dir / "workflow.json"
    custom_prompt = "Custom maintenance prompt with get_note_neighbors and local rules."
    workflow_path.write_text(
        json.dumps(
            [
                {
                    "id": "zettelkasten_maintenance",
                    "schedule_hour": 6,
                    "marker_file": "zettelkasten-last-run",
                    "system_prompt_template": custom_prompt,
                }
            ]
        ),
        encoding="utf-8",
    )

    synced = sync_stale_global_workflow_defaults()

    assert synced is None
    updated = json.loads(workflow_path.read_text(encoding="utf-8"))[0]
    assert updated["system_prompt_template"] == custom_prompt
    assert not list(cfg_dir.glob("workflow.json.bak-*"))


def test_sync_installed_workflow_defaults_updates_copied_bundled_defaults(
    tmp_path, monkeypatch
):
    """pkm update refreshes local copied bundled workflow settings."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cfg_dir = tmp_path / ".config" / "pkm"
    cfg_dir.mkdir(parents=True)
    workflow_path = cfg_dir / "workflow.json"
    default_prompt = {
        workflow.id: workflow for workflow in load_workflows()
    }["zettelkasten_maintenance"].system_prompt_template
    workflow_path.write_text(
        json.dumps(
            [
                {
                    "id": "zettelkasten_maintenance",
                    "schedule_hour": 5,
                    "jitter_type": "md5_hostname_suffix:local",
                    "marker_file": "local-zettel-last-run",
                    "system_prompt_template": default_prompt,
                    "pre_hook": "pkm.workflows.hooks:build_daily_summary",
                    "post_hook": None,
                }
            ]
        ),
        encoding="utf-8",
    )

    synced = sync_installed_workflow_defaults()

    assert synced == workflow_path
    updated = json.loads(workflow_path.read_text(encoding="utf-8"))[0]
    assert updated["schedule_hour"] == 5
    assert updated["jitter_type"] == "md5_hostname_suffix:local"
    assert updated["marker_file"] == "local-zettel-last-run"
    assert updated["enabled"] is False
    assert updated["pre_hook"] is None
    assert updated["post_hook"] == "pkm.workflows.hooks:repair_malformed_notes"
    assert list(cfg_dir.glob("workflow.json.bak-*"))


def test_workflow_history_jsonl_reads_newest_filters_limits_and_skips_corrupt_lines(
    tmp_path,
):
    """Workflow history is vault-local, append-only, filterable, and tolerant."""
    append_workflow_history(
        tmp_path,
        {
            "workflow_id": "weekly",
            "task_id": "task-1",
            "hostname": "host-a",
            "time": "2026-05-10T01:00:00Z",
            "status": "success",
            "source": "manual",
            "phase": "complete",
            "error": None,
            "result_summary": "older",
        },
    )
    history_path = tmp_path / ".pkm" / "workflow-history.jsonl"
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write("{not-json\n")
    append_workflow_history(
        tmp_path,
        {
            "workflow_id": "nightly",
            "task_id": "task-2",
            "hostname": "host-b",
            "time": "2026-05-10T02:00:00Z",
            "status": "failure",
            "source": "scheduled",
            "phase": "agent",
            "error": "model failed",
            "result_summary": "newer",
        },
    )

    all_records = read_workflow_history(tmp_path)
    assert [record["task_id"] for record in all_records] == ["task-2", "task-1"]
    assert read_workflow_history(tmp_path, workflow_id="weekly")[0]["task_id"] == (
        "task-1"
    )
    assert read_workflow_history(tmp_path, limit=1) == [all_records[0]]


# ---------------------------------------------------------------------------
# build_daily_summary hook
# ---------------------------------------------------------------------------


def test_build_daily_summary_basic(tmp_path):
    from pkm.config import VaultConfig
    from pkm.workflows.hooks import build_daily_summary
    from datetime import date

    vault = VaultConfig(name="test", path=tmp_path)
    daily_dir = tmp_path / "daily"
    daily_dir.mkdir()

    today = str(date.today())
    result = build_daily_summary(vault, today)

    assert "rollover_result" in result
    assert isinstance(result["rollover_result"], str)


def test_build_daily_summary_rollover(tmp_path):
    from pkm.config import VaultConfig
    from pkm.workflows.hooks import build_daily_summary
    from datetime import date, timedelta

    vault = VaultConfig(name="test", path=tmp_path)
    daily_dir = tmp_path / "daily"
    daily_dir.mkdir()

    today = date.today()
    yesterday = str(today - timedelta(days=1))
    today_str = str(today)

    yesterday_note = daily_dir / f"{yesterday}.md"
    yesterday_note.write_text(
        f"# {yesterday}\n\n## TODO\n- [ ] buy milk\n- [>] write tests\n",
        encoding="utf-8",
    )

    result = build_daily_summary(vault, today_str)
    assert "rollover_result" in result

    today_note = daily_dir / f"{today_str}.md"
    if today_note.exists():
        content = today_note.read_text()
        assert "buy milk" in content or "write tests" in content


def test_repair_malformed_notes_merges_duplicate_frontmatter(tmp_path):
    from pkm.config import VaultConfig
    from pkm.frontmatter import parse
    from pkm.workflows.hooks import repair_malformed_notes

    vault = VaultConfig(name="test", path=tmp_path)
    vault.notes_dir.mkdir(parents=True)
    note_path = vault.notes_dir / "logger.md"
    note_path.write_text(
        "---\n"
        "id: logger\n"
        "tags: pkm-webapp, logging\n"
        "aliases: []\n"
        "---\n"
        "\n"
        "---\n"
        "id: logger-copy\n"
        "tags: [daily-notes, logging]\n"
        "aliases: [pkm-webapp-logger]\n"
        "---\n"
        "\n"
        "# Logger\n"
        "\n"
        "Actual content.\n",
        encoding="utf-8",
    )

    result = repair_malformed_notes(vault, None)
    repaired_text = note_path.read_text(encoding="utf-8")
    repaired_note = parse(note_path)

    assert result["repaired_count"] == 1
    assert result["repaired_notes"] == ["notes/logger.md"]
    assert repaired_text.count("---") == 2
    assert repaired_note.id == "logger"
    assert repaired_note.tags == ["pkm-webapp", "logging", "daily-notes"]
    assert repaired_note.aliases == ["pkm-webapp-logger"]
    assert repaired_note.body.startswith("# Logger")


def test_repair_malformed_notes_quotes_unquoted_colon_titles(tmp_path):
    from pkm.config import VaultConfig
    from pkm.frontmatter import parse
    from pkm.workflows.hooks import repair_malformed_notes

    vault = VaultConfig(name="test", path=tmp_path)
    vault.notes_dir.mkdir(parents=True)
    note_path = vault.notes_dir / "neo-mcp-opencode-오픈소스-에이전트-허브.md"
    note_path.write_text(
        "---\n"
        "id: neo-mcp-opencode-오픈소스-에이전트-허브\n"
        "title: Neo MCP: opencode 오픈소스 에이전트 허브\n"
        "tags: [hub]\n"
        "---\n"
        "\n"
        "# Hub\n",
        encoding="utf-8",
    )

    result = repair_malformed_notes(vault, None)
    repaired_text = note_path.read_text(encoding="utf-8")
    repaired_note = parse(note_path)

    assert result["repaired_count"] == 1
    assert result["repaired_notes"] == [
        "notes/neo-mcp-opencode-오픈소스-에이전트-허브.md"
    ]
    assert 'title: "Neo MCP: opencode 오픈소스 에이전트 허브"' in repaired_text
    assert repaired_note.title == "Neo MCP: opencode 오픈소스 에이전트 허브"
