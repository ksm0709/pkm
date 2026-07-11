"""Phase B contracts for active docs, bundled guidance, frontend residue, and CI."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ACTIVE_GUIDANCE = (
    REPO_ROOT / "README.md",
    REPO_ROOT / "AGENTS.md",
    REPO_ROOT / "cli/AGENTS.md",
    REPO_ROOT / "cli/src/pkm/AGENTS.md",
    REPO_ROOT / "cli/src/pkm/commands/AGENTS.md",
    REPO_ROOT / "docs/cli/AGENTS.md",
    REPO_ROOT / "plugin/skills/pkm/AGENTS.md",
    REPO_ROOT / "plugin/skills/pkm/workflows/AGENTS.md",
    REPO_ROOT / "docs/cli/pkm-config.md",
    REPO_ROOT / "docs/cli/pkm-hook.md",
    REPO_ROOT / "docs/cli/pkm-mcp.md",
    REPO_ROOT / "docs/cli/pkm-update.md",
    REPO_ROOT / "docs/mcp-server.md",
    REPO_ROOT / "docs/web/api.md",
    REPO_ROOT / "docs/web/frontend.md",
    REPO_ROOT / "plugin/skills/pkm/SKILL.md",
    REPO_ROOT / "plugin/skills/pkm/diagnosis/SKILL.md",
    REPO_ROOT / "plugin/skills/pkm/workflows/zettelkasten-maintenance.md",
)
RETIRED_LITERALS = (
    "pkm_ask",
    "pkm ask",
    "pkm workflow",
    "/ask",
    "/workflows",
    "ask_credentials",
    "Ask Model Credentials",
    "pkm.askSession",
)
GENERATED_RETIRED_LITERALS = (
    "/ask",
    "/workflows",
    "/workflow-history",
    "ask_credentials",
    "Ask Model Credentials",
    "pkm.askSession",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _production_frontend_files() -> list[Path]:
    source = REPO_ROOT / "web-frontend/src"
    files = [
        path
        for path in source.rglob("*")
        if path.is_file()
        and ".test." not in path.name
        and path.suffix in {".ts", ".js", ".svelte", ".json"}
    ]
    files.append(REPO_ROOT / "web-frontend/static/manifest.webmanifest")
    return files


def _generated_static_files() -> list[Path]:
    static = REPO_ROOT / "cli/src/pkm/web/static"
    return [
        path
        for path in static.rglob("*")
        if path.is_file()
        and path.suffix in {".html", ".js", ".css", ".json", ".webmanifest", ".txt"}
    ]


def _matches(paths: list[Path] | tuple[Path, ...], literals: tuple[str, ...]) -> list[str]:
    matches: list[str] = []
    for path in paths:
        content = _text(path)
        for literal in literals:
            if literal in content:
                matches.append(f"{path.relative_to(REPO_ROOT)}: {literal}")
    return matches


def test_retired_feature_docs_are_deleted_and_active_guidance_has_no_runtime_ux() -> None:
    assert not (REPO_ROOT / "docs/cli/pkm-ask.md").exists()
    assert not (REPO_ROOT / "docs/cli/pkm-workflow.md").exists()
    assert all(path.exists() for path in ACTIVE_GUIDANCE)

    assert _matches(ACTIVE_GUIDANCE, RETIRED_LITERALS) == []


def test_active_frontend_source_and_rebuilt_static_have_no_retired_residue() -> None:
    source_matches = _matches(
        _production_frontend_files(),
        GENERATED_RETIRED_LITERALS + ("tiny_agent",),
    )
    static_matches = _matches(_generated_static_files(), GENERATED_RETIRED_LITERALS)

    assert source_matches == []
    assert static_matches == []


def test_hook_and_bundled_skill_prescribe_host_side_mcp_synthesis() -> None:
    hook = _text(REPO_ROOT / "cli/src/pkm/commands/hook.py")
    skill = _text(REPO_ROOT / "plugin/skills/pkm/SKILL.md")
    combined = f"{hook}\n{skill}"

    assert "pkm_ask" not in combined
    assert "pkm ask" not in combined
    assert "search" in skill.lower()
    assert "get_note_neighbors" in skill
    assert "read_note" in skill


def test_v3_migration_and_rollback_are_explicit_and_reversible() -> None:
    migration_path = REPO_ROOT / "docs/migrations/v3.md"
    rollback_path = REPO_ROOT / "docs/rollback-v2.96.1.md"
    update_path = REPO_ROOT / "docs/cli/pkm-update.md"
    assert migration_path.exists()
    assert rollback_path.exists()
    assert update_path.exists()

    migration = _text(migration_path)
    for required in (
        "search",
        "get_note_neighbors",
        "read_note",
        "workflow.json",
        "workflow-history.jsonl",
        "task_queue.json",
        "pkm.askSession",
        "restart",
    ):
        assert required in migration

    rollback = _text(rollback_path)
    update_docs = _text(update_path)
    assert "v2.96.1" in rollback
    assert "pkm update v2.96.1" in rollback
    assert "PKM_INSTALL_REF=v2.96.1" in rollback
    assert "pkm --version" in rollback

    assert "mktemp -d" in rollback
    assert '"$quarantine_dir/workflow.json"' in rollback

    assert "v2.96.6" in migration
    assert "PKM_INSTALL_REF=v2.96.6" in migration
    assert "v2.96.6" in update_docs
    assert "forward-migration bridge" in update_docs
    assert "v2.96.1` remains the temporary rollback target only" in update_docs
    assert "pkm update v3.0.0" in migration
    assert "systemctl --user daemon-reload" in migration
    assert "systemctl --user restart pkm-web.service" in migration
    assert migration.index("systemctl --user daemon-reload") < migration.index(
        "systemctl --user restart pkm-web.service"
    )

    safe_order = (
        "## 1. Stop all PKM processes",
        "## 2. Inventory and quarantine executable state",
        "## 3. Approval checkpoint",
        "## 4. Install v2.96.1",
        "## 5. Start and verify",
    )
    positions = [rollback.index(heading) for heading in safe_order]
    assert positions == sorted(positions)


def test_ci_and_release_run_frontend_quality_gates_before_publish() -> None:
    ci = _text(REPO_ROOT / ".github/workflows/ci.yml")
    release = _text(REPO_ROOT / ".github/workflows/release.yml")
    required_commands = (
        "pnpm install --frozen-lockfile",
        "pnpm exec svelte-kit sync",
        "pnpm format:check",
        "pnpm test:unit",
        "pnpm build",
        "pnpm bundle:check",
        "playwright install --with-deps chromium",
        "phase-b-retirement.spec.ts",
        "cmdk-shell.spec.ts",
        "a11y.spec.ts",
    )

    for workflow in (ci, release):
        assert "node-version: 22" in workflow
        assert "version: 10" in workflow
        for command in required_commands:
            assert command in workflow


def test_ci_and_release_build_and_smoke_install_distribution_artifacts() -> None:
    ci = _text(REPO_ROOT / ".github/workflows/ci.yml")
    release = _text(REPO_ROOT / ".github/workflows/release.yml")
    packaging_commands = (
        "uv build --out-dir dist",
        "uv venv .wheel-smoke",
        "uv pip install --python .wheel-smoke/bin/python",
        ".wheel-smoke/bin/pkm --help",
        "import pkm.mcp_server; import pkm.web.server",
    )

    for workflow in (ci, release):
        for command in packaging_commands:
            assert command in workflow
    assert "uv run --python 3.10" in release
    assert "uv run --python 3.12" in release


def test_frontend_build_version_is_deterministic() -> None:
    config = _text(REPO_ROOT / "web-frontend/svelte.config.js")

    assert 'version: { name: "pkm" }' in config
