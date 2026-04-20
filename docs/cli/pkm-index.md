# pkm index

Build the semantic search index for the vault.

## Usage
`pkm index [OPTIONS]`

## Description
This command builds or updates the semantic search index of your vault. Run this command when you have created or updated multiple notes to ensure the semantic search results are up to date.

It writes the following files under `.pkm/`:
- `ast.db` — incremental AST cache
- `graph.json` — structural graph (wikilinks + tags)
- `vector.db` — sentence-transformer embeddings
- `index.json` — semantic search index
- `graph_enriched.json` — enriched graph with semantic_similar edges, Louvain communities, and cluster centroids. Used by `pkm graph surprising` and agent tools (`find_surprising_connections`, `list_clusters`, `list_god_nodes`, `create_hub_note`).

Similarity threshold for `semantic_similar` edges is configurable via `graph-similarity-threshold` in `~/.config/pkm/config` (default `0.75`).

## Examples
```bash
pkm index
```
