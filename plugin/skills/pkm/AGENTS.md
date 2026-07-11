<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-19 | Updated: 2026-04-19 -->

# pkm (skill namespace)

## Purpose
PKM skill definitions for the Claude Code plugin. Provides agent workflow skills for Zettelkasten knowledge management, daily note capture, semantic search, and vault maintenance.

## Key Files

| File | Description |
|------|-------------|
| `SKILL.md` | Skill manifest — name, description, trigger keywords, vault structure reference, and core workflow documentation |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `diagnosis/` | `pkm:diagnosis` sub-skill — session PKM tool usage self-check and post-work remediation |
| `workflows/` | Reusable manual multi-step procedures (see `workflows/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- `SKILL.md` is the authoritative trigger and documentation entry point for the `pkm` skill namespace.

### Common Patterns
- The core maintenance procedure (`workflows/zettelkasten-maintenance.md`) defines a deterministic, tool-driven Zettelkasten lifecycle.

<!-- MANUAL: -->
