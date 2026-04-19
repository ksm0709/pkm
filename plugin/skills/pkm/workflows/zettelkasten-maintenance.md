# Zettelkasten Maintenance Workflow

## Purpose
Execute the daily Zettelkasten maintenance routine to ensure knowledge graph health, connect isolated thoughts, and refine notes. This workflow is designed to be executed autonomously by the `pkm daemon` in the background.

## Trigger
- Scheduled execution by `pkm daemon` at 2 AM daily.
- Manually via `pkm ask "run zettelkasten maintenance"` (though currently handled strictly by the daemon scheduler).

## Expected Output
A fully maintained vault with:
- Consolidated daily insights
- Cleanly split/merged notes
- Newly discovered semantic and graph-based links between notes
- No orphaned or stale temporary notes

## Sequence of Operations

1. **Daily Note Distillation**
   - Read recent daily logs (`Y-M-D.md`).
   - Extract recurring themes, ideas, or completed tasks.
   - Promote valuable insights into new atomic notes (`pkm note add`).

2. **Graph Refinement (Split & Merge)**
   - Identify excessively large atomic notes that cover multiple topics and split them into smaller, focused notes.
   - Identify highly similar notes and merge them.

3. **Auto-Linking**
   - Perform semantic searches (`pkm search`) to find related notes that are not currently linked via `[[wikilinks]]`.
   - Update notes (`pkm note update`) to add missing `[[wikilinks]]` in the "Related" section.

4. **Health Check & Cleanup**
   - Identify orphaned notes (notes with no incoming or outgoing links) and either link them or flag them.
   - Clean up stale, empty, or temporary notes.

## Principles
- **Atomicity**: One idea per note.
- **Connectivity**: No note should be an island.
- **Safety First**: Do not delete content unless it is safely merged into another note.

## Tools Required
- `read_note`
- `update_note`
- `add_note`
- `search_notes`
- `semantic_search`
- `read_daily_log`
