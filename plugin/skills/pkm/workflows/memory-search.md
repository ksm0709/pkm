# Memory Search Workflow

## Purpose
Retrieve relevant memories using semantic + time-weighted search. Reuse past knowledge before starting work, before implementing, or when errors occur — to avoid repeating the same mistakes.

## Trigger
- **Primary:** memory search
- **Secondary:** past findings, recall, similar patterns

## Tools
- `pkm search` (semantic + time-weighted search CLI)

## Principles
- Always search for relevant past work at the start of a session
- Before implementing, check whether similar patterns have been found before
- When an error occurs, search for past fix recipes first

## Edge Cases
- If no results, retry with a more general search term
- Scores below 0.5 may have low relevance — use with caution
- Use `--format json` for output that can be consumed in a pipeline

## Example Flow

```bash
# 1. Basic semantic search
pkm search "authentication error"

# 2. Type filter
pkm search "database migration" --type procedural

# 3. Recency + importance weighting
pkm search "architecture decision" --recency-weight 0.4 --min-importance 7

# 4. Top 20 results as JSON
pkm search "error handling" --top 20 --format json

# 5. Session start pattern
SESSION_TOPIC="auth refactor"
pkm search "$SESSION_TOPIC" --top 5
pkm search "$SESSION_TOPIC" --type procedural --top 3
```

## Scoring Formula

```
score = (1 - α) * semantic_similarity + α * recency_score * (importance / 10)
```

| `--recency-weight` | Behavior |
|-------------------|----------|
| `0` (default) | Pure semantic similarity |
| `0.5` | Balanced semantic + recency |
| `1.0` | Recency + importance focused |

## Output Formats

| Format | Description |
|--------|-------------|
| `table` (default) | Score \| Type \| Importance \| Title table |
| `plain` | `score path title` one per line |
| `json` | Full structured output, pipeline-ready |

## Expected Output
- List of relevant memories (sorted by score)
- Each entry: similarity score, type, importance, title, path
