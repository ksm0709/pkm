# pkm daily

Manage daily notes.

## Usage
`pkm daily [OPTIONS] COMMAND [ARGS]...`

Without a subcommand, prints today's daily note (creating it if missing). Use the
read-side options below to view a past daily note instead.

### Options (base / `edit`)
- `--offset N` / `-o N`: Days before today (`0`=today, `1`=yesterday, `N`=N days ago).
  Past notes are read-only; the command will not auto-create them.
- `--date YYYY-MM-DD`: Explicit date. Takes precedence over `--offset`.

## Commands
- **`add`**: Append a timestamped `[hh:mm:ss]` log entry to today's `## Logs` section. Always today.
- **`subnote`**: Create a sub-note and log a `[[wikilink]]` in today's daily note. Always today.
- **`edit`**: Open a daily note in your configured editor. Defaults to today; `--offset N`
  or `--date YYYY-MM-DD` opens a past note (must already exist).

## Daily Note Format
```markdown
---
id: yyyy-mm-dd
consolidated: false
aliases: []
tags:
- daily-notes
---
## Logs
- [hh:mm:ss] log entry
- [hh:mm:ss] [[yyyy-mm-dd-subnote-title]]
```

## Examples
```bash
pkm daily
pkm daily --offset 1                          # view yesterday
pkm daily --date 2026-04-15                   # view explicit date
pkm daily add "Shipped the installer fix"
pkm daily subnote "meeting" --content "# Meeting\n- discussed roadmap" --tags "work,meeting"
pkm daily subnote "ideas" --stdin < notes.md
pkm daily edit
pkm daily edit --offset 2                     # edit 2 days ago (note must already exist)
```
