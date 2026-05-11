# pkm relations

Show relation vocabulary, observed relation usage, and advisory audit findings.

Relations are typed graph metadata written in normal Obsidian-compatible
Markdown:

```markdown
&depends_on [[Vector Index]] - semantic search requires indexed embeddings
```

## Usage
`pkm relations [OPTIONS] COMMAND [ARGS]...`

## Commands
- **`show <relation>`**: Show one relation definition and usage summary.
- **`observed`**: List relation names used in notes but not yet in vocabulary.
- **`audit`**: Show advisory quality findings.
- **`promote <relation>`**: Add an observed relation to the vault vocabulary note.

## Options
- `--format [json|table]`: Output format (default: json).

## Source of Truth
Relation facts are canonical only when written in Markdown. Files under `.pkm/`
are rebuildable derived state.

- Markers in `notes/` become graph relation metadata.
- Markers in `daily/` are audit promotion candidates, not canonical graph
  relations.
- Standalone markers such as `&depends_on` without an immediate wikilink do not
  become graph relations.

## Vocabulary
Built-in relations include:

- `is_a`
- `part_of`
- `depends_on`
- `enables`
- `contrasts_with`
- `supersedes`
- `instance_of`
- `related`
- `source`

Vault-local vocabulary lives in `notes/pkm-relation-vocabulary.md`. It is normal
Markdown with `type: index` frontmatter and relation headings:

```markdown
---
id: pkm-relation-vocabulary
type: index
tags: []
---

## depends_on

- Description: Source requires target.
- Aliases: requires, needs
- Inverse: enables
- Example: &depends_on [[Vector Index]]
```

## Derived Files
`pkm index` writes:

- `.pkm/relations-vocabulary.json`
- `.pkm/relations-audit.json`

If those files are missing or stale, `pkm relations` commands rescan Markdown or
tell you to run `pkm index`; they do not treat `.pkm/` as canonical.

## Examples
```bash
pkm relations
pkm relations show depends_on
pkm relations observed
pkm relations audit
pkm relations promote implemented_by
```
