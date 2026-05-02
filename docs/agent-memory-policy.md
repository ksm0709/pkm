# Agent Memory Policy

Reference guide for LLM agents using PKM as their persistent memory layer.

---

## Overview

PKM stores agent memories as atomic Obsidian notes with structured frontmatter. Each memory is searchable by semantic similarity and filterable by type, importance, and session. The memory layer is append-only — each new insight becomes its own note.

---

## When to Store a Memory

Store a memory when:
- You make a **decision** that affects future work (architecture choice, API contract, design tradeoff)
- You **discover an error or bug** and how it was fixed
- You learn a **non-obvious fact** about the codebase, system, or domain
- A **pattern** emerges that applies beyond the current task
- You finish a **session** with work in progress that must resume later

Do NOT store:
- Information already in code or git history
- Temporary scaffolding or intermediate results
- Duplicates of existing memories (search first)

---

## Search Before Storing

Always check for existing memories before creating a new one:

```bash
pkm search "topic keywords" --top 5
```

If a result scores above 0.85 and covers the same ground, update your understanding from it rather than creating a duplicate. Only store if the new memory adds genuinely new information.

---

## Memory Types

### `episodic` — In-progress events, session state
Use for: what happened today, current task status, work in flight.

```bash
pkm note add --content "Refactoring auth module — stopped at middleware layer, resume from jwt_decode()" \
  --type episodic --importance 6 --session abc123
```

### `semantic` — Knowledge and facts
Use for: architectural decisions, API contracts, domain rules, learned patterns.

```bash
pkm note add --content "SQLite WAL mode required for concurrent reads in this project — switching to journal mode caused test flakiness" \
  --type semantic --importance 8
```

### `procedural` — Workflows and how-tos
Use for: repeatable processes, setup steps, debugging runbooks.

```bash
pkm note add --content "To run integration tests: spin up docker-compose first, then uv run pytest tests/integration/" \
  --type procedural --importance 6
```

---

## Importance Scoring

| Score | Meaning | Examples |
|-------|---------|---------|
| 1–3 | Trivial / transient | Formatting preference, minor observation |
| 4–6 | Moderate | Task progress note, useful but forgettable fact |
| 7–8 | Important | Architecture decision, non-obvious constraint, fixed bug root cause |
| 9–10 | Critical | Security constraint, irreversible decision, hard-won lesson |

Default is 5. Bias toward 7+ for anything you'd need to explain to the next agent.

---

## Session Management

Use a stable `--session` ID within a work session (e.g., a task ID, branch name, or UUID):

```bash
pkm note add --content "content" --type episodic --importance 5 --session feat/auth-rewrite
```

Retrieve all memories from a session:

```bash
pkm search --session feat/auth-rewrite
```

---

## Daily Note Updates

At session end, update today's daily note with key accomplishments and unresolved issues:

```bash
pkm daily add "Completed auth middleware refactor. Still need to wire up refresh token endpoint."
```

This creates a human-readable timeline that complements the machine-searchable memory notes.

---

## Consolidation

After accumulating daily notes, consolidate them into long-term semantic memories:

```bash
pkm consolidate          # list candidates
pkm consolidate --run    # process and mark consolidated
```

Consolidation distills episodic logs into durable semantic memories and marks source notes as `consolidated: true` to exclude them from future candidates.

---

## Hook Setup

Install session-start guidance so agents retrieve PKM context on demand. PKM no
longer injects notes or daily context on every user prompt by default.

### Claude Code (`~/.claude/settings.json`)

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "pkm hook run session-start --format system-reminder"
          }
        ]
      }
    ]
  }
}
```

Or use the built-in setup command:

```bash
pkm hook setup --tool claude-code
```

### Codex

```bash
pkm hook setup --tool codex
```

### opencode

Install the PKM plugin; opencode reads `plugin/hooks/hooks.json` through the
plugin bridge.

---

## Quick Reference

```bash
# Store memories
pkm note add --content "content" --type semantic --importance 7
pkm note add --content "content" --type episodic --importance 5 --session my-session

# Search
pkm search "topic" --top 5
pkm search "topic" --type semantic

# Session recall
pkm search --session my-session

# Daily notes
pkm daily                    # view today
pkm daily add "note"         # append entry

# Consolidation
pkm consolidate              # list candidates
pkm consolidate --run        # process

# Hook guidance
pkm hook run session-start --format system-reminder
```

---

## CLAUDE.md Snippet

Add this section to your project `CLAUDE.md` to enable memory for Claude Code agents:

```markdown
## Memory Layer (PKM)

Before starting work, load session context:
  pkm hook run session-start --format system-reminder

Store important findings during work:
  pkm note add --content "content" --type semantic --importance 7        # knowledge/decisions
  pkm note add --content "content" --type episodic --importance 5 \     # in-progress state
    --session $SESSION_ID

Search before storing (avoid duplicates):
  pkm search "topic" --top 5

At session end, update the daily note:
  pkm daily add "What was accomplished and what remains."

Importance guide: 1-3 trivial, 4-6 moderate, 7-8 important, 9-10 critical.
```

---

## AGENTS.md Snippet

Add this section to your project `AGENTS.md` to enforce memory protocol for all agents:

```markdown
## Memory Protocol

All agents must follow this protocol for persistent memory:

1. **Session start**: run `pkm hook run session-start --format system-reminder`
   and follow its retrieval guidance.

2. **Search before non-trivial work or storing**: run `pkm search "topic" --top 5`
   to recall prior notes and avoid duplicates. If an important result appears,
   inspect graph neighbors before proceeding.

3. **Read daily logs when continuity matters**: use `pkm daily --offset 1` or
   `pkm daily --date YYYY-MM-DD` when continuing prior work or when the user
   references a previous session.

4. **Store decisions and errors** as `semantic` memories (importance 7+):
   `pkm note add --content "..." --type semantic --importance 8`

5. **Store in-progress state** as `episodic` memories with a session ID:
   `pkm note add --content "..." --type episodic --importance 5 --session SESSION`

6. **Session end**: append key accomplishments and unresolved issues to the daily note:
   `pkm daily add "Completed X. Still pending: Y."`

Memory types: episodic (daily events), semantic (facts/decisions), procedural (workflows).
Importance scale: 1-3 trivial · 4-6 moderate · 7-8 important · 9-10 critical.
```
