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

### 1. Daily note workflows that stay lightweight

PKM makes daily notes feel fast instead of ceremonial.

```bash
pkm daily
pkm daily add "Shipped the installer fix"
pkm daily todo "Write release notes"
pkm daily edit
pkm daily edit --sub "meeting"
```

Highlights:

- creates today’s daily note automatically
- appends timestamped log entries
- appends timestamped TODOs under a dedicated section
- supports sub-notes like `2026-04-06-meeting.md`
- prints daily notes and same-day sub-notes together for quick review

This gives you a frictionless working log without forcing you into a heavy journaling system.

---

### 2. Atomic note management built for actual use

Create small, reusable notes and find them again without memorizing filenames.

```bash
pkm note add "Postgres MVCC"
pkm note add "Retry strategy" --tags backend,reliability
pkm note edit postgres
pkm note show retry
pkm note links retry
pkm note stale --days 30
pkm note orphans
```

Highlights:

- creates atomic notes with frontmatter
- supports tag assignment at creation time
- lets you open or show notes by title search
- shows backlinks for linked notes
- finds stale notes that may need attention
- finds orphan notes with no wikilink connections

PKM helps your vault become a living system instead of a pile of Markdown files.

---

### 3. Semantic search, not just filename search

When exact wording fails, PKM can search by meaning.

```bash
pkm index
pkm search "vector database tradeoffs"
pkm search "recent debugging lessons" --type semantic --min-importance 7
pkm search "what did I do in this session?" --session feat-auth
```

Highlights:

- builds a semantic index of your vault
- retrieves notes by meaning instead of exact matches
- supports memory-type filtering
- supports importance filtering
- supports session-specific recall
- warns when your index may be stale

Semantic search is optional during setup because it installs heavier dependencies, but it is one of PKM’s biggest quality-of-life upgrades once your vault gets large.

---

### 4. A real memory layer for AI agents

This is one of PKM’s standout features.

PKM can store structured memories inside your vault so coding agents and assistants can reuse decisions, discoveries, errors, and workflow knowledge across sessions.

```bash
pkm note add --content "Use WAL mode for concurrent SQLite reads" \
  --type semantic --importance 8

pkm note add --content "Stopped at the auth middleware refactor" \
  --type episodic --importance 5 --session feat-auth

pkm search "sqlite concurrency"
pkm search "auth middleware" --session feat-auth
pkm consolidate
pkm consolidate mark 2026-04-05
```

Memory features:

- supports `semantic`, `episodic`, and `procedural` memory types
- stores importance scores for ranking and prioritization
- supports session-scoped recall
- encourages search-before-store to avoid duplicates
- surfaces recent memories at agent session start
- can append summaries back into daily notes
- supports consolidation of past daily notes into durable memory candidates

If you use Claude Code, Codex, or opencode, PKM gives you a practical persistent memory layer instead of relying on chat transcripts alone.

Full guide: [`docs/agent-memory-policy.md`](docs/agent-memory-policy.md)

---

### 5. Agent hooks and integrations

PKM includes commands for wiring memory into tool-driven workflows.

```bash
pkm agent hook session-start --format system-reminder
pkm agent hook turn-start --format system-reminder --session my-task
pkm agent setup-hooks --tool claude-code
pkm agent setup-hooks --tool codex
pkm agent setup-hooks --tool opencode
```

Highlights:

- injects recent daily context at session start
- surfaces recent high-importance memories automatically
- prints lightweight turn-start reminders for active workflows
- can write or print hook configuration for supported tools
- installs PKM skill files during setup for agent-friendly usage

This makes PKM useful both as a human note system and as shared context infrastructure for AI-assisted work.

---

### 6. Multi-vault management

PKM is not limited to a single notes folder.

```bash
pkm vault list
pkm vault add personal
pkm vault open personal
pkm --vault work daily
```

Highlights:

- discovers vaults automatically from your vault root
- creates new vaults with a standard PKM structure
- switches the active vault with one command
- supports explicit `--vault` overrides
- can resolve the active vault from local config, environment, git project context, or global config
- can create git-aware vault names like `@owner--repo`

That last point is especially useful if you want one vault per codebase or project.

---

### 7. Tag navigation and vault maintenance

PKM helps you keep the vault healthy, not just write more into it.

```bash
pkm tags
pkm tags show backend
pkm tags search "backend+reliability"
pkm tags search "proj-*"
pkm stats
```

Highlights:

- lists tags and usage counts
- opens or creates dedicated tag notes
- shows all notes associated with a tag
- supports exact, AND, OR, and glob tag searches
- shows vault-level stats like notes, dailies, tasks, orphans, unique tags, average links, and index status

---

### 8. Configuration and update flow

PKM keeps setup simple and maintenance straightforward.

```bash
pkm config set default-vault personal
pkm config set editor "code --wait"
pkm config list
pkm update
pkm update v2.4.0
```

Highlights:

- stores global config in `~/.config/pkm/config`
- lets you set a default vault and preferred editor
- supports updating to the latest version
- supports checking out and reinstalling a specific tagged version from a local clone
- uses `uv tool install` for tool-style installation and upgrades

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
