# pkm search

Search vault notes semantically.

## Usage
`pkm search [OPTIONS] QUERY`

## Description
Search your vault semantically instead of using exact keyword matches. The default output is JSON (optimized for machine/agent reading). Use `--format table` for human-readable display.

When using JSON format, `pkm search` includes a `related_notes` field for each result with structured graph neighbors (`outbound`, `inbound`, `semantic`). Semantic neighbors require `graph_enriched.json` to be present (built during `pkm index`).

## Options
- `-n, --top INTEGER`: Number of results to return (default: 10).
- `--format [json|table]`: Output format.
- `--type [episodic|semantic|procedural]`: Filter by memory type. `episodic`
  remains available for older notes; new session state should live in `daily/`.
- `--min-importance FLOAT RANGE`: Minimum importance score (1-10).
- `--recency-weight FLOAT RANGE`: Weight for recency+importance scoring (0=pure semantic) (0-1).
- `--session TEXT`: Filter by session ID.

## Examples
```bash
pkm search "vector database tradeoffs" --format table
pkm search "error" --type procedural --min-importance 5
pkm search "session work" --session abc123
pkm search "recent" --recency-weight 0.4
```
