#!/usr/bin/env bash
# PKM CLI installer
# Usage: bash install.sh
# Requires: Python 3.10+
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"


echo "=== PKM CLI Installer ==="
echo ""

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
uv tool install --editable ".[search]"

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
