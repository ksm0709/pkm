# pkm daily

Manage daily notes.

## Usage
`pkm daily [OPTIONS] COMMAND [ARGS]...`

## Commands
- **`add`**: Append a timestamped log entry before the `## TODO` section.
- **`edit`**: Open today's daily note in your configured editor.
- **`todo`**: Append a timestamped TODO entry after the `## TODO` section.

## Examples
```bash
pkm daily
pkm daily add "Shipped the installer fix"
pkm daily todo "Write release notes"
pkm daily edit
pkm daily edit --sub "meeting"
```
