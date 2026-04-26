# pkm daily

Manage daily notes.

## Usage
`pkm daily [OPTIONS] COMMAND [ARGS]...`

## Commands
- **`add`**: Append a timestamped `[hh:mm:ss]` log entry to the `## Logs` section.
- **`subnote`**: Create a sub-note and log a `[[wikilink]]` in today's daily note.
- **`edit`**: Open today's daily note in your configured editor.

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
pkm daily add "Shipped the installer fix"
pkm daily subnote "meeting" --content "# Meeting\n- discussed roadmap" --tags "work,meeting"
pkm daily subnote "ideas" --stdin < notes.md
pkm daily edit
```
