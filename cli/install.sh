#!/usr/bin/env bash
# PKM CLI installer
# Usage: bash install.sh
# Requires: Python 3.10+
set -euo pipefail

GITHUB_REPO="ksm0709/pkm"
PKM_INSTALL_REF="${PKM_INSTALL_REF:-main}"
if [[ "$PKM_INSTALL_REF" == "main" ]]; then
  PKM_ARCHIVE_REF="refs/heads/main"
elif [[ "$PKM_INSTALL_REF" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  PKM_ARCHIVE_REF="refs/tags/$PKM_INSTALL_REF"
else
  echo "Error: PKM_INSTALL_REF must be 'main' or a canonical tag such as v2.96.2." >&2
  exit 1
fi

# ── Termux (Android) detection ───────────────────────────────────────────────
# Termux needs Rust for native wheels, serialized builds for cargo registry
# races, and skips [search] (no PyTorch Android wheel).  Delegate to the
# dedicated Termux installer when we detect the environment.
if [[ -n "${TERMUX_VERSION:-}" || -d "/data/data/com.termux" ]]; then
  TERMUX_SCRIPT=""
  # Resolve the Termux script relative to this file when run from the repo.
  if [[ -n "${BASH_SOURCE[0]+x}" && "${BASH_SOURCE[0]}" != "" && "${BASH_SOURCE[0]}" != "bash" ]]; then
    _dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    [[ -f "$_dir/install-termux.sh" ]] && TERMUX_SCRIPT="$_dir/install-termux.sh"
  fi
  # When piped (curl | bash), download the repo and exec the Termux script.
  if [[ -z "$TERMUX_SCRIPT" ]]; then
    echo "Termux detected — downloading Termux installer..."
    _tmp="$(mktemp -d)"
    curl -fsSL "https://github.com/$GITHUB_REPO/archive/$PKM_ARCHIVE_REF.tar.gz" \
      | tar -xz -C "$_tmp" --strip-components=1
    TERMUX_SCRIPT="$_tmp/cli/install-termux.sh"
  fi
  echo "Termux detected — forwarding to install-termux.sh"
  exec bash "$TERMUX_SCRIPT" "$@"
fi

echo "=== PKM CLI Installer ==="
echo ""

# When run via `curl | bash`, BASH_SOURCE[0] is unbound (stdin).
# Detect this and download the source from GitHub instead.
CLEANUP_TMP=false

install_cloudflared() {
  if command -v cloudflared &>/dev/null; then
    echo "✓ cloudflared $(cloudflared --version | awk '{print $3}')"
    return 0
  fi

  local os arch asset bin_dir target tmp_file
  os="${PKM_CLOUDFLARED_OS:-$(uname -s)}"
  arch="${PKM_CLOUDFLARED_ARCH:-$(uname -m)}"

  case "$os:$arch" in
    Linux:x86_64|Linux:amd64) asset="cloudflared-linux-amd64" ;;
    Linux:aarch64|Linux:arm64) asset="cloudflared-linux-arm64" ;;
    Linux:armv7l|Linux:arm) asset="cloudflared-linux-arm" ;;
    *)
      echo "Warning: automatic cloudflared install is not supported for $os/$arch." >&2
      echo "Install it manually from: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/" >&2
      return 0
      ;;
  esac

  bin_dir="${PKM_CLOUDFLARED_BIN_DIR:-$HOME/.local/bin}"
  target="$bin_dir/cloudflared"
  mkdir -p "$bin_dir"

  tmp_file="$(mktemp)"
  echo "cloudflared not found — installing to $target..."
  curl -fsSL -o "$tmp_file" "${PKM_CLOUDFLARED_URL:-https://github.com/cloudflare/cloudflared/releases/latest/download/$asset}"
  chmod +x "$tmp_file"
  mv "$tmp_file" "$target"
  export PATH="$bin_dir:$PATH"

  echo "✓ cloudflared installed: $("$target" --version)"
}

if [[ "${PKM_INSTALL_ONLY_CLOUDFLARED:-}" == "1" ]]; then
  install_cloudflared
  exit 0
fi

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
  curl -fsSL "https://github.com/$GITHUB_REPO/archive/$PKM_ARCHIVE_REF.tar.gz" \
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

if [[ "${PKM_INSTALL_CLOUDFLARED:-}" == "1" ]]; then
  install_cloudflared
else
  echo "cloudflared is optional. Install later with: PKM_INSTALL_CLOUDFLARED=1 bash install.sh"
fi

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
