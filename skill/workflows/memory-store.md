# Memory Store Workflow

## Purpose
Store facts, decisions, error fixes, and patterns discovered by agents as atomic notes in the PKM vault. These notes become reusable long-term memory through semantic + time-weighted search.

## Trigger
- **Primary:** memory store
- **Secondary:** remember this, store finding

## Tools
- `pkm note add --content` (memory storage CLI)
- `pkm search` (duplicate check before storing)

## Principles
- Always search before storing to prevent duplicates
- Explicitly specify memory type and importance
- Use the `--session` flag when session tracking is needed

## Memory Types

| Type | When | Example |
|------|------|---------|
| `semantic` | Stable knowledge, facts, patterns | Architecture decisions, API behavior |
| `episodic` | In-session events, progress | "Fixed login bug in session X" |
| `procedural` | Methods, fix recipes | "To fix Y, do Z" |

## Importance Scale

| Score | Meaning |
|-------|---------|
| 1-3 | Trivial, low value |
| 4-6 | Moderate, useful context |
| 7-8 | Important, should resurface |
| 9-10 | Critical, always relevant |

## Edge Cases
- If a similar memory already exists, do not store a new one — augment the existing note instead
- If importance is hard to judge, set to 5 and adjust later
- Use stdin mode for multi-line content

## Example Flow

```bash
# 1. Check for duplicates before storing
pkm search "IndexEntry crash unknown fields" --top 3

# 2. If no similar entry exists, store it
pkm note add --content "IndexEntry crash occurs when adding new fields — fix: filter unknown fields in load_index()" \
  --type procedural --importance 8

# 3. Store with session tracking
pkm note add --content "WS-1 frontmatter implementation complete" \
  --type episodic --importance 5 --session 2026-04-05-memory-layer

# 4. Multi-line content (stdin)
cat << 'EOF' | pkm note add --content --stdin --type semantic --importance 7
Generative Agents scoring formula:
score = (1 - α) * cosine_similarity + α * recency * (importance / 10)
recency = 0.995^hours_elapsed
EOF
```

## Expected Output
- Stored note path (`memory/YYYY-MM-DD-<slug>.md`)
- Duplicate warning (if a similar memory is found)
