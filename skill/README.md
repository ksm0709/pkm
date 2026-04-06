# PKM Skill — Workflows Index

PKM workflow list. Find the workflow matching the user's request, read that document, and execute it.

## ★ Core Orchestration Loops

These are the two primary entry points for all knowledge work. Run these regularly.

| Workflow | Trigger | Document | Description |
|----------|---------|----------|-------------|
| **★ Zettel Loop** | `zettel-loop`, knowledge production | [workflows/zettel-loop.md](workflows/zettel-loop.md) | **Production loop** — distill consolidated dailies → connect → tag → build structure notes |
| **★ Refine Loop** | `refine-loop`, knowledge cleanup | [workflows/refine-loop.md](workflows/refine-loop.md) | **Cleanup loop** — auto-linking → auto-tagging → health-check → prune/merge/split |

## Supporting Workflows

Sub-steps called by the core loops, or run standalone when targeted work is needed.

| Workflow | Trigger | Document | Description |
|----------|---------|----------|-------------|
| Consolidate | consolidate | [workflows/consolidate.md](workflows/consolidate.md) | Mark daily notes `consolidated: true` — prerequisite for zettel-loop |
| Distill Daily | distill-daily | [workflows/distill-daily.md](workflows/distill-daily.md) | Promote marked dailies to permanent knowledge notes |
| Auto Linking | find connections | [workflows/auto-linking.md](workflows/auto-linking.md) | Discover unconnected note pairs and add wikilinks |
| Auto Tagging | untagged cleanup | [workflows/auto-tagging.md](workflows/auto-tagging.md) | Find untagged notes and classify them |
| Health Check | health check | [workflows/health-check.md](workflows/health-check.md) | Measure orphan ratio, stale notes, untagged count |
| Prune-Merge-Split | prune-merge-split | [workflows/prune-merge-split.md](workflows/prune-merge-split.md) | Remove empty notes, merge duplicates, split mixed-topic notes |
| Backlink Traverse | backlink traverse | [workflows/backlink-traverse.md](workflows/backlink-traverse.md) | Explore connections via backlinks, find isolated notes |
| Tag Explore | tag explore | [workflows/tag-explore.md](workflows/tag-explore.md) | Browse knowledge by topic using tag index notes |

## Periodic Review Workflows

| Workflow | Trigger | Document | Description |
|----------|---------|----------|-------------|
| Init Daily | start today | [workflows/init-daily.md](workflows/init-daily.md) | Create today's daily note with carry-over TODOs |
| Add Context | working memory | [workflows/add-context-to-daily.md](workflows/add-context-to-daily.md) | Preserve in-progress project context in daily note |
| Task Sync | task sync | [workflows/task-sync.md](workflows/task-sync.md) | Sync TODOs from daily notes to tasks/ongoing.md |
| Weekly Review | weekly review | [workflows/weekly-review.md](workflows/weekly-review.md) | Summarize week into stats, anomalies, and action items |
| Monthly Synthesis | monthly synthesis | [workflows/monthly-synthesis.md](workflows/monthly-synthesis.md) | Synthesize last month's notes into key themes |
| 1:1 Prep | 1:1 prep | [workflows/1on1-prep.md](workflows/1on1-prep.md) | Collect notes about a person and draft a meeting agenda |
| Add Workflow | add-workflow | [workflows/add-workflow.md](workflows/add-workflow.md) | Create a new PKM workflow via Socratic interview |

## Memory Layer Workflows (For LLM Agents)

| Workflow | Trigger | Document | Description |
|----------|---------|----------|-------------|
| Memory Store | memory store | [workflows/memory-store.md](workflows/memory-store.md) | Store agent findings as atomic notes for long-term recall |
| Memory Search | memory search | [workflows/memory-search.md](workflows/memory-search.md) | Retrieve past memories via semantic + time-weighted search |
| Memory Session | memory session | [workflows/memory-session.md](workflows/memory-session.md) | Track and retrieve memories linked to an agent session |

## Memory Layer Architecture

```
[agent discovery] → pkm note add --content → memory/YYYY-MM-DD-<slug>.md
                                              ↓
[session start]    ← pkm search ← semantic + time-weighted search
                                              ↓
[daily consolidation] → pkm consolidate mark → consolidated: true
                                              ↓
[knowledge promotion] → zettel-loop workflow → notes/<atomic-note>.md
```

## Integration Snippets

- [CLAUDE.md integration example](references/sample-claude-md.md)
- [AGENTS.md integration example](references/sample-agents-md.md)
