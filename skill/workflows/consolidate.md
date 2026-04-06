# Consolidate Workflow

## Purpose
Identify and mark daily notes (episodic memory) that are ready for consolidation. This is the PKM equivalent of sleep consolidation — a preparation step for moving short-term episodic memories into long-term semantic storage.

## Trigger
- **Primary:** consolidate
- **Secondary:** daily consolidation, memory consolidation

## Tools
- `pkm consolidate` (list candidates — read-only)
- `pkm consolidate mark YYYY-MM-DD` (mark as ready for consolidation)
- Dream workflow (`workflows/dream.md`) — full nightly consolidation pipeline (includes distill-daily)

## Principles
- Consolidation is split into two phases: review candidates → mark. Never merge in one step, to prevent data loss
- Today's daily is always protected — never mark it
- Marking is idempotent: marking the same date twice is safe

## Two-Phase Approach

```
Phase 1 (read-only): pkm consolidate
  → print list of unconsolidated daily candidates (date, entry count)

Phase 2 (marking): pkm consolidate mark YYYY-MM-DD
  → set consolidated: true in the daily's frontmatter

Phase 3 (dream): run Dream workflow
  → extract atomic notes from consolidated: true dailies
```

## Edge Cases
- Attempting to mark today's date → returns an error (intentional protection)
- If distill-daily fails midway, `consolidated: true` is not set → safe to retry on next run
- Dailies already marked `consolidated: true` are excluded from the candidate list

## Example Flow

```bash
# 1. Review consolidation candidates (read-only, safe)
pkm consolidate
# Example output:
# 2026-04-03 — 12 entries (unconsolidated)
# 2026-04-04 — 8 entries (unconsolidated)

# 2. Mark ready dailies
pkm consolidate mark 2026-04-03
pkm consolidate mark 2026-04-04

# 3. Run distill-daily workflow after marking
# → see workflows/distill-daily.md
```

## Safety Rules
- Today's daily can never be marked (actively in use)
- Marking only sets `consolidated: true` in frontmatter (no content changes)
- If Dream fails, marking state is not persisted — safe to retry

## Expected Output
- Candidate list: date, entry count (Phase 1)
- Marking confirmation: "consolidated: true set for YYYY-MM-DD" (Phase 2)
