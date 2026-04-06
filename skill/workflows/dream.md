# Dream — Deprecated Alias for Refine Loop

## Purpose
Compatibility surface for older `dream` invocations.
Use `refine-loop` as the canonical cleanup/reduction orchestrator.

## Trigger
- **Primary:** "dream"
- **Secondary:** "nightly review", "nightly consolidation"

## Status

- Deprecated for one transition cycle
- Kept only to avoid breaking existing trigger habits
- Not a canonical workflow name anymore

## Redirect

- Canonical cleanup path: `workflows/refine-loop.md`
- Canonical production path: `workflows/zettel-loop.md`

## Principles
- Keep old invocations working, but steer users to `refine-loop`
- Do not describe `dream` as canonical in tables or docs
- Today's daily remains protected under both canonical loops

## Execution
When `dream` is triggered, execute `workflows/refine-loop.md`.

## Expected Output
- A deprecation redirect to `refine-loop`
- Compatibility for one transition cycle
