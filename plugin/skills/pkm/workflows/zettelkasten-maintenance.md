# Zettelkasten Maintenance Workflow

## Purpose
Execute the daily Zettelkasten maintenance routine to ensure knowledge graph health, connect isolated thoughts, and refine notes. This workflow is designed to be executed autonomously by the `pkm daemon` in the background.

The workflow keeps capture and promotion separate: `daily/` stores time-bound
memory, while `notes/` stores durable wiki-style knowledge with explicit
wikilinks and typed relation markers.

## Trigger
- Scheduled execution by `pkm daemon` at 2 AM daily.
- Manually via `pkm ask "run zettelkasten maintenance"` (though currently handled strictly by the daemon scheduler).

## Expected Output
A fully maintained vault with:
- Consolidated daily insights
- Durable notes shaped as concepts, entities, processes, principles, patterns, decisions, or indexes
- Cleanly split/merged notes
- Newly discovered semantic and graph-based links between notes
- No orphaned, stale, or temporary-state notes left unhandled under `notes/`

## Sequence of Operations

1. **Daily Note Distillation**
   - Read recent daily logs (`Y-M-D.md`).
   - Extract recurring themes, ideas, decisions, reusable processes, and durable patterns.
   - Keep session state, event logs, temporary TODOs, and meeting-only facts in daily notes or daily subnotes.
   - Promote only insights that pass the promotion gate: stable definition, durable scope, at least one relation or source link, and value without today's date.

2. **Durable Knowledge Audit**
   - Check each `notes/` item for a durable knowledge type: concept, entity, process, principle, pattern, decision, or index.
   - Flag notes with no definition, no meaningful `&relation [[target]] - reason` marker or source link, or scope that depends on a specific day/task.
   - Suggest one repair action: add typed relation, add definition, merge, split, convert to index, or demote to daily/archive.

3. **Graph Refinement (Split & Merge)**
   - Identify excessively large atomic notes that cover multiple topics and split them into smaller, focused notes.
   - Identify highly similar notes and merge them.

4. **Auto-Linking And Relation Repair**
   - Perform semantic searches (`pkm search` or `semantic_search`) and inspect graph neighbors (`get_note_neighbors`, `find_surprising_connections`, `list_clusters`, `list_god_nodes`) to find related notes that are not currently linked via `[[wikilinks]]`.
   - Prefer `patch_note` for partial edits to existing notes, such as adding missing `[[wikilinks]]` or typed `&relation [[target]] - reason` markers.
   - Use full-note replacement only when intentionally rewriting the whole note after reading the current content.
   - Prefer typed relation labels where helpful: `is_a`, `part_of`, `depends_on`, `enables`, `contrasts_with`, `supersedes`, `instance_of`, `related`, or `source`.
   - Use `pkm relations audit` to review unknown relation names, missing reasons, and daily promotion candidates.

5. **Hub & Index Maintenance**
   - Use cluster and hub-note tooling to find topic clusters without a named entry point.
   - Create or update `type: index` notes for clusters that need a stable navigational hub.

6. **Health Check & Cleanup**
   - Identify orphaned notes (notes with no incoming or outgoing links) and either link them or flag them.
   - Clean up stale or empty notes.
   - Demote temporary notes from `notes/` instead of treating them as durable knowledge.

## Principles
- **Atomicity**: One idea per note.
- **Connectivity**: No note should be an island.
- **Durability**: `notes/` is for knowledge that remains useful outside the current day/task.
- **Promotion gate**: If a note cannot be defined and related, it stays in `daily/`.
- **Safety First**: Do not delete content unless it is safely merged into another note.

## Tools Required
- `read_note`
- `patch_note`
- `update_note` (full-body replacement only)
- `add_note`
- `search_notes`
- `semantic_search`
- `get_note_neighbors`
- `find_surprising_connections`
- `list_clusters`
- `list_god_nodes`
- `read_daily_log`
