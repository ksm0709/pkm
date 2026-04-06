# Distill Daily — Daily-to-Knowledge Promotion

> **Prerequisites:** Run `pkm consolidate` to review candidates, then mark them ready with `pkm consolidate mark YYYY-MM-DD` before running this workflow. Only dailies with `consolidated: true` set will be processed. See `workflows/consolidate.md` for details.
>
> **When run from dream:** automatically called as step 2. This workflow can also be run standalone.

## Purpose
Discover insights from marked daily notes that appear repeatedly or have driven behavioral change, and promote them to permanent knowledge notes.

## Trigger
- **Primary:** "distill", "distill daily", "promote daily"
- **Secondary:** "extract insights", "daily to notes", "knowledge promotion"

## Tools
- Read (`daily/*.md` — last 7 days, only files with `consolidated: true`)
- `pkm note add` (create new knowledge notes)
- `pkm search` (check for duplicates among existing notes)
- Edit (add wikilinks)
- `pkm orphans` (detect orphan notes)

## Principles
- Only promote insights that appear repeatedly or have driven behavioral change
- If a duplicate exists among current notes, enrich the existing note instead of creating a new one
- After promotion, leave a `→ [[note name]]` link in the original daily

## Example Flow

1. Run `pkm consolidate` → review list of dailies with `consolidated: true`
2. Skip any daily without `consolidated: true`
3. Read `daily/2026-03-30.md` through `daily/2026-04-05.md` (unconsolidated entries only)
4. Identify recurring keywords and patterns → compile candidate list
   - Example: "async error handling pattern" mentioned 3 days in a row
5. `pkm search "async error"` → check for existing notes
6. If none found, run `pkm note add "Async Error Handling Pattern"`
7. Use Edit to add wikilinks to related notes (`→ [[note name]]`)
8. Run `pkm orphans` → confirm new note is not an orphan
9. Run `pkm consolidate mark {date}` → mark each processed daily as consolidated

## Edge Cases
- If no `consolidated: true` daily exists in the last 7 days, expand the range to 14 days and notify the user
- If `pkm note add` fails, create the file directly using the Write tool
- If there are 0 promotion candidates, return "no insights to promote" summary and exit

## Expected Output
- List of promoted notes (title, path)
- List of newly added wikilinks
- Count of remaining orphan notes
