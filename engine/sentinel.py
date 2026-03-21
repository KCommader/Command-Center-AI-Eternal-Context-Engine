#!/usr/bin/env python3
"""
ECE Watchdog
============
Monitors the Omniscience Engine and restarts it automatically if it goes down.

The watchdog is a lightweight background process. It polls /health every
WATCHDOG_POLL_SEC seconds. On WATCHDOG_FAIL_THRESHOLD consecutive failures,
it reads the last known start command from .omniscience/state.json and
relaunches the engine.

This solves the most common continuity break: a system restart, crash, or
idle timeout drops the engine, and the next AI session cold-starts with no
memory. The watchdog closes that gap — the engine comes back before the
next session even begins.

Usage (via omniscience.py):
  python engine/omniscience.py watchdog start   # Detach and run in background
  python engine/omniscience.py watchdog stop    # Stop the watchdog
  python engine/omniscience.py watchdog status  # Show watchdog status
  python engine/omniscience.py watchdog run     # Run in foreground (systemd)

Direct usage:
  python engine/watchdog.py run
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

# ── Runtime paths ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIR = ROOT / ".omniscience"
STATE_FILE = RUNTIME_DIR / "state.json"
WATCHDOG_PID_FILE = RUNTIME_DIR / "watchdog.pid"
WATCHDOG_LOG_FILE = RUNTIME_DIR / "watchdog.log"

# ── Config (all overridable via env) ──────────────────────────────────────────
WATCHDOG_POLL_SEC = int(os.getenv("OMNI_SENTINEL_POLL_SEC", "20"))
WATCHDOG_FAIL_THRESHOLD = int(os.getenv("OMNI_SENTINEL_FAIL_THRESHOLD", "3"))
WATCHDOG_RESTART_DELAY_SEC = int(os.getenv("OMNI_SENTINEL_RESTART_DELAY_SEC", "3"))
WATCHDOG_HEALTH_TIMEOUT_SEC = int(os.getenv("OMNI_SENTINEL_HEALTH_TIMEOUT_SEC", "5"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        WATCHDOG_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with WATCHDOG_LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _read_state() -> dict[str, Any] | None:
    if not STATE_FILE.exists():
        return None
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write_state(data: dict[str, Any]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _health_url(state: dict[str, Any]) -> str:
    host = state.get("host", "127.0.0.1")
    port = state.get("port", 8765)
    return f"http://{host}:{port}/health"


def _check_health(url: str) -> bool:
    try:
        r = httpx.get(url, timeout=WATCHDOG_HEALTH_TIMEOUT_SEC)
        return r.status_code == 200
    except Exception:
        return False


def _restart_engine(state: dict[str, Any]) -> int | None:
    """Relaunch the engine using the command stored in state.json.

    Returns the new PID on success, None on failure.
    """
    cmd: list[str] | None = state.get("cmd")
    if not cmd:
        _log("No restart command in state — cannot auto-restart.")
        return None

    log_path = Path(state.get("log", str(WATCHDOG_LOG_FILE)))
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as logf:
            logf.write(f"\n\n=== WATCHDOG RESTART {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            logf.flush()
            popen_kwargs: dict[str, Any] = {
                "cwd": str(ROOT),
                "stdout": logf,
                "stderr": subprocess.STDOUT,
            }
            if os.name == "nt":
                popen_kwargs["creationflags"] = (
                    getattr(subprocess, "DETACHED_PROCESS", 0)
                    | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                )
            else:
                popen_kwargs["start_new_session"] = True

            proc = subprocess.Popen(cmd, **popen_kwargs)

        time.sleep(WATCHDOG_RESTART_DELAY_SEC)
        if proc.poll() is not None:
            _log("Engine failed to start after restart attempt.")
            return None

        new_state = dict(state)
        new_state["pid"] = proc.pid
        new_state["started_at"] = time.time()
        _write_state(new_state)
        return proc.pid

    except Exception as exc:
        _log(f"Restart failed: {exc}")
        return None


# ── Main watchdog loop ────────────────────────────────────────────────────────

def run_watchdog() -> None:
    """Main loop — runs until killed.

    Tracks consecutive health check failures. On WATCHDOG_FAIL_THRESHOLD
    failures it attempts a restart. Resets the failure counter on success or
    after a successful restart.
    """
    _log(f"Watchdog started (pid={os.getpid()}). "
         f"Poll every {WATCHDOG_POLL_SEC}s, restart after {WATCHDOG_FAIL_THRESHOLD} failures.")

    consecutive_failures = 0

    while True:
        try:
            state = _read_state()

            if state is None:
                # Engine hasn't been started at all — nothing to watch yet.
                _log("No state file found — waiting for engine to start.")
                time.sleep(WATCHDOG_POLL_SEC)
                consecutive_failures = 0
                continue

            engine_pid = int(state.get("pid", 0))
            health_url = _health_url(state)

            # First: is the process even alive?
            if not _is_process_running(engine_pid):
                _log(f"Engine process (pid={engine_pid}) not found.")
                consecutive_failures += 1
            else:
                # Process alive — check HTTP health
                ok = _check_health(health_url)
                if ok:
                    if consecutive_failures > 0:
                        _log("Engine healthy again — resetting failure counter.")
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    _log(f"Health check failed ({consecutive_failures}/{WATCHDOG_FAIL_THRESHOLD}): {health_url}")

            if consecutive_failures >= WATCHDOG_FAIL_THRESHOLD:
                _log(f"Threshold reached — restarting engine.")
                new_pid = _restart_engine(state)
                if new_pid:
                    _log(f"Engine restarted (pid={new_pid}).")
                    consecutive_failures = 0
                else:
                    _log("Restart failed — will retry next cycle.")
                    consecutive_failures = WATCHDOG_FAIL_THRESHOLD - 1  # back off one step

        except Exception as exc:
            _log(f"Watchdog loop error: {exc}")

        time.sleep(WATCHDOG_POLL_SEC)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "run":
        # Write own PID so omniscience.py can find and stop us.
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        WATCHDOG_PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
        try:
            run_watchdog()
        finally:
            WATCHDOG_PID_FILE.unlink(missing_ok=True)
    else:
        print(__doc__)
        sys.exit(1)
