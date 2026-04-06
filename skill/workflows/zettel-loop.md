# Zettel Loop — Knowledge Production Orchestrator

## Purpose
Run the canonical batch workflow for turning consolidated daily captures into connected, reusable knowledge notes. This loop extracts new knowledge, integrates it into the note graph, and creates structure notes when clusters become strong enough.

## Trigger
- **Primary:** "zettel-loop"
- **Secondary:** "zettel", "knowledge loop", "knowledge production", "promote and connect"

## Pipeline

```
[1/5] consolidate       — stage eligible dailies for promotion
[2/5] distill-daily     — promote daily → durable notes
[3/5] auto-linking      — connect newly promoted notes into the graph
[4/5] auto-tagging      — normalize tags on newly promoted notes
[5/5] structure-pass    — create or update structure notes when note clusters emerge
```

## Tools
- `pkm consolidate` / `pkm consolidate mark`
- `pkm note add`, `pkm search`, `pkm note show`, `pkm note links`
- `pkm note orphans`, `pkm tags show`
- Read, Edit, Write, Glob

## Principles
- Production only: create, connect, and clarify knowledge, but do not merge, split, or delete notes
- Newly promoted notes must be linked and tagged before the loop is considered complete
- Structure notes are created only when a meaningful cluster emerges; they are not generic tag indexes
- Today's daily is never modified or marked

## Execution Protocol

Each step is executed in order. On failure:
1. Capture the error message and include it in the final summary
2. Continue to the next step when the failure is local to that step
3. Stop only if the workflow can no longer promote or connect notes safely

## Step References

| Step | Workflow | Description |
|------|----------|-------------|
| 1 | `workflows/consolidate.md` | Stage daily notes that are ready for promotion |
| 2 | `workflows/distill-daily.md` | Promote daily captures into durable notes |
| 3 | `workflows/auto-linking.md` | Add wikilinks so new notes enter the graph |
| 4 | `workflows/auto-tagging.md` | Correct and normalize tags for newly promoted notes |
| 5 | structure-pass | Create or update authored structure notes for dense note clusters |

## Structure-Pass Rules

- Consider a structure note when 4+ notes repeatedly cluster around one topic
- Each linked note in a structure note must include one line explaining why it belongs
- Structure notes are maps for writing and navigation, not just tag dumps
- Structure note creation is allowed here because it increases the usability of newly created knowledge

## Example Flow

```
/pkm:zettel-loop triggered

[1/5] consolidate...
  → workflows/consolidate.md executed
  → 4 dailies marked ✓

[2/5] distill-daily...
  → workflows/distill-daily.md executed
  → 3 durable notes created ✓

[3/5] auto-linking...
  → workflows/auto-linking.md executed
  → 6 wikilinks added to new notes ✓

[4/5] auto-tagging...
  → workflows/auto-tagging.md executed
  → 3 promoted notes retagged ✓

[5/5] structure-pass...
  → 1 structure note created for recurring workflow notes ✓

✅ zettel-loop complete
  [1] consolidate:    ✓ 4 dailies marked
  [2] distill-daily:  ✓ 3 notes created
  [3] auto-linking:   ✓ 6 links added
  [4] auto-tagging:   ✓ 3 notes normalized
  [5] structure-pass: ✓ 1 structure note created
```

## Edge Cases
- No consolidate targets: report "no unconsolidated dailies to stage" and continue to distillation
- No promotion candidates: report "no knowledge to promote" and skip linking/tagging on absent notes
- No structure-note candidate: report "no cluster strong enough for a structure note"
- If linking finds no valid neighbor, keep at least a source link to the originating daily and report it

## Expected Output
- ✓/⚠/✗ result per step
- Count of notes created, links added, tags corrected, and structure notes created
- Error messages for failed steps
- Remaining notes that still need manual judgment
