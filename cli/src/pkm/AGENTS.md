<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-19 | Updated: 2026-04-19 -->

# pkm

## Purpose
Core Python package implementing all PKM CLI logic — vault management, note I/O, search, daemon, MCP server, and command routing.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | Package init; exposes `__version__` |
| `__main__.py` | `python -m pkm` entry point |
| `cli.py` | Root Click group; registers all command groups and vault resolution |
| `config.py` | Vault discovery, config file loading, `get_vault()` resolution |
| `_memory_types.py` | Memory type constants, schema version, importance defaults |
| `frontmatter.py` | YAML frontmatter parse/serialize for Markdown files |
| `wikilinks.py` | Wikilink extraction and backlink counting |
| `graph.py` | Note graph construction using `networkx` |
| `search_engine.py` | Semantic search engine — vector index (SQLite/FAISS), incremental embeddings |
| `daemon.py` | Background daemon via Unix socket; hosts VectorIndex for fast repeated queries |
| `mcp_server.py` | FastMCP server exposing `note_add`, `daily_add`, `search`, `index` tools |
| `editor.py` | Opens notes in `$EDITOR` |
| `changelog.py` | Reads and formats `CHANGELOG.md` for `--version` output |
| `version_check.py` | Checks PyPI for newer releases |
| `_install_source.py` | Helpers for the install script |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `commands/` | One module per CLI subcommand group (see `commands/AGENTS.md`) |
| `tools/` | Framework-free domain helpers for notes, links, and search |

## For AI Agents

### Working In This Directory
- `cli.py` is the integration point — register new command groups here with `main.add_command()`.
- `config.py:get_vault()` is the single source of truth for resolving the active vault path.
- Search functionality requires the `[search]` extras; guard with `try/except ImportError`.
- Daemon communicates over `~/.config/pkm/daemon.sock` (Unix domain socket).
- MCP server is launched via `pkm mcp` and registered in the host's MCP config.

### Testing Requirements
- Unit test each module independently; use `conftest.py` fixtures for vault setup.
- Daemon tests must avoid port/socket conflicts — use a temp socket path.

### Common Patterns
- Optional import guard: `try: from sentence_transformers import ... except ImportError: raise click.ClickException(...)`.
- Frontmatter is always parsed via `frontmatter.parse()`; never manually split `---` blocks.
- Vault path: always obtained from `get_vault()`, never hardcoded.

### Domain and MCP Tool Rule
Keep `tools/notes.py`, `tools/links.py`, and `tools/search.py` framework-free:
their helpers accept an explicit vault and return domain data. `mcp_server.py`
exposes FastMCP tools directly and adapts those helpers to JSON-safe responses.
When changing shared behavior, update both the domain helper tests and the nearest
FastMCP function/tool-discovery contract.

## Dependencies

### Internal
- All modules within this package are interdependent via relative imports.

### External
- `click`, `rich`, `pyyaml`, `mcp`, `mistletoe`, `networkx` (always)
- `sentence-transformers`, `numpy` (optional, `[search]` extra)

<!-- MANUAL: -->
