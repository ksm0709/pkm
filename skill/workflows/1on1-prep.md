# 1:1 Meeting Preparation

## Purpose
Collect relevant notes and generate an agenda draft before a 1:1 meeting with a specific person.

## Trigger
- **Primary:** "1:1 prep"
- **Secondary:** "meeting prep", "1on1", "one-on-one prep"

## Tools
- Grep (search related notes by person name or tag)
- Read (review related note contents)
- `pkm search` (keyword search)

## Principles
- Search by the person's name or tag first; if no results, expand to project or team name
- Separate open items (action items) from praise/feedback points
- Compress the agenda to 5 items or fewer

## Edge Cases
- If no search results, Grep the person's name directly from daily notes
- If this is a first 1:1, suggest a "first-meeting agenda" template (introduction, expectations, collaboration style)
- If the last 1:1 note is more than 30 days old, display a "stale context" warning

## Example Flow
```
User: "Prep 1:1 with Kim Minjun"

1. Grep `notes/` for "Kim Minjun" → collect related note list
2. `pkm search "Kim Minjun"` → additional search
3. Grep `daily/` for "Kim Minjun" → collect recent daily mentions
4. Read 3-5 related notes
5. Extract open action items
6. Extract praise/feedback points
7. Generate agenda draft
```

## Expected Output
```markdown
## Kim Minjun 1:1 Agenda — 2026-04-05

### Open Action Items
- [ ] Deliver API documentation review feedback (promised last week)
- [ ] Share onboarding checklist

### Discussion Points
1. Q2 goal alignment
2. Check current blockers
3. Collaboration improvement suggestions

### Praise/Feedback
- Improved code review response time — mention this

### Reference Notes
- [[KimMinjun-1on1-2026-03-22]]
- [[Project-Alpha-Status]]
```
