# Consolidated PKM Agent Architecture

## 1. Architectural Strategy
The system follows the "LLM Wiki" paradigm, prioritizing compile-first workflows over dynamic RAG. Agentic logic is enforced via structured hooks:
- **Claude Code/Codex Hooks**: Shifted from unreliable plugins to direct configuration (`~/.claude/settings.json`, `codex/hooks.json`).
- **Enforcement Loops**: Utilizing 'Stop' events and exit code `2` to block completions, forcing validation (linting, git state) before termination.
- **MCP Prioritization**: Session-start hooks are configured to prefer MCP tools over raw CLI commands.

## 2. Security & Risk Management
- **Indirect Prompt Injection**: A primary vulnerability in autonomous vault-reading agents.
- **Mitigations**: 
    - OS-level sandboxing/AppArmor.
    - Explicit user-approval staging areas for destructive file modifications.
    - Capability-based access control rather than broad file-system access.

## 3. Implementation Hierarchy (AGENTS.md)
A hierarchical structure has been established (root → cli, docs, plugin, codex) to document agentic responsibilities. Hidden directories (.context, .omc, .omx) are explicitly excluded from these recursive indexing tasks.
