<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-19 | Updated: 2026-04-19 -->

# cli

## Purpose
Python package root for the `pkm` CLI. Contains the installable package source, test suite, build configuration, and development utilities.

## Key Files

| File | Description |
|------|-------------|
| `pyproject.toml` | Package metadata, dependencies, and build config (hatchling) |
| `uv.lock` | Locked dependency manifest for reproducible installs |
| `install.sh` | One-liner install script for end users |
| `measure_index_load.py` | Benchmark script for search index load time |
| `measure_index_load_huge.py` | Benchmark for large-vault index load |
| `measure_mem.py` | Memory usage profiling script |
| `test_bug.py` | Ad-hoc bug reproduction script (not part of test suite) |
| `test_dedup.py` | Ad-hoc deduplication test script |
| `dummy_graph.json` | Fixture data for graph-related manual testing |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `src/` | Package source tree (see `src/AGENTS.md`) |
| `tests/` | pytest test suite (see `tests/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- Use `uv` for all dependency management: `uv add <pkg>`, `uv run pytest`.
- The package entry point is `pkm = "pkm.cli:main"` (see `pyproject.toml`).
- Optional `[search]` extras activate semantic search; `[dev]` extras add pytest.

### Testing Requirements
- `uv run pytest` from this directory runs all tests.
- Tests must use temporary directories, never the real vault.
- Coverage target: maintain or improve existing coverage.

### Common Patterns
- Add new commands as a new file in `src/pkm/commands/` and register in `src/pkm/cli.py`.
- Optional search dependencies are guarded with `try/except ImportError`.

## Dependencies

### External
- `click` ≥ 8.0, `rich` ≥ 13.0, `pyyaml` ≥ 6.0, `mcp` ≥ 1.20, `mistletoe` ≥ 1.0, `networkx` ≥ 3.0
- Optional search dependencies: `sentence-transformers`, `numpy`

<!-- MANUAL: -->
