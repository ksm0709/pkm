# pkm index

Build the semantic search index for the vault.

## Usage
`pkm index [OPTIONS]`

## Description
This command builds or updates the semantic search index of your vault. Run this command when you have created or updated multiple notes to ensure the semantic search results are up to date.

It writes the following files under `.pkm/`:
- `ast.db` — incremental AST cache
- `graph.json` — structural graph (wikilinks + tags + optional relation metadata)
- `vector.db` — sentence-transformer embeddings
- `index.json` — semantic search index
- `graph_enriched.json` — enriched graph with semantic_similar edges, Louvain communities, and cluster centroids. Used by `pkm graph surprising` and agent tools (`find_surprising_connections`, `list_clusters`, `list_god_nodes`, `create_hub_note`).
- `relations-vocabulary.json` — derived relation vocabulary and observed usage cache
- `relations-audit.json` — derived advisory relation quality report

Similarity threshold for `semantic_similar` edges is configurable via `graph-similarity-threshold` in `~/.config/pkm/config` (default `0.75`).

Relation markers such as `&depends_on [[target]] - reason` in `notes/` are
merged into graph edge metadata. Markers in `daily/` are reported as promotion
candidates only. `.pkm/` files are derived and can be rebuilt from Markdown.

## Examples
```bash
pkm index
```
