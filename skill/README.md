# PKM Skill — Workflows Index

PKM workflow list. Find the workflow matching the user's request, read that document, and execute it.

## Memory Layer Workflows (For LLM Agents)

| Workflow | Primary Trigger | Document | Description |
|----------|----------------|------|------|
| Memory Store | memory store | [workflows/memory-store.md](workflows/memory-store.md) | Store agent discoveries/decisions as atomic notes |
| Memory Search | memory search | [workflows/memory-search.md](workflows/memory-search.md) | Semantic + time-weighted memory search |
| Memory Session | memory session | [workflows/memory-session.md](workflows/memory-session.md) | Session-scoped memory tracking and retrieval |
| Consolidate | consolidate | [workflows/consolidate.md](workflows/consolidate.md) | Identify and mark daily consolidation candidates |
| Dream | dream | [workflows/dream.md](workflows/dream.md) | Extract atomic notes from consolidated dailies |

## Knowledge Management Workflows (User Interactive)

| Workflow | Primary Trigger | Document | Description |
|----------|----------------|------|------|
| Weekly Review | weekly review | [workflows/weekly-review.md](workflows/weekly-review.md) | Weekly knowledge organization and linking |
| 1:1 Prep | 1:1 prep | [workflows/1on1-prep.md](workflows/1on1-prep.md) | 1:1 meeting preparation |
| Health Check | health check | [workflows/health-check.md](workflows/health-check.md) | Vault health inspection |
| Connect | find connections | [workflows/connect.md](workflows/connect.md) | Connect orphan notes |
| Task Sync | task sync | [workflows/task-sync.md](workflows/task-sync.md) | Task synchronization |
| Working Memory | working memory | [workflows/working-memory.md](workflows/working-memory.md) | Current task context management |
| Capture Triage | untagged cleanup | [workflows/capture-triage.md](workflows/capture-triage.md) | Triage unclassified items |
| Daily Seed | start today | [workflows/daily-seed.md](workflows/daily-seed.md) | Daily start routine |
| Monthly Synthesis | monthly synthesis | [workflows/monthly-synthesis.md](workflows/monthly-synthesis.md) | Monthly knowledge synthesis |

## Memory Layer Architecture

```
[agent discovery] → pkm note add --content → memory/YYYY-MM-DD-<slug>.md
                                              ↓
[session start]    ← pkm search ← semantic + time-weighted search
                                              ↓
[daily consolidation] → pkm consolidate mark → consolidated: true
                                              ↓
[knowledge promotion] → dream workflow → notes/<atomic-note>.md
```

## Integration Snippets

- [CLAUDE.md integration example](references/sample-claude-md.md)
- [AGENTS.md integration example](references/sample-agents-md.md)
