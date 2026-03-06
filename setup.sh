#!/usr/bin/env bash
# Command Center AI — one-time setup
# Run once after cloning. After that: python engine/omniscience.py start
#
# Usage:
#   bash setup.sh
#
# Options:
#   PYTHON=python3.12 bash setup.sh    # pick Python version

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"

echo ""
echo "  Command Center AI — Setup"
echo "  ========================="
echo ""

# ── 1. Python venv ────────────────────────────────────────────────────────────
echo "[1/2] Python environment..."

if [[ ! -d "$ROOT/.venv" ]]; then
  "$PYTHON" -m venv "$ROOT/.venv"
  echo "      Created .venv"
else
  echo "      .venv already exists, skipping"
fi

PY="$ROOT/.venv/bin/python"
PIP="$ROOT/.venv/bin/pip"

"$PIP" install --quiet --upgrade pip
"$PIP" install --quiet -r "$ROOT/engine/requirements.txt"
echo "      Python dependencies installed"

# ── 2. Vault scaffold ─────────────────────────────────────────────────────────
echo "[2/2] Vault..."

VAULT="$ROOT/vault"
for DIR in Core Archive Knowledge; do
  mkdir -p "$VAULT/$DIR"
done

# Copy .example templates if real files don't exist yet
for TEMPLATE in "$VAULT/Core"/*.example "$VAULT/Archive"/*.example; do
  [[ -f "$TEMPLATE" ]] || continue
  TARGET="${TEMPLATE%.example}"
  if [[ ! -f "$TARGET" ]]; then
    cp "$TEMPLATE" "$TARGET"
    echo "      Created $(basename "$TARGET") from template"
  fi
done

echo "      Vault ready at $VAULT"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "  Setup complete."
echo ""
echo "  Next steps:"
echo "  1. Fill in your personal vault files:"
echo "     vault/Core/USER.md"
echo "     vault/Core/SOUL.md"
echo "     vault/Core/COMPANY-SOUL.md"
echo ""
echo "  2. Open the vault in Obsidian:"
echo "     File → Open Vault → select the vault/ folder"
echo ""
echo "  3. Start the engine:"
echo "     $PY engine/omniscience.py start"
echo ""
echo "  4. Connect your AI via MCP or REST API:"
echo "     See README.md for connection options."
echo ""
