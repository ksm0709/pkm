# pkm search

Search vault notes semantically.

## Usage
`pkm search [OPTIONS] QUERY`

## Description
Search your vault semantically instead of using exact keyword matches. The default output is JSON (optimized for machine/agent reading). Use `--format table` for human-readable display.

When using JSON format, `pkm search` will also include `graph_context` if `--depth` is set > 0. This context includes the full frontmatter metadata and descriptions of all related notes within the specified graph depth, without requiring additional disk reads. If a note does not have a `description` in its frontmatter, the first 200 characters of its body text are automatically used as the description.

## Options
- `-n, --top INTEGER`: Number of results to return (default: 10).
- `--format [json|table]`: Output format.
- `--type [episodic|semantic|procedural]`: Filter by memory type.
- `--min-importance FLOAT RANGE`: Minimum importance score (1-10).
- `--recency-weight FLOAT RANGE`: Weight for recency+importance scoring (0=pure semantic) (0-1).
- `--session TEXT`: Filter by session ID.
- `--depth INTEGER`: Graph traversal depth.

## Examples
```bash
pkm search "vector database tradeoffs" --format table
pkm search "error" --type procedural --min-importance 5
pkm search "session work" --session abc123
pkm search "recent" --recency-weight 0.4
```
