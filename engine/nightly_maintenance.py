#!/usr/bin/env python3
"""
Nightly maintenance for Omniscience Engine.

Runs:
- local doctor check
- admin cleanup endpoint (if engine is running)

Logs output to .omniscience/nightly.log.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIR = ROOT / ".omniscience"
STATE_FILE = RUNTIME_DIR / "state.json"
NIGHTLY_LOG = RUNTIME_DIR / "nightly.log"


def _log(msg: str) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    with NIGHTLY_LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(line)


def _read_state() -> dict | None:
    if not STATE_FILE.exists():
        return None
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def run_doctor(python_bin: str, vault: Path) -> int:
    cmd = [python_bin, str(ROOT / "engine" / "omniscience.py"), "doctor", "--vault", str(vault)]
    _log("doctor: start")
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True)
    if proc.stdout:
        _log("doctor: stdout begin")
        for ln in proc.stdout.splitlines():
            _log(f"doctor> {ln}")
    if proc.stderr:
        _log("doctor: stderr begin")
        for ln in proc.stderr.splitlines():
            _log(f"doctor! {ln}")
    _log(f"doctor: exit={proc.returncode}")
    return proc.returncode


def try_admin_cleanup(state: dict | None) -> bool:
    if not state:
        _log("cleanup: skipped (engine state not found)")
        return False

    host = state.get("host", "127.0.0.1")
    port = int(state.get("port", 8765))
    url = f"http://{host}:{port}/admin/cleanup"

    headers = {"Content-Type": "application/json"}
    token = (
        os.getenv("OMNI_API_KEYS_ADMIN", "").split(",")[0].strip()
        or os.getenv("OMNI_API_KEY", "").strip()
    )
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=b"{}", headers=headers, method="POST")
    _log(f"cleanup: request {url}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            _log(f"cleanup: ok status={resp.status} body={body[:500]}")
            return True
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        _log(f"cleanup: http_error status={exc.code} body={body[:500]}")
        return False
    except Exception as exc:
        _log(f"cleanup: error {exc}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Nightly maintenance")
    parser.add_argument("--python", default=sys.executable, help="Python executable")
    parser.add_argument("--vault", default=str(ROOT / "vault"), help="Vault path")
    args = parser.parse_args()

    vault = Path(args.vault).resolve()
    _log("nightly: start")
    doctor_rc = run_doctor(args.python, vault)
    cleanup_ok = try_admin_cleanup(_read_state())
    _log(f"nightly: done doctor_rc={doctor_rc} cleanup_ok={cleanup_ok}")
    return 0 if doctor_rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

