#!/usr/bin/env bash
# Command Center AI — one-time setup
# Run once after cloning. After that: python engine/omniscience.py start
#
# Usage:
#   bash setup.sh
#
# Options (env overrides):
#   PYTHON=python3.12 bash setup.sh     # pick Python version
#   SKIP_DASHBOARD=1 bash setup.sh      # skip dashboard build (no node required)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"

echo ""
echo "  Command Center AI — Setup"
echo "  ========================="
echo ""

# ── 1. Python venv ────────────────────────────────────────────────────────────
echo "[1/3] Python environment..."

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

# ── 2. Dashboard build ────────────────────────────────────────────────────────
echo "[2/3] Dashboard..."

DASHBOARD="$ROOT/dashboard"

if [[ "${SKIP_DASHBOARD:-0}" == "1" ]]; then
  echo "      Skipped (SKIP_DASHBOARD=1)"
elif [[ ! -f "$DASHBOARD/package.json" ]]; then
  echo "      dashboard/ not found — skipping"
elif ! command -v node &>/dev/null; then
  echo "      node not found — skipping dashboard build"
  echo "      Install Node 20+ then run: cd dashboard && npm install && npm run build"
else
  NODE_VER=$(node --version | sed 's/v//' | cut -d. -f1)
  if [[ "$NODE_VER" -lt 20 ]]; then
    echo "      node v${NODE_VER} is too old (need v20+) — skipping dashboard build"
    echo "      Use nvm: nvm install 22 && nvm use 22, then re-run setup.sh"
  else
    echo "      node $(node --version) found"
    (cd "$DASHBOARD" && npm install --silent && npm run build --silent)
    echo "      Dashboard built"
  fi
fi

# ── 3. Vault scaffold ─────────────────────────────────────────────────────────
echo "[3/3] Vault..."

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
echo "  2. Start the engine:"
echo "     $PY engine/omniscience.py start"
echo ""
echo "  3. Open the dashboard:"
echo "     http://localhost:8765"
echo ""
