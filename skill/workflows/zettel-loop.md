# Zettel Loop — Knowledge Production Pipeline

## Purpose
Orchestrate the full knowledge production pipeline: from marked daily notes through promotion,
linking, and tagging into the knowledge graph. This loop is strictly additive — it creates and
connects knowledge; it never merges, splits, or deletes notes.

## Trigger
- **Primary:** "zettel-loop", "knowledge production", "promote knowledge"
- **Secondary:** "distill and link", "nightly production", "promote and connect"

## Pipeline

```
[1/4] consolidate    — identify and mark daily notes ready for promotion
[2/4] distill-daily  — promote marked dailies → permanent knowledge notes
[3/4] auto-linking   — add wikilinks to newly promoted and disconnected notes
[4/4] auto-tagging   — add tags to newly promoted and untagged notes
```

## Ownership Boundaries

**zettel-loop owns:**
- Promoting daily captures to atomic notes
- Adding wikilinks to newly promoted notes so they enter the graph correctly
- Tagging newly promoted notes so they are discoverable
- Creating structure notes (topic overviews, indexes) where a cluster needs one

**zettel-loop does NOT own:**
- Merge: combining existing notes (→ `refine-loop`)
- Split: decomposing existing notes (→ `refine-loop`)
- Delete: removing stale or absorbed notes (→ `refine-loop`)
- Orphan repair on legacy notes (→ `refine-loop`)

`consolidate` is the staging step for `zettel-loop`. It identifies and marks daily notes that are
ready for promotion; the rest of the pipeline then acts on those marks.

## Tools
- `pkm consolidate` / `pkm consolidate mark`
- `pkm note add`, `pkm search`, `pkm orphans`
- Read, Edit, Glob
- (For tools specific to each step, refer to the corresponding sub-workflow)

## Principles
- Each step runs independently — a failure in one step does not halt the entire pipeline
- After completion, a per-step result summary must be printed (✓/⚠/✗)
- Note modifications are performed automatically (no user approval required)
- **Today's daily is never modified or marked under any circumstances**
- No destructive operations: this loop only adds knowledge to the graph

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
| 3 | `workflows/auto-linking.md` | Add wikilinks to newly promoted and disconnected notes |
| 4 | `workflows/auto-tagging.md` | Tag newly promoted and untagged notes |

## Example Flow

```
/pkm:zettel-loop triggered

[1/4] consolidate...
  → workflows/consolidate.md executed
  → 4 dailies marked ✓

[2/4] distill-daily...
  → workflows/distill-daily.md executed
  → 3 permanent notes created ✓

[3/4] auto-linking...
  → workflows/auto-linking.md executed
  → 7 wikilinks added ✓

[4/4] auto-tagging...
  → workflows/auto-tagging.md executed
  → 5 notes tagged ✓

✅ zettel-loop complete
  [1] consolidate:    ✓ 4 dailies marked
  [2] distill-daily:  ✓ 3 notes created
  [3] auto-linking:   ✓ 7 links added
  [4] auto-tagging:   ✓ 5 notes tagged
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
