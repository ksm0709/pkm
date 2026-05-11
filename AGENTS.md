<!-- Generated: 2026-04-19 | Updated: 2026-04-19 -->

# pkm

## Purpose
Terminal-first Personal Knowledge Management CLI for Obsidian vaults. Combines fast daily capture, atomic notes, backlinks, semantic search, vault management, and an AI-ready memory layer. Also ships an MCP server so AI agents can read/write the vault programmatically.

## Key Files

| File | Description |
|------|-------------|
| `README.md` | Project overview, quick-start, and feature summary |
| `CHANGELOG.md` | Version history |
| `CLAUDE.md` | Empty project-level CLAUDE.md (global policy applies) |
| `LICENSE` | License file |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `cli/` | Python CLI package — source, tests, and build config (see `cli/AGENTS.md`) |
| `docs/` | User-facing documentation for every CLI command (see `docs/AGENTS.md`) |
| `plugin/` | Claude Code plugin — hooks and pkm skills (see `plugin/AGENTS.md`) |
| `codex/` | Codex agent hooks for stop-event integration (see `codex/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- All production code lives under `cli/src/pkm/`.
- Documentation lives under `docs/cli/` — keep it in sync when adding commands.
- Plugin skills live under `plugin/skills/pkm/commands/` — update when CLI semantics change.
- Do not commit to hidden state dirs (`.omc/`, `.omx/`, `.claude/`).

### PKM Note Management Principles
- Treat capture and promotion as separate operations.
- Store time-bound memory in `daily/`: session state, progress logs, event notes, transient observations, temporary TODO context, and work-in-flight summaries.
- Use daily subnotes for time-bound material that needs structure, such as meetings, investigations, long session notes, and project-specific day artifacts.
- Store only durable knowledge in `notes/`: concepts, entities, processes, principles, patterns, decisions, and index/hub notes.
- Before creating a note under `notes/`, verify it has a stable definition, long-term scope, at least one meaningful relation or source link, and value without today's date.
- Do not create ordinary session-state or easily deprecated status memories as `notes/` entries. Log them to daily notes instead.
- Existing episodic notes remain readable for compatibility, but new agent behavior should prefer `daily add` or `daily subnote` for episodic state.

### Testing Requirements
- Run `cd cli && uv run pytest` from repo root to execute the full test suite.
- Tests use temporary directories; never write vault data to the real `~/pkm` vault.

### Common Patterns
- CLI uses Click groups; each command group lives in `cli/src/pkm/commands/<name>.py`.
- Vault path resolution goes through `cli/src/pkm/config.py:get_vault()`.

## Dependencies

### External
- Python ≥ 3.10, `uv` package manager
- `click` ≥ 8.0 — CLI framework
- `rich` ≥ 13.0 — terminal formatting
- `mcp` ≥ 1.20 — MCP server protocol
- `sentence-transformers` (optional) — semantic search embeddings
- `tiny-agent-py` (optional, local path) — air-gapped LLM worker for `pkm ask`

<!-- MANUAL: -->

## Commit Message Rules

All commits in this project must use a typed intent line:

```text
<type>: <why this change exists>
```

The type prefix is mandatory. Use the smallest accurate type, for example:
- `feat:` for user-visible features or capabilities
- `fix:` or `bug:` for defect fixes
- `chore:` for maintenance, tooling, generated config, or non-user-facing upkeep
- `docs:` for documentation-only changes
- `test:` for test-only changes
- `refactor:` for behavior-preserving code restructuring
- `perf:` for performance changes
- `build:` or `ci:` for packaging, dependency, or pipeline changes
- `revert:` for reverting prior commits

The subject after the type must still describe intent/why, not just what files changed.
When using the Lore Commit Protocol, keep its body and trailers, but the first line
must still start with the typed prefix, for example:

```text
fix: Preserve ask availability when configured LLM is unavailable

Configured pkm ask defaults could pin the daemon worker to a single Gemini model...

Constraint: Explicit --model selection remains strict because it is a direct user override
Confidence: high
Scope-risk: narrow
Tested: cd cli && uv run pytest
Co-authored-by: OmX <omx@oh-my-codex.dev>
```
