#!/usr/bin/env bash
# PKM CLI installer
# Usage: bash install.sh
# Requires: Python 3.10+
set -euo pipefail

echo "=== PKM CLI Installer ==="
echo ""

# When run via `curl | bash`, BASH_SOURCE[0] is unbound (stdin).
# Detect this and download the source from GitHub instead.
GITHUB_REPO="ksm0709/pkm"
CLEANUP_TMP=false

if [[ -n "${BASH_SOURCE[0]+x}" && "${BASH_SOURCE[0]}" != "" && "${BASH_SOURCE[0]}" != "bash" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  # Walk up to find the cli/ directory containing pyproject.toml
  if [[ ! -f "$SCRIPT_DIR/pyproject.toml" ]]; then
    SCRIPT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)/cli"
  fi
else
  echo "Running via pipe — downloading source from GitHub..."
  TMP_DIR="$(mktemp -d)"
  CLEANUP_TMP=true
  # Extract the full repo (not just cli/) so that symlinks inside cli/ that
  # point to sibling directories (e.g. src/pkm/skill -> ../../../skill) resolve.
  curl -fsSL "https://github.com/$GITHUB_REPO/archive/refs/heads/main.tar.gz" \
    | tar -xz -C "$TMP_DIR" --strip-components=1
  SCRIPT_DIR="$TMP_DIR/cli"
fi

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "Error: Python 3.10+ is required. Please install Python first." >&2
  exit 1
fi

read -r PYTHON_MAJOR PYTHON_MINOR <<< "$(python3 -c 'import sys; print(sys.version_info.major, sys.version_info.minor)')"
PYTHON_VERSION="$PYTHON_MAJOR.$PYTHON_MINOR"

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]; }; then
  echo "Error: Python 3.10+ required (found $PYTHON_VERSION)" >&2
  exit 1
fi

echo "✓ Python $PYTHON_VERSION"

# Install uv if missing
if ! command -v uv &>/dev/null; then
  echo "uv not found — installing..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # Add uv to PATH for this session
  export PATH="$HOME/.local/bin:$PATH"
  if ! command -v uv &>/dev/null; then
    echo "Error: uv installation failed. Please install manually: https://github.com/astral-sh/uv" >&2
    exit 1
  fi
fi

echo "✓ uv $(uv --version)"

# Install pkm as a uv-managed tool so no pre-existing virtualenv is required.
echo ""
echo "Installing pkm..."
cd "$SCRIPT_DIR"
if [[ "$CLEANUP_TMP" == "true" ]]; then
  # Temp source dir — install normally (editable would require the dir to persist)
  uv tool install ".[search]"
  rm -rf "$TMP_DIR"
else
  uv tool install --editable ".[search]"
fi

TOOL_BIN_DIR="$(uv tool dir --bin)"


echo ""
echo "✓ pkm installed successfully!"
if [[ ":$PATH:" != *":$TOOL_BIN_DIR:"* ]]; then
  echo ""
  echo "Note: $TOOL_BIN_DIR is not on your PATH in this shell."
  echo "If 'pkm' is not found, run:"
  echo "  export PATH=\"$TOOL_BIN_DIR:\$PATH\""
  echo "Or configure your shell once with:"
  echo "  uv tool update-shell"
fi
echo ""
echo "Next step: run 'pkm setup' to configure your vaults."
