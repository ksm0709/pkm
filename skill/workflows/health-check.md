# Health Check — Note Health Diagnostics

## Purpose
Diagnose the overall health of the vault and report on orphan notes, stale ratios, and tag distribution.

## Trigger
- **Primary:** "health score"
- **Secondary:** "health check", "vault diagnosis", "note inspection"

## Tools
- `pkm orphans` (list of unconnected orphan notes)
- `pkm stale` (list of old, unmodified notes)
- `pkm tags` (current tag distribution)
- `pkm stats` (overall note statistics)

## Principles
- Numbers are measurements, not judgments — the report only describes current state
- Severity thresholds: orphan notes >10% = warning, >20% = critical
- Do not make immediate fixes after reporting; wait for the user's judgment

## Edge Cases
- If `pkm stats` returns 0, count files directly using Glob
- If `pkm stale` returns more than 50 results, show only the top 10 with "(+N more)"
- If the vault has no tags at all, recommend running the capture-triage workflow

## Example Flow
```
1. `pkm stats` → total note count, last-30-day activity stats
2. `pkm orphans` → orphan note count and list
3. `pkm stale` → list of notes unmodified for 90+ days
4. `pkm tags` → note distribution by tag
5. Calculate health scores:
   - orphan rate = orphan count / total count × 100
   - stale rate = stale count / total count × 100
6. Generate report
```

## Expected Output
```
## Vault Health Report — 2026-04-05

### Overall Statistics
- Total notes: 142
- New in last 30 days: 18
- Modified in last 30 days: 34

### Orphan Notes (no connections)
- Count: 11 (7.7%) — ⚠️ Warning
- Top items: "React Hook Memo", "Reading Log 2025-12", ...

### Stale Notes (90+ days unmodified)
- Count: 22 (15.5%)
- Top items: "Docker Config Memo", "Team Meeting Notes 2025-Q3", ...

### Tag Distribution
- #dev: 58 | #meeting: 23 | #idea: 19 | untagged: 12

### Recommended Actions
1. Use dream workflow to connect orphan notes
2. Review 5 stale notes (this week)
3. 12 untagged notes → run capture-triage
```
