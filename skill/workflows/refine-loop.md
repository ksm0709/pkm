# Refine Loop — Knowledge Cleanup Orchestrator

## Purpose
Run the canonical batch workflow for repairing weak, stale, duplicated, or overly broad notes. This loop cleans and reduces knowledge that has drifted out of quality bounds.

## Trigger
- **Primary:** "refine-loop"
- **Secondary:** "refine", "cleanup loop", "note cleanup", "knowledge cleanup"

## Pipeline

```
[1/4] auto-linking      — reconnect weak or orphaned notes
[2/4] auto-tagging      — correct missing or drifted tags
[3/4] health-check      — measure orphan/stale/untagged state
[4/4] prune-merge-split — reduce weak knowledge under strict criteria
```

## Tools
- `pkm note links`, `pkm note show`, `pkm note orphans`
- `pkm tags`, `pkm tags show`, `pkm search`
- `pkm stats`, `pkm note stale --days 30`
- Read, Edit, Write, Glob

## Principles
- Refinement reduces or repairs weak knowledge; it does not generate new writing topics
- Destructive actions require strict criteria and must stay more conservative than the production loop
- Tag and link fixes here apply to weak or legacy notes, not newly promoted notes
- Today's daily is never modified, merged, split, or deleted

## Strict Refine Criteria
- **Merge**: only when notes differ mainly in title or form, but their core claim and link neighborhood are effectively the same
- **Split**: only when one note mixes 2 or more independently reusable concepts
- **Delete/Prune**: only when a note is empty, or fully absorbed elsewhere with zero unique information remaining
- **Rewrite**: always allowed for wording, explanation, link strengthening, and tag correction

## Execution Protocol

Each step is executed in order. On failure:
1. Capture the error message and include it in the final summary
2. Continue to the next step if the failure is local
3. Stop only if a destructive operation can no longer be evaluated safely

## Step References

| Step | Workflow | Description |
|------|----------|-------------|
| 1 | `workflows/auto-linking.md` | Reconnect orphaned or weak notes |
| 2 | `workflows/auto-tagging.md` | Correct missing or drifted tags on existing notes |
| 3 | `workflows/health-check.md` | Report overall vault health before reduction |
| 4 | `workflows/prune-merge-split.md` | Apply pruning, merge, and split rules conservatively |

## Example Flow

```
/pkm:refine-loop triggered

[1/4] auto-linking...
  → workflows/auto-linking.md executed
  → 5 orphan notes reconnected ✓

[2/4] auto-tagging...
  → workflows/auto-tagging.md executed
  → 9 stale notes retagged ✓

[3/4] health-check...
  → workflows/health-check.md executed
  → orphan and stale ratios measured ✓

[4/4] prune-merge-split...
  → workflows/prune-merge-split.md executed
  → 1 note merged, 1 note split, 2 prune candidates reported ✓

✅ refine-loop complete
  [1] auto-linking:      ✓ 5 notes reconnected
  [2] auto-tagging:      ✓ 9 notes retagged
  [3] health-check:      ✓ diagnostics generated
  [4] prune-merge-split: ✓ 1 merge, 1 split, 2 prune candidates
```

## Edge Cases
- No orphan or stale notes: report "nothing to refine — note graph already healthy"
- Candidate for deletion still has unique information: downgrade to rewrite or redirect instead of deleting
- Similar notes share a topic but not the same claim: do not merge them
- A large note is broad but still one reusable concept: do not split it

## Expected Output
- ✓/⚠/✗ result per step
- Count of notes reconnected, retagged, merged, split, and flagged for prune
- Error messages for failed steps
- Remaining manual-review candidates, especially around deletion
