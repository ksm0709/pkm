# pkm hook

Lifecycle hook handlers for LLM agent integrations.

## Usage
`pkm hook [OPTIONS] COMMAND [ARGS]...`

## Commands
- **`debug`**: Toggle hook debug mode.
- **`remove`**: Remove PKM hooks from `~/.claude/settings.json`.
- **`run`**: Run a lifecycle hook handler.
- **`setup`**: Print hook install instructions for agent tools.

## Examples
```bash
pkm hook run session-start --format system-reminder
pkm hook run turn-start --format system-reminder --session my-task
pkm hook setup --tool claude-code
```
