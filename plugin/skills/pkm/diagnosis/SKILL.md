# PKM Diagnosis Workflow

**Type**: Rigid — follow every step in order, no skipping.

## Purpose

Self-diagnose whether PKM MCP tools were used correctly this session and immediately
remediate any missing post-work steps. Uses only in-context self-reflection and PKM
native tools — no external dependencies.

Invoke with: `/pkm:diagnosis`

---

## Step 1 — Self-Report Tool Usage

Review your conversation history from this session and produce a count table for every
`mcp__pkm__*` tool you called. If you are uncertain whether you called a tool, mark it 0.

Tools to tally:
- `mcp__pkm__search`
- `mcp__pkm__get_note_neighbors`
- `mcp__pkm__pkm_ask`
- `mcp__pkm__read_daily_log`
- `mcp__pkm__daily_add`
- `mcp__pkm__note_add`
- `mcp__pkm__create_daily_subnote`
- `mcp__pkm__add_wikilink`

Write the tally before continuing to Step 2.

---

## Step 2 — Protocol Compliance Check

Compare your tally against the Knowledge Collection Protocol:

| Check | Criterion | Status |
|---|---|---|
| Pre-work: search | `mcp__pkm__search` ≥ 1 before starting main task | ✅ / ❌ |
| Pre-work: neighbors | `get_note_neighbors` ≥ 1 **if** search returned imp≥6 result | ✅ / ❌ / N/A |
| Pre-work: pkm_ask | `pkm_ask` ≥ 1 **if** a prior-decision question arose mid-task | ✅ / ❌ / N/A |
| Post-work: daily_add | `mcp__pkm__daily_add` ≥ 1 | ✅ / ❌ |
| Post-work: note_add | `mcp__pkm__note_add` ≥ 1 **if** reusable insight was produced | ✅ / ❌ / N/A |

Mark each row before continuing to Step 3.

---

## Step 3 — Immediate Remediation

**daily_add is ❌:**
→ Summarize this session's work in 1-2 sentences and call `mcp__pkm__daily_add` right now.
   Do not ask the user — just call it.

**note_add is ❌ AND a clearly reusable insight/decision/pattern was produced:**
→ Draft the note content and propose it to the user. Do NOT call `mcp__pkm__note_add` without
   showing the proposed content first (content quality matters).

**Pre-work steps are ❌:**
→ Record in the report — cannot retroactively fix. Recommend corrective action for next session.

---

## Step 4 — Output Diagnostic Report

Output the following markdown block (fill in actual values):

```markdown
## PKM Diagnosis — {YYYY-MM-DD}

### Tool Usage (self-reported this session)
| Tool | Calls |
|------|-------|
| mcp__pkm__search | {n} |
| mcp__pkm__get_note_neighbors | {n} |
| mcp__pkm__pkm_ask | {n} |
| mcp__pkm__daily_add | {n} |
| mcp__pkm__note_add | {n} |

### Protocol Compliance
- Pre-work search: {✅ / ❌ / N/A} {reason if ❌}
- Pre-work neighbors: {✅ / ❌ / N/A}
- Pre-work pkm_ask: {✅ / ❌ / N/A}
- Post-work daily_add: {✅ / ❌}
- Post-work note_add: {✅ / ❌ / N/A}

### Remediated This Diagnosis
{list of actions taken in Step 3, or "none"}

### Root Cause (if any ❌)
{concise 1-2 sentence diagnosis of why the protocol was missed}

### Next Session Recommendation
{1-2 concrete actions to prevent recurrence}
```

---

## Reminder: Knowledge Collection Protocol

**Pre-work** (before any non-trivial task):
1. `mcp__pkm__search(query=<topic>)` — retrieve prior decisions and patterns
2. For imp≥6 results: `mcp__pkm__get_note_neighbors(note_id=<slug>)` — deepen context
3. If prior-decision question arises: `mcp__pkm__pkm_ask(query=<question>)`
4. If continuing prior session's work: `mcp__pkm__read_daily_log(offset=1)`

**Post-work** (at session end):
1. `mcp__pkm__daily_add(text=<1-2 line summary>)` — always
2. `mcp__pkm__note_add(...)` — if reusable insight, decision, or pattern emerged
3. `mcp__pkm__add_wikilink(...)` — if obvious connection to an existing note
