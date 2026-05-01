# PKM-Claude Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align MCP tool descriptions, hook injection text, and PKM Skill so Claude Code proactively uses PKM for knowledge collection before, during, and after work.

**Architecture:** Three-layer text-only changes: (1) MCP tool docstrings gain trigger conditions, anti-cases, and workflow position; (2) hook text shifts from vague imperatives to factual project reality with step-by-step protocols; (3) PKM Skill gains a three-phase Knowledge Collection Protocol.

**Tech Stack:** Python docstrings (mcp_server.py), Click hook handlers (hook.py), Markdown (SKILL.md)

---

## File Map

| File | Change |
|---|---|
| `cli/src/pkm/mcp_server.py` | Docstrings for 12 tools: search, pkm_ask, get_note_neighbors, note_add, daily_add, create_daily_subnote, add_wikilink, list_orphans, find_surprising_connections, mark_consolidated, list_clusters, list_god_nodes |
| `cli/src/pkm/commands/hook.py` | `_handle_turn_start` footer (lines 497–506), `_handle_turn_end_exit2` instructions (lines 565–567) |
| `plugin/skills/pkm/SKILL.md` | New `## Knowledge Collection Protocol` section after line 104 |

---

## Task 1: Update Search Cluster Tool Descriptions

**Files:**
- Modify: `cli/src/pkm/mcp_server.py:165-173` (search)
- Modify: `cli/src/pkm/mcp_server.py:245-252` (pkm_ask)
- Modify: `cli/src/pkm/mcp_server.py:409-417` (get_note_neighbors)

- [ ] **Step 1: Replace `search` docstring**

In `cli/src/pkm/mcp_server.py`, replace lines 165–173:
```python
    """Search notes semantically via the PKM daemon.

    Args:
        query: Search query string.
        top: Maximum number of results (default 10).
        vault: Vault name for cross-vault search. Uses server vault if omitted.
        memory_type: Filter by type — semantic, episodic, or procedural.
        min_importance: Minimum importance score filter (default 1.0).
    """
```
with:
```python
    """Search vault notes by topic or concept (semantic similarity).

    Use BEFORE starting any non-trivial task to recall prior knowledge, decisions,
    and patterns. Also use before note_add() to check for duplicates.
    Do NOT use when you already know the exact note slug — use get_note_neighbors() instead.
    Typically followed by get_note_neighbors() on relevant results.

    Args:
        query: Free-text concept or topic to search for.
        top: Maximum number of results (default 10, max 50).
        vault: Vault name for cross-vault search. Uses server vault if omitted.
        memory_type: Filter by type — semantic, episodic, or procedural.
        min_importance: Minimum importance score filter (default 1.0). Use 5.0 to focus on non-trivial notes.
    """
```

- [ ] **Step 2: Replace `pkm_ask` docstring**

In `cli/src/pkm/mcp_server.py`, replace lines 245–252:
```python
    """Ask a natural language question about your vault.

    Args:
        query: The natural language question to ask.
        vault: Vault name for cross-vault search. Uses server vault if omitted.
        model: Optional LLM model to use. Overrides config if provided.
        timeout: Timeout in seconds to wait for the result.
    """
```
with:
```python
    """Ask a natural language question and get a synthesized answer from vault notes (RAG).

    Use when you need an answer synthesized across multiple notes — prior decisions,
    user preferences, patterns. Slower than search() but returns a direct answer.
    Safe to run as a background task while other work continues.
    Do NOT use as a substitute for search() — use search() for exploration, pkm_ask() for questions.

    Args:
        query: The natural language question to ask.
        vault: Vault name for cross-vault search. Uses server vault if omitted.
        model: Optional LLM model to use. Overrides config if provided.
        timeout: Timeout in seconds to wait for the result (default 120).
    """
```

- [ ] **Step 3: Replace `get_note_neighbors` docstring**

In `cli/src/pkm/mcp_server.py`, replace lines 409–417:
```python
    """Get all neighbors of a note: outbound wikilinks, inbound backlinks, tags, ghost
    nodes, and optionally semantic connections. Daemon-free (reads graph.json directly).

    Returns {note_id, outbound:[{note_id,title,type}], inbound:[{note_id,title,type}],
    semantic:[{note_id,title,type,confidence}]}. All node types included (note, tag,
    note_or_unresolved). Filter by 'type' field as needed.
    Requires pkm index to have been run to build graph.json.
    """
```
with:
```python
    """Explore the connection graph around a specific note.

    Use after search() when a result looks relevant — traverse its outbound links,
    inbound backlinks, and optionally semantic connections for deeper context.
    This is the second step in tree-traversal knowledge collection:
    search() → get_note_neighbors() → get_note_neighbors() (one more level if needed, max 2-depth).
    Do NOT use include_semantic=True unless embedding-based connections are specifically needed; it is slower.

    Returns {note_id, outbound:[{note_id,title,type}], inbound:[{note_id,title,type}],
    semantic:[{note_id,title,type,confidence}]}. Requires pkm index to have been run.

    Args:
        note_id: Note slug without extension (e.g. "2026-04-05-my-note").
        include_semantic: Include embedding-based semantic connections (default False).
    """
```

- [ ] **Step 4: Run existing tests to verify no regressions**

```bash
cd /home/taeho/repos/pkm && uv run pytest tests/ -x -q 2>&1 | tail -5
```
Expected: all tests pass (currently 396).

- [ ] **Step 5: Commit**

```bash
git add cli/src/pkm/mcp_server.py
git commit -m "feat(mcp): add trigger conditions and workflow position to search cluster tools"
```

---

## Task 2: Update Note Writing Cluster Tool Descriptions

**Files:**
- Modify: `cli/src/pkm/mcp_server.py:46-57` (note_add)
- Modify: `cli/src/pkm/mcp_server.py:82-86` (daily_add)
- Modify: `cli/src/pkm/mcp_server.py:106-116` (create_daily_subnote)

- [ ] **Step 1: Replace `note_add` docstring**

In `cli/src/pkm/mcp_server.py`, replace lines 46–57:
```python
    """Create an atomic note in the PKM vault.

    Args:
        content: Note body text (required).
        title: Note title. Auto-generated from content if omitted.
        type: Memory type — semantic, episodic, or procedural.
        importance: Importance score 1-10 (default 5).
        tags: List of tags.
        meta: Arbitrary key-value metadata added to frontmatter.
        session_id: Session tracking ID.
        agent_id: Agent tracking ID.
    """
```
with:
```python
    """Create a permanent atomic note for reusable knowledge.

    Use for knowledge that will be referenced again: architectural decisions, bug root causes,
    API behaviors, patterns, user preferences. Always search() first to avoid duplicates —
    update an existing note if the topic already exists.
    Do NOT use for ephemeral session logs — use daily_add() instead.

    importance: 1-3 trivial · 4-6 moderate · 7-8 important (arch decisions, bug root causes)
    · 9-10 critical (security, irreversible). Default 5 if unsure. Bias 7+ for anything the
    next agent would need.

    Args:
        content: Note body text (required).
        title: Note title. Auto-generated from content if omitted.
        type: Memory type — semantic (concepts/facts), episodic (events), procedural (how-to).
        importance: Importance score 1-10 (default 5).
        tags: List of tags.
        meta: Arbitrary key-value metadata added to frontmatter.
        session_id: Session tracking ID.
        agent_id: Agent tracking ID.
    """
```

- [ ] **Step 2: Replace `daily_add` docstring**

In `cli/src/pkm/mcp_server.py`, replace lines 82–86:
```python
    """Append a timestamped log entry to today's daily note.

    Args:
        text: The text to add to today's daily note.
    """
```
with:
```python
    """Append a timestamped log entry to today's daily note (ephemeral session log).

    Use for work summaries, observations, and progress notes that don't need independent
    future reference. This is the lightest PKM write and should be called at the END of
    every session. Do NOT use for reusable knowledge — use note_add() instead.

    Args:
        text: The text to log. Keep to 1-3 sentences summarizing what was done.
    """
```

- [ ] **Step 3: Replace `create_daily_subnote` docstring**

In `cli/src/pkm/mcp_server.py`, replace lines 106–116:
```python
    """Create a dated subnote and link it from today's daily note.

    Creates YYYY-MM-DD-{title}.md in the vault daily directory and appends
    a timestamped [[wikilink]] entry to today's daily note.

    Args:
        title: Subnote title slug (spaces become hyphens).
        content: Markdown body content for the new subnote.
        tags: Optional list of tags for the subnote frontmatter.
        aliases: Optional list of aliases for the subnote frontmatter.
    """
```
with:
```python
    """Create a dated subnote linked from today's daily note (medium-weight session record).

    Use for session-scoped records larger than a daily_add() entry but not warranting
    a standalone atomic note — meeting notes, investigation logs, design explorations.
    Creates YYYY-MM-DD-{title}.md in the vault daily directory and appends a timestamped
    [[wikilink]] entry to today's daily note.
    For permanent reusable knowledge, use note_add() instead.

    Args:
        title: Subnote title slug (spaces become hyphens).
        content: Markdown body content for the new subnote.
        tags: Optional list of tags for the subnote frontmatter.
        aliases: Optional list of aliases for the subnote frontmatter.
    """
```

- [ ] **Step 4: Run tests**

```bash
cd /home/taeho/repos/pkm && uv run pytest tests/ -x -q 2>&1 | tail -5
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add cli/src/pkm/mcp_server.py
git commit -m "feat(mcp): clarify note writing tool distinctions (note_add vs daily_add vs subnote)"
```

---

## Task 3: Update Maintenance/Graph Tool Descriptions

**Files:**
- Modify: `cli/src/pkm/mcp_server.py:617-622` (add_wikilink)
- Modify: `cli/src/pkm/mcp_server.py:365-366` (list_orphans)
- Modify: `cli/src/pkm/mcp_server.py:549-554` (find_surprising_connections)
- Modify: `cli/src/pkm/mcp_server.py:488-492` (mark_consolidated)

- [ ] **Step 1: Replace `add_wikilink` docstring**

In `cli/src/pkm/mcp_server.py`, replace lines 618–622:
```python
    """Append a [[target|description]] entry to the '## Related' section of source note.

    description MUST explain WHY the connection is meaningful — the conceptual bridge,
    not a description of the target note. Use after find_surprising_connections().
    """
```
with:
```python
    """Append a [[target|description]] entry to the '## Related' section of source note.

    Use after note_add() when the new note has an obvious meaningful connection to an existing note.
    description MUST explain WHY the connection is meaningful — the conceptual bridge,
    not a description of the target. Example: "shares vault-scoped path resolution pattern"
    not "another note about vault paths". The daemon discovers non-obvious links periodically;
    manual use here is for connections you already know about.

    Args:
        source_note_id: Note slug to add the link to (without .md extension).
        target_note_id: Note slug to link to (without .md extension).
        description: WHY this connection is meaningful (required).
    """
```

- [ ] **Step 2: Replace `list_orphans` docstring**

In `cli/src/pkm/mcp_server.py`, replace line 366:
```python
    """List all orphan notes — notes with zero inbound AND zero outbound wikilinks."""
```
with:
```python
    """List all orphan notes — notes with zero inbound AND zero outbound wikilinks.

    Use during vault maintenance to find disconnected knowledge that has become dead.
    Orphan notes are candidates for deletion, consolidation, or connecting via add_wikilink().
    Not needed in normal task workflows.
    """
```

- [ ] **Step 3: Replace `find_surprising_connections` docstring**

In `cli/src/pkm/mcp_server.py`, replace lines 550–554:
```python
    """Find notes that semantically bridge two different topic clusters (hidden cross-cluster links).

    Use when you want to discover non-obvious connections between different vault topic areas.
    Requires pkm index to have been run to build the enriched graph.
    """
```
with:
```python
    """Find notes that semantically bridge two different topic clusters (hidden cross-cluster links).

    Use for on-demand cross-domain connection discovery. The daemon runs this periodically
    in the background — call manually only when you suspect an important connection exists
    or want an immediate scan. Results can then be linked with add_wikilink().
    Requires pkm index to have been run to build the enriched graph.
    """
```

- [ ] **Step 4: Replace `mark_consolidated` docstring**

In `cli/src/pkm/mcp_server.py`, replace line 492:
```python
    """Mark a daily note as consolidated. Requires distilled_note_ids for auditability."""
```
with:
```python
    """Mark a daily note as consolidated after Zettelkasten distillation.

    Call AFTER creating atomic notes from a daily note's content (note_add()), providing
    the IDs of the notes created. Part of the zettel-loop workflow:
    list_consolidation_candidates() → distill → note_add() → mark_consolidated().
    Requires distilled_note_ids for auditability — cannot mark without them.

    Args:
        date_str: Date of the daily note to mark (format: YYYY-MM-DD).
        distilled_note_ids: IDs of atomic notes created during distillation (required).
    """
```

- [ ] **Step 5: Run tests**

```bash
cd /home/taeho/repos/pkm && uv run pytest tests/ -x -q 2>&1 | tail -5
```
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add cli/src/pkm/mcp_server.py
git commit -m "feat(mcp): add trigger conditions to maintenance and graph tools"
```

---

## Task 4: Rewrite UserPromptSubmit Hook Footer

**Files:**
- Modify: `cli/src/pkm/commands/hook.py:497-506`

- [ ] **Step 1: Replace footer in `_handle_turn_start`**

In `cli/src/pkm/commands/hook.py`, replace lines 497–506:
```python
    if _detect_pkm_mcp():
        lines.append(
            "`mcp__pkm__search` — recall related notes if needed"
            "\nFor full command reference see the `/pkm` skill or session-start context."
        )
    else:
        lines.append(
            '`pkm search "<query>"` — recall related notes if needed'
            "\nFor full command reference see the `/pkm` skill or session-start context."
        )
```
with:
```python
    if _detect_pkm_mcp():
        lines.append(
            "# PKM Context\n"
            "Relevant notes above are exploration starting points.\n"
            "→ mcp__pkm__get_note_neighbors(note_id=<slug>) — explore connections (2-depth max)\n"
            "→ mcp__pkm__pkm_ask(query=<question>) — synthesized answers from vault\n"
            "Before starting non-trivial work: mcp__pkm__search(query=<topic>)"
        )
    else:
        lines.append(
            "# PKM Context\n"
            "Relevant notes above are exploration starting points.\n"
            'pkm search "<topic>" — recall prior knowledge before starting work'
        )
```

- [ ] **Step 2: Run tests**

```bash
cd /home/taeho/repos/pkm && uv run pytest tests/ -x -q 2>&1 | tail -5
```
Expected: all tests pass.

- [ ] **Step 3: Manually verify hook output**

```bash
echo '{"message": "help me refactor the MCP server"}' | pkm hook run turn-start
```
Expected output includes `# PKM Context` section with the three `→` lines.

- [ ] **Step 4: Commit**

```bash
git add cli/src/pkm/commands/hook.py
git commit -m "feat(hook): reframe relevant notes as exploration starting points in turn-start footer"
```

---

## Task 5: Rewrite Stop Hook Protocol

**Files:**
- Modify: `cli/src/pkm/commands/hook.py:565-567`

- [ ] **Step 1: Replace `instructions` string in `_handle_turn_end_exit2`**

In `cli/src/pkm/commands/hook.py`, replace lines 565–567:
```python
    instructions = """\
KNOWLEDGE EXTRACTION: Save key learnings from this session using pkm commands.
Be selective — skip trivial facts. See /pkm skill for available commands. Then you may stop."""
```
with:
```python
    instructions = """\
# Knowledge Extraction — complete these steps, then stop:
1. mcp__pkm__daily_add(text="<1-2 line summary of what was done>")  ← always
2. Reusable insight, decision, or pattern found?
   → mcp__pkm__search(query=<topic>) first (check duplicates)
   → mcp__pkm__note_add(content=..., importance=7+) if no duplicate exists
   Skip step 2 if nothing non-obvious or reusable was learned.
3. Obvious connection to an existing note?
   → mcp__pkm__add_wikilink(source_note_id=..., target_note_id=..., description="WHY this connects")
   Skip step 3 if no clear connection exists.
Then stop."""
```

- [ ] **Step 2: Run tests**

```bash
cd /home/taeho/repos/pkm && uv run pytest tests/ -x -q 2>&1 | tail -5
```
Expected: all tests pass.

- [ ] **Step 3: Manually verify hook output**

```bash
echo '{}' | pkm hook run turn-end-exit2; echo "exit: $?"
```
Expected: prints the new `# Knowledge Extraction` block to stdout, exits 0.

- [ ] **Step 4: Commit**

```bash
git add cli/src/pkm/commands/hook.py
git commit -m "feat(hook): replace vague stop hook message with step-by-step knowledge extraction protocol"
```

---

## Task 6: Add Knowledge Collection Protocol to PKM Skill

**Files:**
- Modify: `plugin/skills/pkm/SKILL.md` — insert new section after line 104 (after the MCP interface example block)

- [ ] **Step 1: Insert `## Knowledge Collection Protocol` section**

In `plugin/skills/pkm/SKILL.md`, after line 104 (the line ending with `Default 5 if unsure.`), insert:

```markdown

## Knowledge Collection Protocol

Three-phase protocol for using PKM as an active knowledge partner throughout work.

### A. Pre-work: Context Recall (before starting any non-trivial task)

1. `mcp__pkm__search(query=<task topic>, min_importance=5.0)` — find prior knowledge, decisions, patterns
2. For any result with imp≥6 or obviously relevant title:
   `mcp__pkm__get_note_neighbors(note_id=<slug>)` — explore connections
   Repeat once more if a neighbor is also clearly relevant (max 2-depth total).
3. If a specific question arises about prior decisions or user preferences:
   `mcp__pkm__pkm_ask(query=<question>)` — synthesized answer from vault

Stop when: no relevant results found, or sufficient context collected.

### B. During Work: Background Queries

When a question arises mid-task about prior decisions, patterns, or the user's preferences:
`mcp__pkm__pkm_ask(query=<question>)` — safe to run as a background agent task; continue work while waiting.

### C. Post-work: Knowledge Capture

1. **Always:** `mcp__pkm__daily_add(text="<1-2 line summary of what was done>")`
2. **If reusable:** `mcp__pkm__search(query=<topic>)` first (check duplicates), then `mcp__pkm__note_add(content=..., importance=7+)` for decisions or patterns the next agent would need
3. **If obvious connection:** `mcp__pkm__add_wikilink(source_note_id=..., target_note_id=..., description="WHY — the conceptual bridge")`
```

- [ ] **Step 2: Verify skill file renders correctly**

```bash
head -120 /home/taeho/repos/pkm/plugin/skills/pkm/SKILL.md | tail -30
```
Expected: the new `## Knowledge Collection Protocol` section appears cleanly after the MCP interface section.

- [ ] **Step 3: Commit**

```bash
git add plugin/skills/pkm/SKILL.md
git commit -m "feat(skill): add three-phase Knowledge Collection Protocol to pkm skill"
```

---

## Task 7: Final Verification

- [ ] **Step 1: Run full test suite**

```bash
cd /home/taeho/repos/pkm && uv run pytest tests/ -q 2>&1 | tail -10
```
Expected: 396+ tests pass, 0 failures.

- [ ] **Step 2: Verify hook end-to-end**

```bash
echo '{"message": "refactor the daemon pool architecture"}' | pkm hook run turn-start
```
Expected output structure:
```
## Relevant Notes
- [semantic|imp:N] ...

## Recent Context
...

# PKM Context
Relevant notes above are exploration starting points.
→ mcp__pkm__get_note_neighbors(note_id=<slug>) — explore connections (2-depth max)
→ mcp__pkm__pkm_ask(query=<question>) — synthesized answers from vault
Before starting non-trivial work: mcp__pkm__search(query=<topic>)
```

- [ ] **Step 3: Verify stop hook end-to-end**

```bash
echo '{}' | pkm hook run turn-end-exit2
```
Expected: prints `# Knowledge Extraction — complete these steps, then stop:` with numbered steps.

- [ ] **Step 4: Commit final verification tag (optional)**

```bash
git tag pkm-claude-alignment-v1
```
