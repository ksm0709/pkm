#!/usr/bin/env bash
# PKM CLI installer — Termux (Android) variant
# Usage: bash install-termux.sh
#   or:  curl -fsSL .../install.sh | bash   (auto-detected)
#
# Termux quirks handled here:
#   1. Native Python extensions (rpds-py, pydantic-core, cryptography) need
#      Rust, which is not bundled — install via `pkg install rust`.
#   2. Cargo's registry unpacking races on Android's filesystem, producing
#      spurious "File exists" errors — serialize with UV_CONCURRENT_BUILDS=1.
#   3. Cross-filesystem hardlinks are unsupported — UV_LINK_MODE=copy.
#   4. The [search] extra pulls in sentence-transformers → PyTorch, which has
#      no aarch64-android wheel.  Install core only; offer [search] as opt-in.
set -euo pipefail

echo "=== PKM CLI Installer (Termux) ==="
echo ""

GITHUB_REPO="ksm0709/pkm"
CLEANUP_TMP=false

# ── Locate source tree ──────────────────────────────────────────────────────
if [[ -n "${BASH_SOURCE[0]+x}" && "${BASH_SOURCE[0]}" != "" && "${BASH_SOURCE[0]}" != "bash" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [[ ! -f "$SCRIPT_DIR/pyproject.toml" ]]; then
    SCRIPT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)/cli"
  fi
else
  echo "Running via pipe — downloading source from GitHub..."
  TMP_DIR="$(mktemp -d)"
  CLEANUP_TMP=true
  curl -fsSL "https://github.com/$GITHUB_REPO/archive/refs/heads/main.tar.gz" \
    | tar -xz -C "$TMP_DIR" --strip-components=1
  SCRIPT_DIR="$TMP_DIR/cli"
fi

# ── System dependencies via pkg ─────────────────────────────────────────────
ensure_pkg() {
  local cmd="$1" pkg="${2:-$1}"
  if command -v "$cmd" &>/dev/null; then
    return 0
  fi
  echo "$cmd not found — installing via pkg..."
  pkg install -y "$pkg"
}

ensure_pkg python3 python
ensure_pkg rustc  rust
ensure_pkg curl   curl

# ── Python version check ────────────────────────────────────────────────────
read -r PYTHON_MAJOR PYTHON_MINOR <<< \
  "$(python3 -c 'import sys; print(sys.version_info.major, sys.version_info.minor)')"
PYTHON_VERSION="$PYTHON_MAJOR.$PYTHON_MINOR"

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]; }; then
  echo "Error: Python 3.10+ required (found $PYTHON_VERSION)" >&2
  exit 1
fi
echo "✓ Python $PYTHON_VERSION"

# ── Install uv if missing ───────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
  echo "uv not found — installing..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  if ! command -v uv &>/dev/null; then
    echo "Error: uv installation failed." >&2
    exit 1
  fi
fi
echo "✓ uv $(uv --version)"

# ── Clean stale cargo registry artifacts ─────────────────────────────────────
# Android's filesystem sometimes leaves orphan .cargo-ok files that block
# subsequent unpacks.
if [[ -d "$HOME/.cargo/registry/src" ]]; then
  find "$HOME/.cargo/registry/src" -name ".cargo-ok" -size 0 -delete 2>/dev/null || true
fi

# ── Choose extras ────────────────────────────────────────────────────────────
# Default: skip [search] because PyTorch has no Android wheel.
# Set PKM_INSTALL_SEARCH=1 to attempt it anyway (e.g. if a custom torch wheel
# is available).
INSTALL_SPEC="."
if [[ "${PKM_INSTALL_SEARCH:-0}" == "1" ]]; then
  echo "Note: installing with [search] extras (PyTorch) — this may fail on Android."
  INSTALL_SPEC=".[search]"
else
  echo "Note: skipping [search] extras (sentence-transformers / PyTorch"
  echo "      has no aarch64-android wheel).  Core CLI features work fine."
  echo "      Set PKM_INSTALL_SEARCH=1 to attempt it anyway."
fi

# ── Install pkm ─────────────────────────────────────────────────────────────
echo ""
echo "Installing pkm..."
cd "$SCRIPT_DIR"

# UV_CONCURRENT_BUILDS=1  — serialize native builds to avoid cargo registry
#                           race ("File exists" on .cargo-ok).
# UV_LINK_MODE=copy       — Termux's filesystem does not support cross-device
#                           hardlinks between cache and tool directories.
export UV_LINK_MODE=copy
export UV_CONCURRENT_BUILDS=1

if [[ "$CLEANUP_TMP" == "true" ]]; then
  uv tool install "$INSTALL_SPEC"
  rm -rf "$TMP_DIR"
else
  uv tool install --editable "$INSTALL_SPEC"
fi

TOOL_BIN_DIR="$(uv tool dir --bin)"

# ── PATH persistence ────────────────────────────────────────────────────────
echo ""
echo "✓ pkm installed successfully!"

if [[ ":$PATH:" != *":$TOOL_BIN_DIR:"* ]]; then
  # Termux typically sources ~/.bashrc on every interactive shell.
  SHELL_RC="$HOME/.bashrc"
  if ! grep -qF "$TOOL_BIN_DIR" "$SHELL_RC" 2>/dev/null; then
    echo "export PATH=\"$TOOL_BIN_DIR:\$PATH\"" >> "$SHELL_RC"
    echo "Added $TOOL_BIN_DIR to $SHELL_RC"
  fi
  export PATH="$TOOL_BIN_DIR:$PATH"
fi

echo ""
echo "Next step: run 'pkm setup' to configure your vaults."
