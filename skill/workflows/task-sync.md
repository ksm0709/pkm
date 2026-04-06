# Task Sync — Task Synchronization

## Purpose
Synchronize TODO items from daily notes with `tasks/ongoing.md` to maintain consistent task tracking.

## Trigger
- **Primary:** "task sync"
- **Secondary:** "task synchronization", "todo sync", "ongoing update"

## Tools
- Read (`tasks/ongoing.md`)
- Grep (extract TODO sections from `daily/*.md`)
- Edit (update `tasks/ongoing.md`)

## Principles
- Daily TODOs are the source of truth; ongoing.md is the aggregated view
- Completed items are moved to a "completed this week" section in ongoing.md
- New items are classified as WIP or TODO after user confirmation

## Edge Cases
- If `tasks/ongoing.md` does not exist, create it fresh from the CLAUDE.md template
- Skip dates with no daily TODOs
- For duplicate items, keep the one with the most recent date and remove the rest

## Example Flow
```
1. Read `tasks/ongoing.md` → understand current WIP/TODO list

2. Grep `daily/` for "## TODO" → collect TODOs from the last 7 days
   Found: "- [ ] Write API documentation" (2026-04-03)
          "- [x] Code review complete" (2026-04-04)
          "- [ ] Review deployment script" (2026-04-05)

3. Compare:
   - "Write API documentation" → not in ongoing WIP → suggest adding
   - "Code review complete" → in ongoing WIP → move to completed
   - "Review deployment script" → new → suggest adding as TODO

4. Edit `tasks/ongoing.md` after user confirmation
```

## Expected Output
- Updated `tasks/ongoing.md` (WIP/TODO/completed sections refreshed)
- Change summary:
  - Moved to completed: N items
  - Newly added: N items
  - Duplicates removed: N items
