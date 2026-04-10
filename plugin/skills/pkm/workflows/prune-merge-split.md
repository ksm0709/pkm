# Prune-Merge-Split — Note Refinement

> **When run from refine-loop:** automatically called as step 4. This workflow can also be run standalone.

## Purpose
Maintain note quality in the knowledge base:
- **Prune**: remove notes that are empty or fully absorbed elsewhere
- **Merge**: consolidate note pairs with the same claim and link neighborhood
- **Split**: decompose notes covering multiple independently reusable concepts into atomic notes

## Trigger
- **Primary:** "prune", "merge", "split", "refine", "prune-merge-split"
- **Secondary:** "dedup", "note merge", "note split", "atomize", "remove stale"

## Tools
- `pkm search` (find similar notes)
- `pkm orphans` (notes with no connections)
- Read, Edit, Write, Glob

## Principles
- **Prune criteria**: last modified 6+ months ago AND zero incoming links AND zero unique information
  not already present in another note — length or age alone is insufficient
- **Merge criteria**: two notes have effectively identical claims AND effectively identical
  link neighborhoods; they would be indistinguishable to a future reader — similarity score alone
  (e.g. 80%) is insufficient; content redundancy must be confirmed by reading both notes
- **Split criteria**: a note contains two or more independently reusable concepts that can each
  stand alone without referencing the other — length alone is not a criterion
- Prune (deletion): report candidates only — actual deletion requires explicit user confirmation
- Merge and Split: performed automatically (original content preserved before changes)

## Three Operations

### 1. Prune (removal)
Identify stale candidates:
1. `pkm orphans` → list notes with no links
2. Confirm the note is empty or fully absorbed elsewhere with zero unique information remaining
3. Report candidates (in refine-loop: list only / standalone: prompt for deletion confirmation)

### 2. Merge (consolidation)
Consolidate duplicate notes:
1. Identify similar note pairs using `pkm search` + Read
2. Confirm the pair shares the same core claim and link neighborhood, not just topic overlap
3. Merge content into the more complete note
4. Replace merged note with a `→ [[consolidated note name]]` redirect wikilink

### 3. Split (decomposition / atomization)
Decompose large notes:
1. Analyze note structure with Read → identify independently reusable concepts
2. Create new atomic note for each topic (`pkm note add` or Write)
3. Convert original note into a table of contents / link collection

## Example Flow

```
1. pkm orphans → ["old-scratch-2023.md", "temp-note.md"]
2. Confirm "old-scratch-2023.md" has no unique information left → Prune candidate
3. pkm search + Read → "perf-metrics.md" ↔ "benchmark-records.md" share the same claim and neighbors → Merge
4. Read "docker-setup-and-deploy.md" → 2 topics found → Split
   → create "docker-setup.md" + "docker-deploy.md"
   → convert original to a link list pointing to both notes

Report:
  Prune candidates: 1 (pending deletion under strict criteria)
  Merged: 1 pair (perf-metrics ← benchmark-records)
  Split: 1 (docker-setup-and-deploy → 2 notes)
```

## Edge Cases
- If no candidates found: report "no notes to refine — knowledge base is healthy"
- If notes are similar but do not share the same claim, do not merge them
- If original deletion fails after Merge: add redirect wikilink only and continue
- If new filename conflicts during Split: append date suffix (`note-name-2026-04.md`)

## Expected Output
- **Prune**: N candidates (list), N deleted
- **Merge**: N pairs merged
- **Split**: N notes split (list of created files)
- Full list of changed files
