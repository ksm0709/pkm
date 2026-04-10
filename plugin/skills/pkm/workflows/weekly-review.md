# Weekly Review

## Purpose
Summarize the week's activity into statistics, anomalies, and action items to set the direction for the next week.

## Trigger
- **Primary:** "weekly review"
- **Secondary:** "weekly review", "this week's summary", "weekly summary"

## Tools
- `pkm stats` (note count, creation/modification statistics)
- `pkm orphans` (list of orphan notes)
- `pkm stale` (list of stale notes)
- Read (`daily/YYYY-MM-DD.md` — last 7 days)

## Principles
- Measure before judging — interpret only after seeing the numbers
- Limit action items to 3 or fewer (more than that and they won't get done)
- Check whether last week's action items were completed first

## Edge Cases
- If `pkm stats` returns empty results, count files directly with Glob
- If there are fewer than 3 daily notes, include a "insufficient records" warning
- If `pkm stale` returns more than 20 results, show only the top 5 and summarize the rest

## Example Flow
1. Read the last 7 daily notes (`daily/2026-03-30.md` ~ `daily/2026-04-05.md`)
2. Run `pkm stats` → check number of notes created and modified
3. Run `pkm orphans` → check orphan note count and list
4. Run `pkm stale` → check notes not modified in 30+ days
5. Tally recurring keywords, completed tasks, and incomplete tasks from dailies
6. Identify anomalies (e.g., sudden spike in a topic, surge in orphan notes)
7. Write the weekly summary

## Expected Output
```
## Weekly Review — 2026-W14

### Statistics
- New notes: 5
- Modified notes: 12
- Orphan notes: 3 (↑1)
- Stale notes: 8

### Anomalies
- 3 new notes related to "async patterns" → cluster forming

### Action Items
1. Link 3 orphan notes (run extract-note-from-daily workflow)
2. Review "React hook patterns" among stale notes
3. Prepare for next week's 1:1 (1on1-prep workflow)
```
