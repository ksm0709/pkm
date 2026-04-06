# Memory Session Workflow

## Purpose
Track and retrieve all memories linked to a specific agent session. Used for session resumption, progress auditing, and consolidation preparation after task completion.

## Trigger
- **Primary:** memory session, session memory
- **Secondary:** session tracking, session resume

## Tools
- `pkm search --session` (query session memories)
- `pkm note add --content --session` (store with session tag)
- `pkm consolidate` (prepare for consolidation after session ends)

## Principles
- Generate the session ID once at the start and use it consistently throughout the session
- Always store episodic memories with the `--session` flag
- At session end, review results with `pkm search --session <id>`

## Session ID Convention

Use a short descriptive slug: `YYYY-MM-DD-task-name`

```bash
# Date + task name based
SESSION_ID="2026-04-05-auth-refactor"

# Auto-generated
SESSION_ID="$(date +%Y-%m-%d)-$(echo $TASK_NAME | tr ' ' '-' | head -c 20)"
```

## Edge Cases
- If the session ID is forgotten, find episodic memories using `pkm search` with a date range
- If no session memories exist, they may have been stored without the `--session` flag in that session
- Consolidation after session end is not required immediately — `pkm consolidate` manages candidates

## Example Flow

```bash
# 1. Session start: generate ID
SESSION_ID="2026-04-05-memory-layer-impl"

# 2. During work: store episodic memories
pkm note add --content "WS-1 frontmatter parsing complete, edge case: BOM header handling needed" \
  --type episodic --importance 6 --session $SESSION_ID

pkm note add --content "sentence-transformers lazy import improved startup from 1.2s to 0.1s" \
  --type procedural --importance 8 --session $SESSION_ID

# 3. Session end: review results
pkm search --session $SESSION_ID

# 4. Detailed retrieval as JSON
pkm search --session $SESSION_ID --format json

# 5. Check consolidation candidates (optional)
pkm consolidate
```

## Expected Output
- List of memories linked to the session (ordered by timestamp)
- Each entry: type, importance, title, stored time
- Summary of total memory count for the session
