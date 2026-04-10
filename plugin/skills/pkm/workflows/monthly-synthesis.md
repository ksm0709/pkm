# Monthly Synthesis — Monthly Synthesis

## Purpose
Synthesize notes created and modified over the past month to produce a monthly synthesis note containing key themes and insights.

## Trigger
- **Primary:** "monthly synthesis"
- **Secondary:** "monthly synthesis", "monthly review", "this month's summary"

## Tools
- Glob (`notes/YYYY-MM-*.md` — this month's notes)
- Read (review monthly note contents)
- `pkm note add` (create synthesis note)

## Principles
- Extract patterns and themes rather than copying individual notes
- The synthesis note is interpretation, not an index — compress "this month's key findings" to 1–3 items
- Synthesis note filename: `YYYY-MM-synthesis.md`

## Edge Cases
- If there are fewer than 5 notes this month, warn "insufficient data" and ask the user whether to proceed
- If `pkm note add` fails, create the file directly with Write
- If a synthesis note for that month already exists, update it with Edit rather than overwriting

## Example Flow
```
User: "monthly synthesis" (as of 2026-04-05 → summarizing 2026-03)

1. Glob `notes/2026-03-*.md` → list of this month's notes
   Result: 23 files

2. Read the first paragraph + tags of each note (skip reading in full)

3. Tally tag frequency:
   #dev: 12 | #architecture: 5 | #meeting: 4 | #idea: 2

4. Identify major themes:
   - Async architecture patterns (6 notes)
   - Team onboarding process (4 notes)

5. `pkm note add "2026-03-synthesis"` → create file

6. Write the synthesis note:
   - 2–3 key findings
   - Links to notes by major theme
   - Topics to carry into next month
```

## Expected Output
`notes/2026-03-synthesis.md` file:

```markdown
---
id: 2026-03-synthesis
aliases:
  - March 2026 Synthesis
tags:
  - synthesis
  - monthly
---

# March 2026 Synthesis

## Key Findings
1. Async error handling should be separated per layer → [[async-error-handling-patterns]]
2. The onboarding checklist cut actual onboarding time by 40%

## Major Themes
### Async Architecture (6 notes)
- [[async-await-patterns]], [[error-boundary-design]], ...

### Team Onboarding (4 notes)
- [[onboarding-checklist-v2]], ...

## Topics to Carry into Next Month
- Repository pattern deep dive
- Performance monitoring setup
```
