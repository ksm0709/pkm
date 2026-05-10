# PKM Relations Graph Design

Date: 2026-05-11
Status: approved design
Scope: Obsidian-compatible relation system for PKM

## Summary

PKM should support a more systematic ontology workflow without turning ontology
into a second database. The product terminology for the system is **relations**.
Ontology remains a methodology described in guidance: users and agents can use
relations to build a durable knowledge system, but CLI commands, graph schema,
and derived files should use relation-oriented names.

Canonical relation facts live in Obsidian-compatible Markdown. `.pkm/` files are
derived caches or reports and can always be rebuilt from the vault.

## Goals

- Preserve Obsidian compatibility: Markdown files remain readable and editable
  without PKM.
- Keep the vault portable: deleting `.pkm/` must not lose canonical relation
  facts.
- Make relation extraction deterministic enough to rebuild from Markdown.
- Integrate relation data into the existing graph pipeline instead of creating
  a second canonical ontology store.
- Provide a vocabulary management surface so agents do not invent relation
  names blindly.
- Support audit-first quality control without blocking note writing.

## Non-Goals

- No Obsidian plugin requirement.
- No canonical sidecar database under `.pkm/`.
- No schema validation that blocks note creation or editing.
- No automatic rewrite, promotion, demotion, or relation inference in the first
  implementation.
- No LLM-inferred relation becomes canonical unless it is written back into
  Markdown as a relation marker.

## Core Model

A relation fact exists only when Markdown contains a deterministic marker:

```markdown
&depends_on [[Vector Index]] - semantic search requires indexed embeddings
```

`pkm index` parses these markers and folds them into the existing graph layer.
The graph remains the single derived structural artifact. Relations are metadata
on source-target graph edges, not a separate canonical ontology file.

Conceptual flow:

```text
notes/foo.md
  &depends_on [[bar]]

pkm index
  ->
.pkm/graph.json
  edge foo -> bar:
    type: wikilink
    relations:
      - type: depends_on
        reason: ...
        source:
          path: notes/foo.md
          line: 42
```

If `.pkm/` is deleted, `pkm index` rebuilds relation metadata from Markdown and
relation vocabulary sources.

## Syntax And Parsing

Canonical relation markers use this pattern:

```markdown
&relation_type [[Target]]
&relation_type [[Target]] - optional reason
```

Parsing rules:

- The source is the current Markdown file.
- The target is the wikilink target.
- The relation type is the token after `&`.
- The reason is optional text after the wikilink, typically after `-`.
- A marker is canonical only when `&relation_type` is immediately followed by a
  wikilink.
- Standalone `&foo` is ignored.
- Markers are recognized across the document, not only inside `## Relations`.
- Markers from `notes/` become canonical graph relations.
- Markers from `daily/` are promotion signals and audit candidates, not
  canonical graph relations.

Reason text is recommended but not required. Missing reasons appear in audit
output as quality warnings.

## Vocabulary

Relation vocabulary has three layers:

```text
built-in vocabulary
  PKM-provided relation set in code

vault vocabulary
  vault-local custom relation set defined in Markdown

observed vocabulary
  relation types found in notes/daily but not yet built-in or vault-defined
```

The built-in vocabulary should cover common durable-knowledge relations, for
example:

- `is_a`
- `part_of`
- `depends_on`
- `enables`
- `contrasts_with`
- `supersedes`
- `instance_of`
- `related`
- `source`

Unknown relation types are not errors. They are observed vocabulary. Audit
classifies them as likely typo candidates, synonym candidates, vault vocabulary
promotion candidates, or low-frequency noise.

Vault vocabulary is canonical in Markdown so it travels with the vault. `.pkm/`
may cache parsed vocabulary and usage stats, but it is not the source of truth.

## Graph Integration

`pkm index` remains the rebuild path for graph-like derived structure. It parses
normal wikilinks, tags, and relation markers in one coordinated pipeline.

Derived outputs:

```text
.pkm/graph.json
  Structural graph:
  - nodes for notes, daily notes, tags, unresolved wikilink targets
  - normal wikilink/tag edges
  - relation metadata merged into source-target edges

.pkm/graph_enriched.json
  Enriched graph:
  - graph.json contents
  - semantic_similar edges
  - clusters, centroids, hub metadata

.pkm/relations-vocabulary.json
  Derived cache of built-in + vault vocabulary + observed usage stats

.pkm/relations-audit.json
  Derived audit report for relation quality and promotion candidates
```

Edge model:

```json
{
  "source": "foo",
  "target": "bar",
  "type": "wikilink",
  "relations": [
    {
      "type": "depends_on",
      "reason": "semantic search requires indexed embeddings",
      "source": {
        "path": "notes/foo.md",
        "line": 42
      }
    }
  ]
}
```

If a normal `[[bar]]` link and `&depends_on [[bar]]` both exist, they collapse
into the same source-target edge. If only `&depends_on [[bar]]` exists, it still
creates a source-target edge because the marker contains a wikilink.

Multiple relations between the same source and target are allowed and stored in
the `relations` array. Audit should flag them as review candidates because they
may indicate a fuzzy relation, vocabulary issue, or note boundary problem.

Terminology:

- Product, CLI, file, and schema terminology uses **relations**.
- **Ontology** appears only in guidance as a methodology for using relations to
  build a durable knowledge system.

## Command Surface

The user-facing command group should be `pkm relations`, parallel to `pkm tags`.

Initial commands:

```bash
pkm relations
pkm relations show <relation>
pkm relations observed
pkm relations audit
pkm relations promote <relation>
```

Expected behavior:

- `pkm relations`: list built-in, vault-defined, and observed relations with
  usage counts.
- `pkm relations show <relation>`: show definition, aliases/synonyms, examples,
  usage locations, common targets, and common sources.
- `pkm relations observed`: list relation markers found in Markdown but not yet
  built-in or vault-defined.
- `pkm relations audit`: report unknown relations, missing reasons, broken
  targets, daily promotion signals, and suspicious multi-relation edges.
- `pkm relations promote <relation>`: add an observed relation to the vault
  vocabulary Markdown note.

This command surface replaces the earlier `pkm ontology audit` idea. The audit
operation belongs under `pkm relations`.

## Agent Workflow

Agents should be able to inspect available relation vocabulary before writing
relation markers. That can start with CLI guidance and later become an MCP or
worker tool.

Agent rules:

- Prefer built-in or vault-defined relation types when a close match exists.
- Observed relation types are allowed, but should be treated as vocabulary
  candidates rather than silently accepted as best practice.
- Include a reason when writing a relation marker unless the relation is
  self-evident.
- Never treat daily relation markers as canonical graph relations.
- Do not infer canonical relations from LLM output unless the relation is
  written back into Markdown as `&relation [[Target]]`.

## Audit Behavior

`pkm relations audit` reports quality issues without blocking writes.

Audit categories:

- malformed relation markers
- missing reasons
- broken or unresolved relation targets
- observed relation types not in built-in or vault vocabulary
- likely typos or near-duplicate relation names
- low-frequency relation types that may be noise
- multiple relation types for one source-target pair
- relation markers in `daily/` that may indicate promotion candidates
- notes whose relation usage conflicts with the daily/notes durability policy

Malformed markers are ignored by graph extraction but listed in audit output.
Broken relation targets become unresolved graph nodes following current graph
behavior and also appear in relation audit.

## Testing Strategy

Parser tests:

- valid markers with and without reasons
- unknown relation types
- multiple relations for one source-target pair
- wikilinks with aliases
- ignored standalone `&foo`
- malformed markers reported to audit

Graph build tests:

- relation metadata merges onto existing source-target edges
- relation-only markers still create graph edges
- multiple relations are stored and audited
- deleting `.pkm/` and rerunning `pkm index` restores relation metadata from
  Markdown

Daily boundary tests:

- daily relation markers become audit promotion candidates
- daily relation markers do not become canonical graph relations

Vocabulary tests:

- built-in relation vocabulary loads from code
- vault vocabulary loads from Markdown
- observed vocabulary is derived from scanned markers
- promoted relations are written to the vault vocabulary Markdown note

CLI tests:

- `pkm relations`
- `pkm relations show <relation>`
- `pkm relations observed`
- `pkm relations audit`
- `pkm relations promote <relation>`

## Open Implementation Notes

- The default vault vocabulary note path is `notes/pkm-relation-vocabulary.md`.
  It should be a normal Markdown note with `type: index` frontmatter and a
  durable description so Obsidian users can read and edit it directly.
- The first implementation scope is CLI and index integration. MCP/worker
  vocabulary tooling is a follow-up, but the CLI data model should leave a
  direct path to tool parity.
- Existing graph consumers must tolerate edges with a `relations` array.
- Existing Obsidian users should not need to change existing notes unless they
  want typed relation extraction.
