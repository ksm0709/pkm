#!/usr/bin/env bash
# E2E test for install.sh — runs in a tmp dir, does not pollute the system.
#
# Tests two modes:
#   1. Local file:  bash install.sh          (BASH_SOURCE[0] is set)
#   2. Pipe/stdin:  bash < install.sh        (BASH_SOURCE[0] unbound, simulates curl | bash)
#
# Usage:
#   bash cli/tests/test_install_e2e.sh
#
# Requirements: uv, python3

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTALL_SCRIPT="$REPO_ROOT/cli/install.sh"

PASS=0
FAIL=0

# ── helpers ──────────────────────────────────────────────────────────────────

run_test() {
  local name="$1"; shift
  echo ""
  echo "▶ $name"
  if "$@"; then
    echo "  ✓ PASS"
    ((PASS++)) || true
  else
    echo "  ✗ FAIL (exit $?)"
    ((FAIL++)) || true
  fi
}

# Install into a fresh tmp dir and verify pkm binary exists + runs.
# $1 = mode description, $2 = tmp dir, $3+ = bash invocation
assert_install() {
  local tmp_tools="$1/uv-tools"
  local tmp_bin="$1/uv-bin"
  mkdir -p "$tmp_tools" "$tmp_bin"

  # Run the install with UV dirs redirected so nothing touches ~/.local
  UV_TOOL_DIR="$tmp_tools" UV_TOOL_BIN_DIR="$tmp_bin" \
    bash "${@:2}" 2>&1 | sed 's/^/    /'

  local pkm_bin="$tmp_bin/pkm"
  if [[ ! -x "$pkm_bin" ]]; then
    echo "  pkm binary not found at $pkm_bin" >&2
    return 1
  fi

  # Smoke-test: pkm --help must exit 0
  "$pkm_bin" --help >/dev/null
}

# ── setup ─────────────────────────────────────────────────────────────────────

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Copy the cli/ tree into tmp so the "local file" test runs from an isolated dir
TMP_CLI="$TMP/cli"
cp -r "$REPO_ROOT/cli/." "$TMP_CLI"

# ── test 1: local file mode ───────────────────────────────────────────────────
# BASH_SOURCE[0] resolves to the script path → uses the adjacent pyproject.toml

run_test "local file mode (bash install.sh from tmp dir)" \
  assert_install "$TMP/local" "$TMP_CLI/install.sh"

# ── test 2: pipe/stdin mode ───────────────────────────────────────────────────
# BASH_SOURCE[0] is unbound → script downloads source from GitHub and installs.
# Skip if no network (check via curl to github).

if curl -fsS --max-time 5 "https://github.com" -o /dev/null 2>/dev/null; then
  run_test "pipe/stdin mode (bash < install.sh, simulates curl | bash)" \
    assert_install "$TMP/pipe" -s < "$INSTALL_SCRIPT"
else
  echo ""
  echo "▷ pipe/stdin mode — SKIPPED (no network)"
fi

# ── summary ───────────────────────────────────────────────────────────────────

echo ""
echo "══════════════════════════════════"
echo "  Results: $PASS passed, $FAIL failed"
echo "══════════════════════════════════"

[[ $FAIL -eq 0 ]]
