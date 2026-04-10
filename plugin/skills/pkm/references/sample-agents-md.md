# Sample AGENTS.md — Memory Layer Integration

Add the snippet below to your project's `AGENTS.md` to enable the agent team to use shared memory.

---

```markdown
## Agent Memory Protocol

### Session Initialization
All agents must run the following before starting any task:

```bash
# 1. Search for relevant memories
pkm search "$TASK_DESCRIPTION" --top 5
pkm search "$TASK_DESCRIPTION" --type procedural --top 3

# 2. Set session ID
export SESSION_ID="$(date +%Y-%m-%d)-$(echo $TASK_NAME | tr ' ' '-' | head -c 20)"
```

### During Work
Save important discoveries immediately — don't wait until the session ends:

```bash
# When resolving an error (save immediately)
pkm note add --content "error name: cause and resolution" --type procedural --importance 8

# When making an architecture decision (save immediately)
pkm note add --content "decision — rationale" --type semantic --importance 7 --session $SESSION_ID

# Create a sub-note for a specific topic (logs [[wikilink]] in today's daily note)
pkm daily add --sub "<topic-title>"

# Open a sub-note in editor for extended notes
pkm daily edit --sub "<topic-title>"
```

### Before Claiming Completion
Before declaring task completion:

```bash
# 1. Review session memory
pkm search --session $SESSION_ID

# 2. Save any unsaved important discoveries
# 3. Check consolidation candidates (optional)
pkm consolidate
```

### Shared Memory Rules
- Don't report the same error twice — search before saving
- Memories with `importance >= 7` are considered knowledge shared across the entire team
- When conflicting memories are found between agents, prefer the more recent + higher importance
- Experimental/unverified discoveries should be saved with `importance <= 5`
```
