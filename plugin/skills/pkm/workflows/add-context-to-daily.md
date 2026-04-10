# Working Memory — Context Preservation

## Purpose
Record the context of an in-progress project in today's daily note to preserve working memory across sessions.

## Trigger
- **Primary:** "working memory"
- **Secondary:** "preserve context", "working context", "working memory"

## Tools
- `pkm search` (explore in-progress project notes)
- Read (in-progress project notes)
- `pkm daily add` (add a section to today's daily)
- `pkm daily add --sub <title>` (create a dedicated sub-note and log [[wikilink]] in today's daily)
- `pkm daily edit --sub <title>` (create/open sub-note in editor)

## Principles
- Record only what matters right now — not the full project documentation
- The three core items are "how far along", "next steps", and "blockers"
- Add to the daily without overwriting existing content

## Edge Cases
- If `pkm search` returns empty results, read WIP items from `tasks/ongoing.md`
- If there are no in-progress projects, output "no active projects" and exit
- If `pkm daily add` fails, Read today's daily file first and add directly with Edit

## Example Flow
```
User: "save working memory"

1. Read `tasks/ongoing.md` → check WIP items
   e.g., "Project-Alpha API integration"

2. `pkm search "Project-Alpha"` → explore related notes
   Result: "notes/2026-04-03-project-alpha-design.md"

3. Read that note → understand current status
   - How far: "Auth module complete, data layer in progress"
   - Next steps: "Implement Repository pattern"
   - Blockers: "Waiting for DB schema finalization"

4a. Quick log: `pkm daily add` or Edit today's daily:
    ## Working Memory
    - Project: [[project-alpha-api-integration]]
    - How far: auth complete, data layer in progress
    - Next: implement Repository pattern
    - Blockers: waiting for DB schema finalization

4b. Sub-note (for extended context): `pkm daily add --sub project-alpha`
    → Creates `daily/YYYY-MM-DD-project-alpha.md` with full context
    → Logs `- [HH:MM] Sub note added: [[YYYY-MM-DD-project-alpha]]` in today's daily
```

## Expected Output
`## Working Memory` section added to today's daily note:
- Project name (wikilink)
- Current progress status
- Next steps
- Blockers (if any)
