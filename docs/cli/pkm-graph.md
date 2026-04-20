# pkm graph

Graph analysis commands on the enriched vault graph.

## Subcommands

### pkm graph surprising

Show surprising cross-cluster bridge notes — notes that semantically sit between two different topic clusters.

Uses centroid bridge score: `1 / (dist_a + dist_b + |dist_a - dist_b|)`. The asymmetry term penalizes notes close to only one centroid, so equidistant (true bridge) notes rank higher than cluster-interior notes.

## Usage
`pkm graph surprising [OPTIONS]`

## Options
- `--top, -n INT` — Number of results to return (default 20).
- `--format [json|table]` — Output format. Default is JSON (machine-readable); use `table` for human display.

## Examples
```bash
pkm graph surprising
pkm graph surprising --top 10 --format table
```

## Prerequisites
Run `pkm index` first to build `.pkm/graph_enriched.json`. Requires the semantic search extra (`pkm setup`).
