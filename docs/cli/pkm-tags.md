# pkm tags

Show all tags used across notes and dailies, sorted by count.

## Usage
`pkm tags [OPTIONS] COMMAND [ARGS]...`

## Commands
- **`edit`**: Open a tag note in the editor.
- **`search`**: Search notes by tag pattern.
- **`show`**: Show a tag note and all notes with that tag.

## Options
- `--format [json|table]`: Output format (default: json).

## Examples
```bash
pkm tags
pkm tags show backend
pkm tags search "backend+reliability"
pkm tags search "proj-*"
```
