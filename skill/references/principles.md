# PKM Principles & Know-how

This document accumulates principles, patterns, and know-how discovered through PKM work.
Update it whenever new insights emerge.

## Core Principles

### 1. Atomicity
One note = one topic. If a note covers two topics connected by "and", split them.
However, multiple aspects of a single topic (e.g., definition, pros/cons, use cases) belong in one note.

### 2. Connection
Every note must be connected to at least one other note via `[[wikilink]]`.
Isolated notes are dead knowledge that will never be found.

**Types of connections:**
- **Source connection**: `[[2026-04-05]]` — the daily note where this knowledge was first recorded
- **Concept connection**: `[[related-concept]]` — related concepts
- **Parent/child**: Managed with tags; explicitly state relationships in the note body when needed

### 3. Own Words
Copy-paste is not knowledge. Understand the core and write it concisely in your own words.
The process of "understand → summarize → articulate" is what makes it stick.

### 4. Flat Structure + Tag Classification
Do not create folders inside `notes/`. Classify with tags.
Folders create physical boundaries that impede connections. Tags allow multi-classification.

### 5. Progressive Refinement
The first version doesn't need to be perfect. Record roughly in dailies, promote to atomic notes when repeated,
and refine a little each time it's referenced.

## Tagging Strategy

### Tag Rules
- English tags: kebab-case (`global-planning`)
- Non-ASCII tags: no spaces (`selfimprovement`)
- Check existing tags before creating new ones (`pkm tags`)
- Tag pattern examples by purpose:
  - People: lowercase name (`sunny`, `junho`)
  - Technology: topic kebab-case (`navigation`, `global-planning`)
  - Type: activity type (`1on1`, `team`, `knowledge`)
  - Category: broad classification (`learning`, `technology`, `philosophy`)

## Know-how

_Add practical know-how discovered during PKM work here._

### Promotion Timing
- If the same topic appears 3+ times in dailies, it's a promotion candidate
- Anything you think "I'll need to look this up later" should be promoted immediately

### Good Note Titles
- Use claims or conclusions as titles: "PostgreSQL MVCC implements snapshot isolation" > "PostgreSQL MVCC"
- Consider searchability: what keywords would you use to find this later?

### Frontmatter Management
- Keep `id` identical to the filename (without extension)
- `aliases` for frequently used abbreviations or alternative names
- `source` is the originating daily note date (optional)
