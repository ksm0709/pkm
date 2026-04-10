# Backlink Traverse — Backlink-Based Knowledge Exploration

## Purpose
Traverse backlinks to explore connections between notes, discover isolated notes, and increase the density of the knowledge network.

## Trigger
- **Primary:** backlink traversal, backlink traverse
- **Secondary:** connection exploration, knowledge exploration, note relationships, check backlinks

## Tools
- `pkm note show <query>` — note body + Backlinks section at the bottom (with descriptions)
- `pkm note links <query>` — view only that note's backlinks as a table
- `pkm note orphans` — find isolated notes with no connections
- `pkm tags show <tag>` — start exploration from a tag-based entry point

## Principles
- **Backlinks are "who references me"**: wikilinks inside a note are "what I reference"; backlinks are the reverse. Seeing both together reveals the full context of a note.
- **Quick judgment via description**: in the backlink list, notes with a description are shown as `title — description`, allowing you to assess relevance without opening the note.
- **Zero orphan notes**: orphans are dead knowledge. Check regularly and either connect them or clean them up.

## Edge Cases
- Notes with no backlinks — the Backlinks section will not appear in `note show` (this is normal)
- Tag notes (`tags/*.md`) are excluded from backlink scanning — prevents lazily-created files from affecting counts
- In large vaults, `find_backlinks()` scans all .md files and may be slow — not an issue at current scale

## Example Flow

```bash
# 1. Start from a tag index
pkm tags show database
# → view list of notes with the database tag
# → mvcc, database-isolation, concurrency-note, etc.

# 2. Understand the connections of a key note
pkm note show mvcc
# → after body output...
# Backlinks
#   · database-isolation
#   · concurrency-note — comparison note on concurrency control techniques

# 3. Follow backlinks to explore related notes
pkm note show database-isolation
# → view this note's body + backlinks
# → discover it is only referenced by mvcc

# 4. Quickly check with backlinks-only view
pkm note links mvcc
# → see Title | Description | Path table at a glance

# 5. Discover orphan notes → add wikilinks
pkm note orphans
# → list of notes with no connections
# → add [[orphan-note]] wikilink to related notes to connect them to the network
```

## Expected Output
- Connections between notes are understood (which notes are hubs, which are isolated)
- Wikilinks added to orphan notes, integrating them into the network
- Descriptions written to enable quick context assessment when traversing backlinks
