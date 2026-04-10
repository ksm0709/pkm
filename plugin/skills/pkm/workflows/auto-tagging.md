# Capture Triage — Untagged Note Classification

## Purpose
Find notes with no tags in their frontmatter, suggest appropriate tags, and classify them.

## Trigger
- **Primary:** "untagged cleanup"
- **Secondary:** "untagged notes", "capture triage", "classify notes"

## Tools
- Grep (find notes with an empty `tags` field in frontmatter)
- Read (review note content)
- Edit (add tags)
- `pkm tags` (review the existing tag list)

## Principles
- First understand the existing tag taxonomy, then classify within it — minimize creating new tags
- Recommend no more than 3 tags per note
- Do not add tags without reading the content

## Edge Cases
- If Grep returns no results, print "no unclassified notes" and exit
- If content is too short to classify, suggest the "#stub" tag
- If the user requests changes after a tag suggestion, offer alternatives and re-confirm

## Example Flow
```
1. `pkm tags` → understand the current vault's tag list
   e.g.: #dev, #meeting, #idea, #book, #personal

2. Grep `notes/` for empty tags field:
   Pattern: `tags:\s*\[\]` or `tags:$`
   Results: ["memo-240315.md", "scrap-react.md", "thoughts.md"]

3. Read "memo-240315.md" → content: memo about React performance optimization
   Suggested tags: ["#dev", "#react"]

4. Confirm with user:
   "Add tags #dev, #react to 'memo-240315.md'?"

5. On approval: Edit to update frontmatter

6. Repeat for next note
```

## Expected Output
- List of notes with tags added (note name, tags added)
- List of skipped notes (with reason)
- Count of remaining unclassified notes after processing
