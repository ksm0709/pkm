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
pkm hook setup --tool claude-code
```

## Default Lifecycle

Default setup installs `SessionStart` and `Stop` hooks only.

- `SessionStart` emits concise PKM retrieval guidance. It tells agents when to use
  `search`, graph neighbors, `ask`, daily-log reads, and daily logging.
- `Stop` preserves session knowledge when supported by the host agent.
- `UserPromptSubmit` is not installed by default, so PKM no longer injects relevant
  notes or recent daily context on every user prompt.

`pkm hook run turn-start` remains available as a legacy/manual command for direct
callers, but setup does not register it.
