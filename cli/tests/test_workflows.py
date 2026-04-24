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
)


# ---------------------------------------------------------------------------
# WorkflowConfig loading
# ---------------------------------------------------------------------------


def test_load_workflows_returns_bundled_defaults_when_no_global(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    configs = load_workflows()
    # Bundled default_workflows.json provides at least zettelkasten_maintenance
    ids = [c.id for c in configs]
    assert "zettelkasten_maintenance" in ids
    assert "daily_task_summary" in ids


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
