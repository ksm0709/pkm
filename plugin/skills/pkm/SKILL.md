---
name: pkm
description: "Personal Knowledge Management for Obsidian vaults — Zettelkasten workflow with daily notes, atomic notes, wikilinks, and a Python CLI tool (pkm). Use this skill whenever the user mentions: daily notes, note management, knowledge extraction, Zettelkasten, note search, backlinks, wikilinks, PKM, note writing, tag search, tag explore, backlink traverse, or wants to create/update/search notes in their Obsidian vaults. Also trigger when the user says /pkm. Workflow triggers: zettel-loop, refine-loop."
---

# PKM — Personal Knowledge Management

Obsidian vault-based Zettelkasten knowledge management system. Uses daily notes as the entry point for knowledge, refines knowledge into atomic notes, and builds a knowledge network with wikilinks.

## Vault Structure

All vaults follow the standard structure below:

```
<vault>/
├── daily/              # YYYY-MM-DD.md — chronological records
├── notes/              # flat-structure Zettelkasten atomic notes
├── tags/               # tag index notes (one .md file per tag)
├── tasks/              # ongoing.md + task-<slug>.md
│   └── archive/        # completed tasks
└── data/               # note attachments
```

Vaults are automatically discovered under `PKM_VAULTS_ROOT` (default: `~/vaults`). A directory is recognized as a vault if it contains a `daily/` or `notes/` subdirectory.

When used inside a Git repository, the vault name is automatically assigned in `@owner--repo` format to distinguish it from regular vaults (e.g., `@taeho--pkm`).

## Core Workflow

```
[experience/learning] → daily/ (chronological record) → repeated/structured value found → notes/ (atomic note promotion)
                                                                                         ↕ [[wikilink]] connections
                                                                                    notes/ ↔ notes/ (knowledge network)
                                                                                         |
                                                                          pkm search (semantic search)
                                                                          workflows/ (automated knowledge management)
```

### 1. Daily Note — Entry Point for Knowledge

Record the day's experiences, learning, and ideas in chronological order. It doesn't need to be perfect — capturing it comes first.

```markdown
---
id: 2026-04-05
aliases: []
tags:
  - daily-notes
---
- [09:30] Learned today: ...
- [14:20] Ideas from the meeting: ...

## TODO
- [09:30] Task item
```

### 2. Atomic Note — Refined Knowledge

Promote knowledge that appears repeatedly in dailies or is worth structuring into an atomic note.

**Principles:**
- **Atomicity**: One note = one topic. Don't mix multiple topics.
- **Connection**: Every note must be connected to related notes via `[[wikilink]]`. Isolated notes are dead knowledge.
- **Own words**: Not copy-paste — understand the core and write it concisely.
- **Flat structure**: Classify with tags, no nested folders inside `notes/`.

```markdown
---
id: <filename-without-extension>
aliases:
  - <short alias>
tags:
  - <topic-tag>
description: "one-line summary (optional)"
---

Content...

Related: [[YYYY-MM-DD]] (first learned), [[related-concept]]
```

The `description` field is optional and appears next to the title in backlink lists.

### 3. Knowledge Extraction — Criteria for Promotion

Criteria for deciding when to promote from a daily note to an atomic note:

- **Recurrence**: If the same topic appears in dailies for 3+ days, it's a promotion candidate
- **Reference potential**: Independent knowledge worth referencing in other contexts
- **Structuring value**: When scattered notes can be organized into a single concept
- **Connection potential**: When meaningful connections can be made with existing atomic notes

## CLI Tool: `pkm`

Python CLI tool at `~/.claude/skills/pkm/scripts/pkm-cli/`. Install with:

```bash
cd ~/.claude/skills/pkm/scripts/pkm-cli && uv pip install -e ".[search]"
```

### Configuration

```bash
export PKM_VAULTS_ROOT=~/vaults        # vault root directory (default: ~/vaults)
export PKM_DEFAULT_VAULT=<vault-name>  # default vault (first discovered vault if not set)
```

### Commands

```bash
# Daily notes
pkm daily                          # Show/create today's daily note
pkm daily --vault <name>           # Specific vault
pkm daily add "learning content"   # Append timestamped entry
pkm daily todo "task"              # Add to TODO section

# Note management
pkm note add "Note Title" --tags t1,t2  # Create atomic note with frontmatter
pkm note add "Title" --vault <name>     # In specific vault
pkm note show <query>                   # Show note content + backlinks section
pkm note edit <query>                   # Open note in editor by title keyword
pkm note links <query>                  # Show backlinks for a note (who links here?)
pkm note stale --days 30               # Notes not updated in 30+ days
pkm note orphans                        # Find notes with no wikilinks (dead knowledge)

# Tag index notes
pkm tags                           # List all tags with counts
pkm tags show <tag>                # Show tag note + notes with that tag
pkm tags edit <tag>                # Open tag note in editor
pkm tags search "python*"          # Glob pattern search
pkm tags search "python+ml"        # AND: notes with both tags
pkm tags search "python,rust"      # OR: notes with either tag

# Data files
pkm data                           # List data files in vault
pkm data add <fname> <path>        # Copy local file into vault data/
pkm data add <fname> <url>         # Download URL into vault data/
pkm data add <fname> <src> --force # Overwrite existing file
pkm data rm <fname>                # Remove a data file from vault

# Vault management
pkm vault list                     # List vaults (git vaults show @owner--repo)
pkm vault where                    # Show active vault name and path (2 lines)
pkm vault add <name>               # Create new vault
pkm vault open <name>              # Switch active vault

# Maintenance
pkm stats                          # Vault statistics
pkm search <query>                 # Semantic search (use --format json --depth 1 to include related note metadata)
pkm ask <query>                    # Ask a natural language question (uses semantic search for RAG context, requires daemon & air-gapped worker)
pkm ask --list-models              # List available LLM models
pkm index                          # Build/rebuild search index
```

### Design Principles

- **No database** — files are the single source of truth. No conflict with Obsidian
- **Auto vault discovery** — vaults are recognized by directory structure, no hardcoding
- **Native language support** — filenames, content, and search all support non-ASCII characters

## Vault Context (MANDATORY)

PKM 명령을 실행하기 전, 항상 다음 순서로 vault 컨텍스트를 확인합니다:

1. **현재 vault 확인**: `pkm vault where` — 이름(1줄)과 경로(1줄) 출력
2. **올바른 vault인지 검증**: 현재 작업 프로젝트/디렉토리에 맞는 vault인지 확인
3. **불일치 시 전환**: `pkm vault open <name>` 으로 명시적 전환 후 다시 확인
4. **PKM 명령 실행**: `pkm daily add ...`, `pkm note add ...` 등 실행

> vault 디렉토리로 직접 이동(cd)할 필요 없음 — pkm 명령은 어느 디렉토리에서든 실행 가능.
> vault 경로가 필요하면 `pkm vault where` 두 번째 줄을 사용하세요.

**예시:**
```bash
$ pkm vault where
@bearrobotics--pennybot
/home/taeho/vaults/@bearrobotics--pennybot

# vault가 맞지 않으면:
$ pkm vault open @taeho--pkm
★ Switched to vault '@taeho--pkm'

# 이후 PKM 명령 실행:
$ pkm daily add "오늘의 작업 내용"
```

## Write Gates (MANDATORY)

**Never create or append to daily/note files directly with Write/Edit tools as the first action.** Always use the CLI as the entry gate:

- **Daily entries**: `pkm daily add "<text>"` — ensures timestamp format, frontmatter, and TODO section integrity
- **New notes**: `pkm note add "<Title>" --tags t1,t2` — ensures required frontmatter (id, aliases, tags, description)
- **TODO items**: `pkm daily todo "<task>"` — places item in the correct section

**After** the CLI creates the file/entry, using Read/Edit to modify the internal content is fine (e.g., expanding a note body, fixing wording). The gate applies to creation and appending only.

### Tag Index Notes & Backlinks

Tags are managed as physical .md files in the `tags/` directory. Tag notes are created lazily on access, and adding a description turns them into index cards. Backlinks are automatically shown in `note show`, and can also be queried directly with `note links`.

## Workflows

PKM workflows are defined as independent documents in the `workflows/` folder. Find the workflow matching the user's request, read that document, and execute it.

| Workflow | Primary Trigger | Document |
|----------|----------------|------|
| Zettel Loop | zettel-loop, knowledge production, promote knowledge | workflows/zettel-loop.md |
| Refine Loop | refine-loop, knowledge cleanup, vault refinement | workflows/refine-loop.md |

When a user request matches one of the triggers above, read the corresponding `workflows/*.md` and execute it. If multiple workflows could match, ask the user which one they want.

## Workflow Extension Guide

To add a new workflow:
1. Copy `workflows/_template.md` to create a new file
2. Fill in Purpose, Trigger, Tools, Principles, Edge Cases, Example Flow, Expected Output
3. Add an entry to the Workflows table above
4. Accumulate related know-how in references/principles.md

Criteria for a good workflow:
- Executable via pkm CLI commands or file tools
- Respects agent discretion (no excessive step-by-step directives)
- Clear output definition
- Consistent quality on repeated execution
- Unique Primary Trigger (must not overlap with other workflows)

## Principles & Know-how

Accumulated PKM principles and patterns are in `references/principles.md`. Read it when making decisions about note structure, tagging strategy, or knowledge organization. This file grows over time as we discover what works.

Read `references/workflows.md` for specific workflow patterns and automation recipes.

## Task Checklist

When the user asks for PKM help, follow this flow:

1. **Identify intent**: daily logging, note creation, knowledge extraction, or maintenance?
2. **Check vault context**: Run `pkm vault where` to confirm active vault. If wrong, run `pkm vault open <name>` to switch. No need to cd into vault directory.
3. **Choose vault**: Infer from context if not specified. Use `--vault` flag or `PKM_DEFAULT_VAULT`.
3. **Check existing notes**: Search before creating — avoid duplicates.
4. **Maintain connections**: Every new note must link to at least one existing note.
5. **Use appropriate tool**: CLI as the write gate (creation/append), Read/Edit for subsequent content editing.
