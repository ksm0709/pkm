# PKM

**Your Obsidian vault, upgraded into a real workflow.**

PKM is a terminal-first personal knowledge management CLI for people who live in Markdown, think in notes, and want their vault to stay useful over time. It combines fast daily capture, atomic notes, backlinks, tags, semantic search, vault management, and an AI-ready memory layer in one lightweight tool.

Whether you use Obsidian as a personal knowledge base, a work notebook, or a shared context layer for coding agents, PKM helps you capture ideas faster, retrieve them by meaning, and keep your vault organized without leaving the terminal.

---

## Why PKM

Most Markdown note systems start simple and slowly become hard to use:

- daily notes turn into messy timelines
- good ideas disappear into unsearchable files
- tags and links drift out of sync
- context from previous work sessions gets lost
- AI tools have no durable memory beyond chat history

PKM is designed to fix that.

It gives you a practical command-line layer for your Obsidian vault: quick capture for humans, durable memory for agents, and structure that scales as your notes grow.

---

## Quick start

### Install in one line

```bash
curl -fsSL https://raw.githubusercontent.com/ksm0709/pkm/main/cli/install.sh | bash
```

### Run the setup wizard

```bash
pkm setup
```

The setup flow can:

- install optional semantic search dependencies
- create or discover your vaults
- choose a default vault
- install PKM skill files for agent workflows

### First commands to try

```bash
pkm daily
pkm daily add "What I learned today"
pkm note add "A note worth keeping" --tags pkm,idea
pkm index
pkm search "what was that concurrency idea?"
```

---

## What PKM does

PKM provides a suite of CLI commands to manage your vault, as well as an MCP server for AI integration.

### CLI Features

We have extracted detailed documentation for each CLI command into the `docs/cli/` directory:

- [Daily Notes (`pkm daily`)](docs/cli/pkm-daily.md): Daily note workflows that stay lightweight.
- [Atomic Notes (`pkm note`)](docs/cli/pkm-note.md): Atomic note management built for actual use.
- [Semantic Search (`pkm search`)](docs/cli/pkm-search.md): Search your vault by meaning, not just exact wording.
- [Ask (`pkm ask`)](docs/cli/pkm-ask.md): Ask a natural language question about your vault (powered by an air-gapped LLM worker).
- [Index (`pkm index`)](docs/cli/pkm-index.md): Build the semantic search index.
- [Multi-Vault Management (`pkm vault`)](docs/cli/pkm-vault.md): Manage multiple vaults natively.
- [Tags (`pkm tags`)](docs/cli/pkm-tags.md): Tag navigation and vault maintenance.
- [Agent Hooks (`pkm hook`)](docs/cli/pkm-hook.md): Agent hooks and integrations for LLM workflows.
- [Config (`pkm config`)](docs/cli/pkm-config.md): Configuration management.
- [Data (`pkm data`)](docs/cli/pkm-data.md): Manage data files in the vault.
- [Stats (`pkm stats`)](docs/cli/pkm-stats.md): View vault statistics.
- [Consolidate (`pkm consolidate`)](docs/cli/pkm-consolidate.md): Nightly knowledge distillation.
- [Daemon (`pkm daemon`)](docs/cli/pkm-daemon.md): Background ML daemon (Host Daemon + Sandbox Worker) for fast semantic search and LLM tasks.
- [Setup (`pkm setup`)](docs/cli/pkm-setup.md): Interactive setup wizard.
- [Update (`pkm update`)](docs/cli/pkm-update.md): Update the CLI.
- [MCP Server (`pkm mcp`)](docs/cli/pkm-mcp.md): Start the MCP server for AI agent interactions.

For a full guide on the memory layer for AI agents, see: [`docs/agent-memory-policy.md`](docs/agent-memory-policy.md)

### MCP Server Integration

PKM includes a built-in MCP (Model Context Protocol) server to expose your vault to AI coding assistants (like Claude Desktop, Cursor, or Cline). It includes tools like `pkm_ask` for safe, parameterized natural language queries against your vault.

For full details and registration instructions, see: **[MCP Server Registration How-To](docs/mcp-server.md)**

---

## Example workflow

A typical PKM flow looks like this:

1. Run `pkm setup`
2. Open today’s note with `pkm daily`
3. Log progress with `pkm daily add "..."`
4. Turn a useful insight into an atomic note with `pkm note add`
5. Build the semantic index with `pkm index`
6. Retrieve the idea later with `pkm search "..."`
7. Save a durable lesson as a semantic memory for future sessions

The result is a vault that is easier to write to, easier to search, and more useful tomorrow than it was today.

---

## Installation options

### One-line install

```bash
curl -fsSL https://raw.githubusercontent.com/ksm0709/pkm/main/cli/install.sh | bash
```

### Install from source

```bash
git clone https://github.com/ksm0709/pkm ~/repos/pkm
cd ~/repos/pkm/cli
uv tool install --editable ".[search]"
```

### Development setup

```bash
cd cli
uv venv
uv pip install -e ".[search,dev]"
pytest tests/
```

Requirements:

- Python 3.10+
- [`uv`](https://github.com/astral-sh/uv)

---

## Repository layout

```text
pkm/
├── cli/          # Python package and CLI implementation
│   ├── src/pkm/
│   │   ├── commands/   # daily, note, search, vault, config, agent, update...
│   │   └── ...
│   └── tests/
├── docs/         # usage and policy docs
├── plugin/       # Claude Code plugin (hooks, skills)
└── README.md
```

---

## Why people end up liking PKM

Because it solves a real workflow problem:

- you can capture ideas quickly
- you can find them later without remembering exact words
- you can keep notes linked and maintained
- you can manage multiple vaults without ad hoc shell scripts
- you can give AI tools a durable memory layer that lives in your own Markdown files

PKM is opinionated, practical, and built for people who want their notes to stay useful.

---

## Contributing

Contributions are welcome.

If you want to work on PKM locally:

```bash
cd cli
uv venv
uv pip install -e ".[search,dev]"
pytest tests/
```

Good contribution areas include:

- improving onboarding and docs
- expanding note and vault workflows
- search quality and ranking
- agent-memory integrations
- UX polish for terminal output

---

## License

See the repository for license details.
