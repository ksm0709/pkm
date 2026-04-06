# Prune-Merge-Split — Note Refinement

> **When run from refine-loop:** automatically called as step 4. This workflow can also be run standalone.

## Purpose
Maintain note quality in the knowledge base:
- **Prune**: remove old, disconnected stale notes
- **Merge**: consolidate note pairs with duplicate content
- **Split**: decompose notes covering multiple topics into atomic notes

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
2. Check last modified date for each note → filter for 6+ months
3. Report candidates (in refine-loop: list only / standalone: prompt for deletion confirmation)

### 2. Merge (consolidation)
Consolidate duplicate notes:
1. Identify similar note pairs using `pkm search` + Read
2. Merge content into the more complete note
3. Replace merged note with a `→ [[consolidated note name]]` redirect wikilink

### 3. Split (decomposition / atomization)
Decompose large notes:
1. Analyze note structure with Read → identify independent topics
2. Create new atomic note for each topic (`pkm note add` or Write)
3. Convert original note into a table of contents / link collection

## Example Flow

```
1. pkm orphans → ["old-scratch-2023.md", "temp-note.md"]
2. Check modified date → "old-scratch-2023.md" 8 months old → Prune candidate
3. pkm search → "perf-metrics.md" ↔ "benchmark-records.md" similarity 0.87 → Merge
4. Read "docker-setup-and-deploy.md" → 2 topics found → Split
   → create "docker-setup.md" + "docker-deploy.md"
   → convert original to a link list pointing to both notes

Report:
  Prune candidates: 1 (pending deletion)
  Merged: 1 pair (perf-metrics ← benchmark-records)
  Split: 1 (docker-setup-and-deploy → 2 notes)
```

## Edge Cases
- If no candidates found: report "no notes to refine — knowledge base is healthy"
- If original deletion fails after Merge: add redirect wikilink only and continue
- If new filename conflicts during Split: append date suffix (`note-name-2026-04.md`)

## Expected Output
- **Prune**: N candidates (list), N deleted
- **Merge**: N pairs merged
- **Split**: N notes split (list of created files)
- Full list of changed files
