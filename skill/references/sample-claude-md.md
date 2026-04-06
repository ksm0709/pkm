# Sample CLAUDE.md — Memory Layer Integration

Add the snippet below to your project's `CLAUDE.md` to enable agents to use the PKM memory layer.

---

```markdown
## Memory Layer

This project uses the PKM memory layer to persist agent knowledge.

### Before Starting Work (required)
1. Search for relevant past knowledge:
   ```bash
   pkm search "<current task keywords>" --top 5
   pkm search "<current task keywords>" --type procedural --top 3
   ```
2. Items with score 0.6 or higher must be read and referenced
3. If a previously resolved identical error exists, try that solution first

### During Work (on important discoveries)
```bash
# After fixing an error
pkm note add --content "<error name> fix: <resolution>" --type procedural --importance 8

# After an architecture decision
pkm note add --content "<decision> — reason: <rationale>" --type semantic --importance 7

# Session progress
pkm note add --content "<completed work>" --type episodic --importance 5 --session $SESSION_ID
```

### After Work is Complete
```bash
# Review session memory
pkm search --session $SESSION_ID

# Check consolidation candidates
pkm consolidate
```

### Memory Type Guide
- `procedural`: fix recipes, HOW-TOs ("to fix X, do Y")
- `semantic`: architecture decisions, API behavior, patterns ("Z works like this")
- `episodic`: progress, session events ("completed A today")

### Importance Scale
- 7-8: Information that must be revisited in the next session
- 5-6: Useful as context but not essential
- 9-10: Core project constraints, decisions that must never be missed
```
