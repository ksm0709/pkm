# Refine Loop — Knowledge Cleanup and Reduction Pipeline

## Purpose
Orchestrate the full knowledge cleanup and reduction pipeline: inspect vault health, repair orphans,
correct tags on weak or legacy notes, and apply prune/merge/split where strictly warranted.
This loop is strictly corrective — it improves existing knowledge; it does not promote new notes
or generate writing topics.

## Trigger
- **Primary:** "refine-loop", "knowledge cleanup", "vault refinement"
- **Secondary:** "nightly cleanup", "orphan repair", "reduce knowledge base", "full cleanup"
- **Deprecated alias:** "dream" (compatibility only; prefer `refine-loop`)

## Pipeline

```
[1/4] health-check       — detect orphans, stale notes, and tag gaps
[2/4] auto-tagging       — correct tags on weak or untagged legacy notes
[3/4] auto-linking       — reconnect weak or legacy notes that have drifted out of the graph
[4/4] prune-merge-split  — remove stale, merge near-identical, split multi-topic notes
```

## Ownership Boundaries

**refine-loop owns:**
- Orphan repair: reconnect legacy notes that have drifted out of the knowledge graph
- Tag correction: retag weak or legacy notes whose tags no longer reflect their content
- Stale inspection: surface notes that have not been updated and may need review or deletion
- Prune, merge, and split operations under strict criteria (see below)

**refine-loop does NOT own:**
- Daily-to-knowledge promotion (→ `zettel-loop`)
- Tagging or linking newly promoted notes (→ `zettel-loop`)
- Structure-note creation as a production goal (→ `zettel-loop`)
- Writing-topic generation or brainstorming (out of scope for both loops)

## Strict Destructive Operation Criteria

These criteria are intentionally stricter than generic similarity thresholds:

### Merge — only when:
- Two notes have effectively identical claims AND effectively identical link neighborhoods
- They would be indistinguishable to a future reader seeking either one
- Not merely similar topic or overlapping tags — the content itself must be redundant

### Split — only when:
- A single note contains two or more independently reusable concepts
- Each concept can stand alone without referencing the other
- Not merely long notes — length alone is not a criterion

### Delete (Prune) — only when:
- The note is empty, or every unique claim has been fully absorbed into another note
- The note has zero unique information that does not exist elsewhere
- Deletion requires explicit user confirmation; this loop lists candidates, does not auto-delete

## Tools
- `pkm orphans` (notes with no connections)
- `pkm stale` / `pkm note stale` (unmodified notes)
- `pkm tags`, `pkm search`
- Read, Edit, Glob
- (For tools specific to each step, refer to the corresponding sub-workflow)

## Principles
- Each step runs independently — a failure in one step does not halt the entire pipeline
- After completion, a per-step result summary must be printed (✓/⚠/✗)
- Note modifications are performed automatically except deletion (requires user confirmation)
- **Today's daily is never modified, marked, or cleaned up under any circumstances**
- Destructive operations use the strict criteria above, not generic similarity thresholds

## Execution Protocol

Each step is executed in order. On failure:
1. Capture the error message and include it in the final summary
2. Continue to the next step
3. Print a consolidated summary after all steps complete

## Step References

| Step | Workflow | Description |
|------|----------|-------------|
| 1 | `workflows/health-check.md` | Detect and report orphan, stale, and tag-gap notes |
| 2 | `workflows/auto-tagging.md` | Correct tags on weak or legacy untagged notes |
| 3 | `workflows/auto-linking.md` | Reconnect or retag notes that have drifted from the graph |
| 4 | `workflows/prune-merge-split.md` | Remove stale, merge near-identical, split multi-topic notes |

## Example Flow

```
/pkm:refine-loop triggered

[1/4] health-check...
  → workflows/health-check.md executed
  → 2 orphans, 3 stale, 5 untagged found ✓

[2/4] auto-tagging...
  → workflows/auto-tagging.md executed
  → 5 legacy notes retagged ✓

[3/4] auto-linking...
  → workflows/auto-linking.md executed
  → 4 orphan notes reconnected ✓

[4/4] prune-merge-split...
  → workflows/prune-merge-split.md executed
  → 2 prune candidates listed (awaiting user confirmation)
  → 1 pair merged, 1 note split ✓

✅ refine-loop complete
  [1] health-check:      ✓ 2 orphans, 3 stale reported
  [2] auto-tagging:      ✓ 5 notes retagged
  [3] auto-linking:      ✓ 4 notes reconnected
  [4] prune-merge-split: ✓ 1 merged, 1 split; 2 prune candidates listed
```

## Edge Cases
- No orphans found: report "no orphan notes detected" then proceed to next step
- No stale notes: report "no stale notes found" then proceed
- All steps fail: print each error summary then guide the user to run individual workflows manually
- No step has any work to do: report "vault is clean — no refinement targets found"

## Expected Output
- ✓/⚠/✗ result per step
- Count of items modified/repaired/listed
- Error messages for failed steps (if any)
- Prune candidate list (for user confirmation before any deletion)
- Total elapsed time (optional)
