# Agent Memory Policy

Reference guide for LLM agents using PKM as their persistent memory layer.

---

## Overview

PKM has two memory layers:

- `daily/` stores time-bound memory: session state, progress logs, event notes,
  transient observations, temporary TODO context, and structured daily subnotes.
- `notes/` stores durable knowledge: concepts, entities, processes, principles,
  patterns, decisions, and index notes that should remain useful without today's
  date or the current task.

Agents should capture freely into daily notes, then promote selectively into
atomic notes only when the information has durable knowledge shape.

---

## When to Store Durable Knowledge

Create or update a `notes/` entry when:
- You make a **decision** that affects future work (architecture choice, API contract, design tradeoff)
- You **discover an error or bug** and how it was fixed
- You learn a **non-obvious fact** about the codebase, system, or domain
- A **pattern** emerges that applies beyond the current task
- You define a reusable **process**, **principle**, **concept**, or **index**

Write to `daily/` or a daily subnote instead when:
- You finish a **session** with work in progress that must resume later
- The content is a current status, event log, investigation trace, or temporary TODO
- The value depends on today's date, this branch, this meeting, or this one task

Do NOT create a durable note for:
- Information already in code or git history
- Temporary scaffolding or intermediate results
- Duplicates of existing memories (search first)

---

## Promotion Gate

Before creating a note under `notes/`, verify:

1. It can be named as a concept, entity, process, principle, pattern, decision, or index.
2. It has a stable definition or rule, not just a status update.
3. It will still be useful after today's date and current task are forgotten.
4. It can link to at least one existing note, source daily/subnote, or hub.
5. It adds knowledge not already covered by an existing note.

If the gate fails, use `pkm daily add` or `pkm daily subnote`.

---

## Search Before Storing

Always check for existing memories before creating a new one:

```bash
pkm search "topic keywords" --top 5
```

If a result scores above 0.85 and covers the same ground, update your understanding from it rather than creating a duplicate. Only store if the new memory adds genuinely new information.

---

## Durable Note Shape

Durable notes should make one-search retrieval useful:

```markdown
---
id: <note-id>
type: concept | entity | process | principle | pattern | decision | index
aliases: []
tags: []
description: "one-line answer to what this note is"
---

## Definition
One short paragraph defining the knowledge unit.

## Use When
- Situations where this note should be retrieved or applied.

## Relations
&is_a [[...]] - why this classification matters
&part_of [[...]] - why this belongs to the target
&depends_on [[...]] - what requirement the target satisfies
&enables [[...]] - what the source makes possible
&contrasts_with [[...]] - the meaningful difference
&related [[...]] - why this connection matters

## Evidence / Examples
- Daily source, code reference, observed case, or concrete example.
```

Minimum viable durable note: `type`, `description`, `Definition`, and at least
one `&relation [[target]] - reason` marker or source link.

Relation markers in `notes/` become graph metadata after `pkm index`. Relation
markers in `daily/` are promotion candidates only; use them to capture possible
structure without making the daily note canonical knowledge.

---

## Memory Types

### `episodic` — Compatibility only

Older vaults may contain `memory_type: episodic` notes. Keep them readable, but
new agents should not create ordinary session-state notes under `notes/`. Use
`pkm daily add` for short state and `pkm daily subnote` for structured state.

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

Use daily notes for normal session state:

```bash
pkm daily add "Refactoring auth module — stopped at middleware layer, resume from jwt_decode()."
```

Use a daily subnote when the session record needs structure:

```bash
pkm daily subnote "auth-refactor-investigation" --content "# Auth refactor investigation"
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

Consolidation distills daily logs into durable semantic memories and marks source notes as `consolidated: true` to exclude them from future candidates.

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
pkm daily add "short time-bound session state"
pkm daily subnote "investigation" --content "# Structured time-bound record"

# Search
pkm search "topic" --top 5
pkm search "topic" --type semantic
pkm relations
pkm relations audit

# Session recall
pkm daily --offset 1
pkm daily --date YYYY-MM-DD

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
  pkm daily add "content"                                                # in-progress state
  pkm daily subnote "investigation" --content "# Notes"                  # structured state

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

5. **Store in-progress state** in daily notes:
   `pkm daily add "Stopped at X. Resume from Y."`
   Use `pkm daily subnote "investigation" --content "# Notes"` for structured state.

6. **Session end**: append key accomplishments and unresolved issues to the daily note:
   `pkm daily add "Completed X. Still pending: Y."`

Memory types: semantic (facts/decisions), procedural (workflows). Existing
episodic notes are compatibility data; do not create new ordinary session-state
notes under `notes/`.
Importance scale: 1-3 trivial · 4-6 moderate · 7-8 important · 9-10 critical.
```
