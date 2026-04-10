# PKM Plugin — Install Guide

PKM knowledge hooks for Claude Code, Codex, and opencode.

## Prerequisites

```bash
pip install pkm
pkm vault init  # configure your vault
```

## Claude Code

Install via Claude Code plugin marketplace (recommended).

Or register the hooks manually by adding to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "pkm hook run session-start --format system-reminder", "timeout": 10}]}],
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "pkm hook run turn-start --format system-reminder", "timeout": 10}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "pkm hook run turn-end --format system-reminder", "timeout": 30}]}]
  }
}
```

**If you previously used `pkm hook setup --tool claude-code`**, remove old hooks:
```bash
pkm hook migrate
```

## Codex

Install the Codex hook config:
```bash
# Copy (or symlink for auto-updates):
cp codex/hooks.json ~/.codex/hooks.json
# or
ln -sf "$(pwd)/codex/hooks.json" ~/.codex/hooks.json
```

Or run:
```bash
pkm hook setup --tool codex
```

## opencode (oh-my-opencode bridge)

opencode with the omo bridge reads `plugin/hooks/hooks.json` automatically.
No additional configuration needed — install the PKM plugin and omo will pick up the hooks.
