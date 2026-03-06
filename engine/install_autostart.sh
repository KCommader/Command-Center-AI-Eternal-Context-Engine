#!/usr/bin/env bash
# Install Command Center AI as a systemd user service that starts on login.
# No root required — installs to ~/.config/systemd/user/
#
# Usage:
#   bash engine/install_autostart.sh
#
# Override Python or vault path:
#   PY_BIN=/path/to/python VAULT=/path/to/vault bash engine/install_autostart.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY_BIN="${PY_BIN:-$ROOT/.venv/bin/python}"
VAULT="${VAULT:-$ROOT/vault}"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
SERVICE_NAME="command-center.service"

if [[ ! -x "$PY_BIN" ]]; then
  echo "Python binary not found/executable: $PY_BIN" >&2
  echo "Set with: PY_BIN=/path/to/python bash engine/install_autostart.sh" >&2
  exit 1
fi

if [[ ! -d "$VAULT" ]]; then
  echo "Vault directory not found: $VAULT" >&2
  echo "Set with: VAULT=/path/to/vault bash engine/install_autostart.sh" >&2
  exit 1
fi

mkdir -p "$SYSTEMD_USER_DIR"

cat > "${SYSTEMD_USER_DIR}/${SERVICE_NAME}" <<EOF
[Unit]
Description=Command Center AI — Eternal Memory Engine
After=network.target

[Service]
Type=forking
WorkingDirectory=${ROOT}
ExecStart=${PY_BIN} ${ROOT}/engine/omniscience.py start --vault ${VAULT}
ExecStop=${PY_BIN} ${ROOT}/engine/omniscience.py stop
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now "${SERVICE_NAME}"

echo ""
echo "Command Center AI auto-start installed."
echo "Engine starts automatically on login."
echo ""
echo "Manage with:"
echo "  systemctl --user status ${SERVICE_NAME}"
echo "  systemctl --user stop ${SERVICE_NAME}"
echo "  systemctl --user start ${SERVICE_NAME}"
echo "  systemctl --user disable ${SERVICE_NAME}   # remove auto-start"
echo ""
echo "Vault:  ${VAULT}"
echo "Python: ${PY_BIN}"
echo "API:    http://localhost:8765"
