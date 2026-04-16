# Add Workflow — Workflow Creation Wizard

## Purpose
Fully clarify new PKM workflow requirements through a Socratic interview, ensure quality with ambiguity/stability measurement, then create and deploy the file.

## Trigger
- **Primary:** add-workflow, add workflow, new workflow
- **Secondary:** create workflow, custom workflow

## Tools
- AskUserQuestion (Socratic interview — one question at a time)
- Read (`plugin/skills/pkm/workflows/` — reference existing workflows as concrete examples)
- Write (`plugin/skills/pkm/workflows/<name>.md`, `plugin/skills/pkm/commands/<name>.md`)
- Edit (`plugin/skills/pkm/SKILL.md`)
- Bash (`cp ~/.claude/commands/pkm/` immediate deployment)

## Principles
- Ask **one question at a time**, using AskUserQuestion
- Calculate ambiguity score after each round and share it with the user
- Continue the interview until Ambiguity ≤ 20%
- Show existing workflows as examples, but encourage the user to invent new patterns
- When concepts converge (same entity for 2 consecutive rounds), wrap up the interview

## Workflow

### Phase 0: Introduction

```
Starting the PKM workflow creation wizard.

Using the Socratic method, questions will help concretize your idea into a complete workflow specification.
Clarity is measured after each round; once sufficiently clear, the files will be created.

Current ambiguity: 100%
```

Show the list of existing workflows:
```
Current workflows:
  init-daily         — start today's daily note
  extract-note-from-daily — promote daily → atomic note
  weekly-review      — weekly review
  auto-tagging       — classify untagged notes
  auto-linking       — auto-link similar notes
  health-check       — vault health diagnosis
  tag-explore        — tag-based knowledge exploration
  backlink-traverse  — backlink-based connection traversal
  1on1-prep          — 1:1 meeting preparation
  task-sync          — TODO/task synchronization
  monthly-synthesis  — monthly synthesis
  add-context-to-daily — record project context
  (+ memory-* series)
```

### Phase 1: Socratic Interview Loop

**Ambiguity 5 Dimensions (workflow-design specific):**

| Dimension | Weight | Meaning |
|-----------|--------|---------|
| Purpose Clarity | 30% | Is the problem this workflow solves clear? Is it differentiated from existing workflows? |
| Trigger Clarity | 20% | Are there specific signals for when to run it? |
| Tool Coverage | 20% | Do we know which pkm commands/file tools to use? |
| Flow Completeness | 20% | Are the execution steps concrete enough to be reproducible? |
| Output Clarity | 10% | Is the deliverable the user receives upon completion clear? |

**Ambiguity Calculation:**
```
clarity = purpose×0.30 + trigger×0.20 + tool×0.20 + flow×0.20 + output×0.10
ambiguity = 1 - clarity
```

**Question Strategy:**
- Each round: ask 1 question targeting the weakest dimension
- State the weakest dimension and the reason first, then ask the question
- Show concrete examples from existing workflows to present options
- Ask questions that surface hidden assumptions in the user's answers

**Interview Format (each round):**
```
Round {n} | Target: {weakest_dimension} | Ambiguity: {score}%

[One-line reason why weakest_dimension is low]

{question}
```

**pkm Feature Reference (present when asking about Tool Coverage):**
```
CLI commands:
  pkm daily                       — view/create today's daily
  pkm daily add "content"         — add timestamped entry
  pkm daily todo "task"           — add TODO
  pkm note add "title" --tags t,t2 — create atomic note
  pkm note show <query>           — view note + backlinks
  pkm note links <query>          — backlinks-only table view
  pkm note edit <query>           — open in editor
  pkm note orphans                — list isolated notes
  pkm note stale --days 30        — stale notes
  pkm tags                        — tag list + counts
  pkm tags show <tag>             — notes by tag
  pkm tags search "python+ml"     — AND/OR/glob tag search
  pkm vault list                  — vault list
  pkm search <query>              — semantic search (index required)
  pkm index                       — build search index
  pkm stats                       — vault statistics
  pkm consolidate                 — list dailies ready for promotion
  pkm consolidate mark YYYY-MM-DD — mark as promotion-ready

File tools:
  Read / Write / Edit             — direct note manipulation
  Glob                            — file pattern search
  Grep                            — content search
```

**Existing Workflow Examples (for reference):**

`health-check` Tools example:
```
- pkm stats
- pkm note orphans
- pkm note stale --days 30
- pkm tags
```

`extract-note-from-daily` Flow example:
```
1. pkm consolidate → check unintegrated dailies
2. Read daily/*.md (consolidated: true items)
3. Identify recurring keywords → list of promotion candidates
4. pkm search → check for duplicates among existing notes
5. pkm note add → create new atomic note
6. Edit → add wikilink
7. pkm consolidate mark → mark as complete
```

**Convergence Tracking (Concept Stability):**

Extract the core elements of the current workflow concept after each round:
- Core Problem (the problem being solved)
- Primary Action (main action)
- Key Entities (notes, tags, dailies, etc.)

Compare with the previous round and calculate stability_ratio:
```
stability_ratio = stable_elements / total_elements
```

If stability ≥ 0.8 for 2 consecutive rounds, the concept is considered converged.

**Post-Round Report:**
```
Round {n} complete.

| Dimension | Score | Weight | Contribution | Undecided |
|-----------|-------|--------|--------------|-----------|
| Purpose     | {s} | 30% | {s*0.3} | {gap or "clear"} |
| Trigger     | {s} | 20% | {s*0.2} | {gap or "clear"} |
| Tool        | {s} | 20% | {s*0.2} | {gap or "clear"} |
| Flow        | {s} | 20% | {s*0.2} | {gap or "clear"} |
| Output      | {s} | 10% | {s*0.1} | {gap or "clear"} |
| **Ambiguity** | | | **{score}%** | |

Concept convergence: {stable}/{total} elements stable (stability: {ratio})

Next target: {weakest_dimension} — {reason}
```

**Early Exit Conditions:**
- Ambiguity ≤ 20% → automatically proceed to Phase 2
- After round 3, if user says "that's enough", "create it", etc. — warn and confirm
- Round 10: soft warning ("Current ambiguity {score}%. Continue?")

**Challenge Mode (creativity enhancement):**
- Round 4+: "If this workflow didn't exist, how would you achieve the same goal right now?" → remove unnecessary complexity
- Round 6+: "What would the simplest version look like?" → refine the core
- Round 8+ (ambiguity > 0.3): "Which existing workflow is most similar? What makes this one different?" → clarify differentiation

### Phase 2: Finalize Specification and Create Files

Summarize collected information for confirmation:
```
Workflow Specification (Ambiguity: {final_score}%)

Name: <name>
Purpose: <purpose>
Trigger: Primary — <primary> | Secondary — <secondary>
Tools: <tools>
Principles: <principles>
Flow: <n> steps
Expected Output: <output>
```

Confirm via AskUserQuestion:
- "Create as-is"
- "Rename and create"
- "Continue interview"

After confirmation, create the files:

**`plugin/skills/pkm/workflows/<name>.md`** (follow `_template.md` structure):
```markdown
# <Workflow Name>

## Purpose
<purpose>

## Trigger
- **Primary:** <primary trigger>
- **Secondary:** <secondary triggers>

## Tools
<bullet list of pkm commands and file tools>

## Principles
<bullet list of principles>

## Edge Cases
<bullet list of edge cases>

## Example Flow
<numbered concrete steps>

## Expected Output
<output description>
```

**`plugin/skills/pkm/commands/<name>.md`**:
```markdown
Read `~/.claude/skills/pkm/workflows/<name>.md` and execute the workflow described there.
```

**`plugin/skills/pkm/SKILL.md`** — add a row to the workflow table:
```
| <Display Name> | <trigger keywords> | workflows/<name>.md |
```

**Immediate deployment:**
```bash
mkdir -p ~/.claude/commands/pkm ~/.agents/commands/pkm
cp plugin/skills/pkm/commands/<name>.md ~/.claude/commands/pkm/<name>.md
cp plugin/skills/pkm/commands/<name>.md ~/.agents/commands/pkm/<name>.md
```

### Phase 3: Complete

```
✓ Workflow created!

Final Ambiguity: {score}%

Files created:
  plugin/skills/pkm/workflows/<name>.md
  plugin/skills/pkm/commands/<name>.md

SKILL.md updated

Ready to use immediately (no Claude Code restart required):
  /pkm:<name>

To commit to the repository:
  git add plugin/skills/pkm/ && git commit -m "feat: add <name> workflow"
```

## Edge Cases
- Name conflicts with existing workflow → suggest a different name
- Primary Trigger overlaps with existing workflow → warn and confirm
- `~/.claude/commands/pkm/`, `~/.agents/commands/pkm/` do not exist → create automatically
- Ambiguity stagnates within ±5% for 3 consecutive rounds → reframe: "Let's redefine the concept itself"

## Expected Output
- `plugin/skills/pkm/workflows/<name>.md` (completed workflow specification)
- `plugin/skills/pkm/commands/<name>.md` (slash command wrapper)
- `plugin/skills/pkm/SKILL.md` (table updated)
- `~/.claude/commands/pkm/<name>.md` (immediately deployed)
- `~/.agents/commands/pkm/<name>.md` (immediately deployed)
