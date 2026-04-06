# Tag Explore — Tag Index Exploration

## Purpose
Use tags as index cards to explore knowledge by topic, and add descriptions to tag notes to build entry points into the knowledge network.

## Trigger
- **Primary:** tag explore, tag explore
- **Secondary:** tag search, tag organization, index notes, organize by topic

## Tools
- `pkm tags` — view full tag list + usage counts
- `pkm tags show <tag>` — tag note content + list of notes with that tag
- `pkm tags edit <tag>` — open tag note in editor
- `pkm tags search <pattern>` — tag pattern search (glob, AND, OR)

## Principles
- **Tags are index cards**: not just classification, but an entry point to the topic. Write a topic overview, key concepts, and related links in the tag note to make it a starting point for knowledge exploration.
- **Lazy creation**: tag notes are automatically created when `tags show` is run. No need to write descriptions for every tag — fill them in gradually, starting with the meaningful ones.
- **Discovery through cross-search**: use AND/OR search to discover new connections at the intersection of tags.

## Edge Cases
- Passing a non-existent tag to `pkm tags show` creates an empty tag note — this is intentional, but delete it from `tags/` if not needed
- Using special characters (`../`, non-allowed characters other than spaces) in tag names returns an error
- `pkm tags search "c++"` — consecutive `++` is recognized as a tag name; only a single `+` acts as the AND operator

## Example Flow

```bash
# 1. Check the current state of tags
pkm tags
# → database (5), python (3), postgresql (2), ...

# 2. View the index page for a major tag
pkm tags show database
# → tag note (empty) + list of 5 notes with the database tag

# 3. Write a topic overview in the tag note
pkm tags edit database
# → write in tags/database.md: "Collection of database-related notes. Key topics: MVCC, isolation levels, indexing", etc.

# 4. Discover related notes through cross-search
pkm tags search "database+postgresql"
# → filter to only notes with both tags

# 5. Explore related tag families
pkm tags search "data*"
# → notes for related tags like database, data-pipeline, data-modeling
```

## Expected Output
- Index notes with descriptions written for major tags (`tags/*.md`)
- Note groups identified by topic based on tags
- New connections discovered through cross-search
