# pkm note

Manage durable atomic notes in the vault.

Use `pkm note` for long-lived knowledge: concepts, entities, processes,
principles, patterns, decisions, and index notes. Use `pkm daily add` or
`pkm daily subnote` for time-bound session state, progress logs, event notes,
investigations, and temporary TODO context.

Before adding a note, check that it has a stable definition, long-term scope,
and at least one meaningful relation or source link.

## Usage
`pkm note [OPTIONS] COMMAND [ARGS]...`

## Commands
- **`add`**: Create a new durable atomic note in the vault.
- **`auto-link`**: Auto-link plain text matching other notes' titles.
- **`edit`**: Open a note in the editor (search by title, first match).
- **`links`**: Show backlinks for a note.
- **`log`**: Show recent note operation log from `.pkm/log.md`.
- **`orphans`**: List orphan notes — notes with no inbound or outbound links.
- **`search`**: Search notes semantically (default: JSON output for agents).
- **`show`**: Show note contents.
- **`split`**: Split notes into smaller atomic notes.
- **`stale`**: Show notes not modified in the last N days.

## Examples
```bash
pkm note add "Postgres MVCC"
pkm note add "Retry strategy" --tags backend,reliability
pkm note edit postgres
pkm note show retry
pkm note links retry
pkm note stale --days 30
pkm note orphans
```
