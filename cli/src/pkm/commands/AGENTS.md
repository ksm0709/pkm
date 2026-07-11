<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-19 | Updated: 2026-04-19 -->

# commands

## Purpose
One Click command group per file. Each module implements a top-level `pkm <subcommand>` group and its subcommands. All modules are registered in `cli.py`.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | Empty package init |
| `config.py` | `pkm config` — read/write vault, graph, editor, and web settings |
| `consolidate.py` | `pkm consolidate` — nightly distillation of daily notes into atomic notes |
| `daemon.py` | `pkm daemon` — start/stop/status of background semantic search daemon |
| `daily.py` | `pkm daily` — open, add entries to, and navigate daily notes |
| `data.py` | `pkm data` — copy/download files into vault `data/` and remove them |
| `hook.py` | `pkm hook` — manage agent lifecycle hooks (session-start, stop payloads) |
| `links.py` | `pkm links` — list backlinks and wikilink graph for a note |
| `maintenance.py` | `pkm stats` — vault statistics and health summary |
| `mcp.py` | `pkm mcp` — launch the MCP server process |
| `notes.py` | `pkm note` — add, list, view, and delete atomic notes |
| `search.py` | `pkm search` / `pkm index` — semantic and keyword search, index build |
| `setup.py` | `pkm setup` — interactive first-run wizard |
| `tag_commands.py` | `pkm tags` — tag listing, exploration, and maintenance |
| `update.py` | `pkm update` — self-update the PKM CLI |
| `vault.py` | `pkm vault` — multi-vault add/remove/switch/list |
| `_trash.py` | Internal helper for safe file deletion (moves to trash, not permanent delete) |

## For AI Agents

### Working In This Directory
- Each file exposes a Click group or command that is imported and registered in `../cli.py`.
- Vault-free commands (those that work without a configured vault) are listed in `VAULT_FREE_COMMANDS` in `cli.py` — add new ones there if applicable.
- Use `_trash.py` for any file deletion to maintain recoverability.
- Guard optional `sentence-transformers` / `numpy` imports with `try/except ImportError` and emit a friendly `click.ClickException`.

### Testing Requirements
- Each command module should have a corresponding `tests/test_<module>.py`.
- Use the Click `CliRunner` from `conftest.py` to invoke commands in tests.

### Common Patterns
- Click group pattern: `@click.group(); def <name>(): pass` then `@<name>.command()` for subcommands.
- Vault resolution: `vault = get_vault(vault_name)` at the start of each command that needs it.
- Rich console for output: `console = Console()` from `rich`.

## Dependencies

### Internal
- `pkm.config` — vault resolution
- `pkm.models` — shared data types
- `pkm.frontmatter` — note parsing
- `pkm.search_engine` — semantic search (optional)
- `pkm.daemon` — daemon client helpers

### External
- `click`, `rich` (always); `sentence-transformers`, `numpy` (optional search dependencies)

<!-- MANUAL: -->
