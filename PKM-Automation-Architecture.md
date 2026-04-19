# PKM Automation Architecture

## Native Hooks & Automation
The system utilizes native Claude Code/OpenCode hooks to enforce agentic workflows without external plugin dependencies.

### Key Implementation Details
- **Stop Hooks**: Used instead of 'SessionEnd' for agentic enforcement loops. Exit code 2 with output sent to stderr ('exec 1>&2') blocks agent completion, forcing validation before exit.
- **Command Hooks**: Defined in `.opencode/command-hooks.jsonc` for `session.end` events to run quality gates (linting, testing, `opencode /review-work`, `opencode /remove-ai-slops`) and auto-commit changes.
- **Hook Configuration**: Configuration is written directly to `~/.claude/settings.json` (replacing previous unreliable plugin system approach).

## Agent Management
- **Hierarchical Context**: Organized using `AGENTS.md` files across the repository structure (root, cli, docs, plugins, codex).
- **Tool Routing**: `session-start` hooks prioritize MCP tools over direct CLI commands.
- **Dependency Management**: Local file dependencies (e.g., in `pyproject.toml`) have been migrated to `git+https` URLs to ensure compatibility with GitHub Actions/CI pipelines.
