# Connect — Link Discovery

## Purpose
Discover semantically similar but unconnected note pairs, and add wikilinks after user approval.

## Trigger
- **Primary:** "find links"
- **Secondary:** "suggest links", "connect notes", "connect orphans"

## Tools
- `pkm orphans` (list of unconnected notes)
- `pkm search` (keyword-based search for similar notes)
- Read (review note content)
- Edit (add wikilinks)

## Principles
- Suggestions are based on semantic similarity — notes with the same tags but different content are not linked
- Do not run Edit without user approval
- Add bidirectional links (both A→B and B→A)

## Edge Cases
- If `pkm orphans` returns an empty list, print "no orphan notes, all connected" and exit
- If the user rejects a suggestion, skip that pair and move to the next candidate
- If Read fails, verify file existence with Glob and correct the path

## Example Flow
```
1. `pkm orphans` → get list of orphan notes
   e.g.: ["memo-async-pattern.md", "reading-clean-code.md", ...]

2. Read "memo-async-pattern.md" → extract key keywords: "async/await", "error handling"

3. `pkm search "async await error handling"` → search for similar notes
   Result: "javascript-error-handling-pattern.md" (score: 0.87)

4. Suggest to user:
   "Connect [[memo-async-pattern]] ↔ [[javascript-error-handling-pattern]]?"

5. On approval: Edit to add bidirectional links
6. Repeat for next orphan note
```

## Expected Output
- List of connected note pairs (how many pairs linked)
- List of rejected suggestions
- Count of remaining orphan notes
