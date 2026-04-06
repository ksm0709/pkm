# Daily Seed — Morning Startup

## Purpose
Create today's daily note and prepare a startup context that includes carry-over TODOs and working memory from yesterday.

## Trigger
- **Primary:** "start today"
- **Secondary:** "daily seed", "morning startup", "today's daily", "start daily"

## Tools
- Read (yesterday's daily note and sub-notes)
- `pkm daily` (create today's daily and display all sub-notes)
- `pkm daily edit` (edit today's daily note)
- `pkm daily edit --sub` (create and edit sub-notes)
- `pkm daily todo` (add carry-over TODOs)

## Principles
- Carry over only yesterday's incomplete items — do not bring completed items forward
- If today's daily already exists, only add sections rather than overwriting
- If a carry-over item has been incomplete for 3 consecutive days, add a "#stale-todo" marker

## Sub-Notes
Daily notes now support sub-notes. Sub-notes are stored with the pattern `daily/YYYY-MM-DD-{title}.md`, and the `pkm daily` command displays all sub-notes sequentially alongside the main note. When reading yesterday's context, also check `YYYY-MM-DD-*.md` files in the `daily/` directory.

## Edge Cases
- If yesterday's daily does not exist, find the most recent daily and carry over from there
- If `pkm daily` fails, create today's file directly with Write
- After a weekend or holiday, carry over starting from the Friday daily

## Example Flow
```
User: "start today"

1. Confirm today's date: 2026-04-05 (Sunday)
   → Reference Friday's 2026-04-03 daily

2. Read `daily/2026-04-03.md` → extract the ## TODO section
   Incomplete: "- [ ] Write API documentation"
               "- [ ] Review deployment script"  (2 days in a row)
   Complete:   "- [x] Code review"

   Check sub-notes: also read `daily/2026-04-03-*.md` files

3. `pkm daily` → create `daily/2026-04-05.md` (or confirm it exists)
   Display main note and all sub-notes sequentially

4. `pkm daily todo` or Edit to add carry-over section:
   ## TODO
   - [ ] Write API documentation (carried over: 04-03)
   - [ ] Review deployment script (carried over: 04-03, ⚠️ day 2)

5. Suggest linking the working-memory workflow
```

## Expected Output
- File path of today's daily (created or confirmed)
- List of carried-over TODOs (with carry-over date)
- Warning list of long-overdue items (3+ days)
