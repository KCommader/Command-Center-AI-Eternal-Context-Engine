#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY_BIN="${PY_BIN:-$ROOT/.venv/bin/python}"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
SERVICE_NAME="omniscience-nightly.service"
TIMER_NAME="omniscience-nightly.timer"

if [[ ! -x "$PY_BIN" ]]; then
  echo "Python binary not found/executable: $PY_BIN" >&2
  echo "Set with: PY_BIN=/path/to/python bash engine/install_nightly_timer.sh" >&2
  exit 1
fi

mkdir -p "$SYSTEMD_USER_DIR"

cat > "${SYSTEMD_USER_DIR}/${SERVICE_NAME}" <<EOF
[Unit]
Description=Omniscience nightly maintenance (doctor + cleanup)

[Service]
Type=oneshot
WorkingDirectory=${ROOT}
ExecStart=${PY_BIN} ${ROOT}/engine/nightly_maintenance.py --python ${PY_BIN} --vault ${ROOT}/vault
EOF

cat > "${SYSTEMD_USER_DIR}/${TIMER_NAME}" <<EOF
[Unit]
Description=Run Omniscience nightly maintenance timer

[Timer]
OnCalendar=*-*-* 03:15:00
Persistent=true
RandomizedDelaySec=10m
Unit=${SERVICE_NAME}

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now "${TIMER_NAME}"

echo "Installed and started ${TIMER_NAME}"
echo "Check status:"
echo "  systemctl --user status ${TIMER_NAME}"
echo "  systemctl --user list-timers | rg omniscience-nightly || true"
