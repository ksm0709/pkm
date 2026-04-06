# Dream — Nightly Knowledge Consolidation

## Purpose
Automatically runs the full nightly knowledge consolidation pipeline, from daily notes to knowledge base refinement.
Orchestrates 6 sub-workflows in sequence; if any step fails, it is skipped and execution continues.

## Trigger
- **Primary:** "dream"
- **Secondary:** "nightly review", "nightly consolidation", "full cleanup", "full knowledge cleanup"

## Pipeline

```
[1/6] consolidate       — mark unconsolidated dailies
[2/6] distill-daily     — promote daily → permanent notes
[3/6] auto-linking      — add wikilinks to disconnected notes
[4/6] auto-tagging      — add tags to untagged notes
[5/6] health-check      — detect and report orphan/stale notes
[6/6] prune-merge-split — remove stale, merge duplicates, split large notes
```

## Tools
- `pkm consolidate` / `pkm consolidate mark`
- `pkm note add`, `pkm search`, `pkm orphans`
- Read, Edit, Glob
- (For tools specific to each step, refer to the corresponding sub-workflow)

## Principles
- Each step runs independently — a failure in one step does not halt the entire pipeline
- After completion, a per-step result summary must be printed (✓/⚠/✗)
- Note modifications are performed automatically (no user approval required)
- Today's daily is never modified or marked under any circumstances

## Execution Protocol

Each step is executed in order. On failure:
1. Capture the error message and include it in the final summary
2. Continue to the next step
3. Print a consolidated summary after all steps complete

## Step References

| Step | Workflow | Description |
|------|----------|-------------|
| 1 | `workflows/consolidate.md` | Identify and mark unconsolidated daily candidates |
| 2 | `workflows/distill-daily.md` | Extract and promote permanent notes from marked dailies |
| 3 | `workflows/auto-linking.md` | Add wikilinks between disconnected note pairs |
| 4 | `workflows/auto-tagging.md` | Auto-tag untagged notes |
| 5 | `workflows/health-check.md` | Detect and report orphan and stale notes |
| 6 | `workflows/prune-merge-split.md` | Remove stale, merge duplicates, split large notes |

## Example Flow

```
/pkm:dream triggered

[1/6] consolidate...
  → workflows/consolidate.md executed
  → 4 dailies marked ✓

[2/6] distill-daily...
  → workflows/distill-daily.md executed
  → 3 permanent notes created ✓

[3/6] auto-linking...
  → workflows/auto-linking.md executed
  → 7 wikilinks added ✓

[4/6] auto-tagging...
  → workflows/auto-tagging.md executed
  → 12 notes tagged ✓

[5/6] health-check...
  → workflows/health-check.md executed
  → 2 orphans, 1 stale found ✓

[6/6] prune-merge-split...
  → workflows/prune-merge-split.md executed
  → 1 merged, 1 split ✓

✅ dream complete
  [1] consolidate:       ✓ 4 dailies marked
  [2] distill-daily:     ✓ 3 notes created
  [3] auto-linking:      ✓ 7 links added
  [4] auto-tagging:      ✓ 12 notes tagged
  [5] health-check:      ✓ 2 orphans reported
  [6] prune-merge-split: ✓ 1 merged, 1 split
```

## Edge Cases
- No consolidate targets: report "no unconsolidated dailies to mark" then proceed to step 2
- No distill-daily promotion candidates: report "no insights to promote" then proceed to step 3
- All steps fail: print each error summary then guide the user to run individual workflows manually
- No step has any work to do: report "already up to date — no targets for any step"

## Expected Output
- ✓/⚠/✗ result per step
- Count of items created/modified/found
- Error messages for failed steps (if any)
- Total elapsed time (optional)
