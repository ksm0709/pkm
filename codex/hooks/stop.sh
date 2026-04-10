#!/bin/bash
# codex/hooks/stop.sh — Phase 2 intelligent Stop hook for Codex
# Exit-2 blocking: writes extraction instructions to stderr, exits 2
# Codex main agent receives stderr as "continuation prompt" and acts on it
# Codex binary confirms only type: "command" is supported at runtime.
if ! command -v jq >/dev/null 2>&1; then
  # jq not available — skip processing to avoid silent failures
  exit 0
fi

INPUT=$(cat)

# Guard: prevent infinite loop when stop_hook_active is set
HOOK_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')
if [ "$HOOK_ACTIVE" = "true" ]; then
  exit 0
fi

TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // empty')
if [ -z "$TRANSCRIPT_PATH" ]; then
  exit 0
fi

# Inject extraction instructions via stderr (exit 2 = "continue working")
cat >&2 << 'EOF'
KNOWLEDGE EXTRACTION TASK: Before stopping, extract knowledge from this session.
Use your Read tool to read the session transcript, then:
1. Identify: key decisions, bugs fixed, patterns learned, new concepts discovered
2. For session entries: run `pkm daily add '<summary>'` via your Bash tool
3. For reusable knowledge: run `pkm note add '<content>' --type semantic --importance <5-9> --tags <tags>` via your Bash tool
4. Run: `pkm daily add '<one-sentence session summary>'`
Be selective — skip trivial facts. Quality over quantity.
Then you may stop.
EOF
exit 2
