#!/usr/bin/env python3
"""
Omniscience Thin Launcher
=========================
Small wrapper to run Omniscience Engine like an app.

Commands:
  start   Start background engine process
  stop    Stop background engine process
  status  Show process status
  doctor  Validate local setup
  logs    Show recent log output
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ENGINE_SCRIPT = Path(__file__).resolve().with_name("engine.py")
RUNTIME_DIR = ROOT / ".omniscience"
STATE_FILE = RUNTIME_DIR / "state.json"
LOG_FILE = RUNTIME_DIR / "engine.log"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_VAULT = ROOT / "vault"


def _ensure_runtime_dir() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def _read_state() -> dict[str, Any] | None:
    if not STATE_FILE.exists():
        return None
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def _write_state(data: dict[str, Any]) -> None:
    _ensure_runtime_dir()
    STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _remove_state() -> None:
    try:
        STATE_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def _is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _wait_for_exit(pid: int, timeout_sec: float) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if not _is_process_running(pid):
            return True
        time.sleep(0.2)
    return not _is_process_running(pid)


def cmd_start(args: argparse.Namespace) -> int:
    state = _read_state()
    if state and _is_process_running(int(state.get("pid", 0))):
        print(f"Engine already running (pid={state['pid']})")
        print(f"Endpoint: http://{state.get('host', DEFAULT_HOST)}:{state.get('port', DEFAULT_PORT)}")
        return 0

    if state:
        _remove_state()

    if not ENGINE_SCRIPT.exists():
        print(f"Engine script not found: {ENGINE_SCRIPT}")
        return 1

    vault = Path(args.vault).resolve()
    if not vault.exists():
        print(f"Vault path not found: {vault}")
        return 1

    cmd = [
        args.python,
        str(ENGINE_SCRIPT),
        "--vault",
        str(vault),
        "--watch",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]

    if args.foreground:
        print("Running in foreground:")
        print(" ", " ".join(cmd))
        return subprocess.call(cmd, cwd=str(ROOT))

    _ensure_runtime_dir()
    with LOG_FILE.open("a", encoding="utf-8") as logf:
        logf.write(f"\n\n=== START {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        logf.write("CMD: " + " ".join(cmd) + "\n")
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

    time.sleep(0.8)
    if proc.poll() is not None:
        print("Engine failed to start. Check logs:")
        print(f"  {LOG_FILE}")
        return 1

    state = {
        "pid": proc.pid,
        "started_at": time.time(),
        "host": args.host,
        "port": args.port,
        "vault": str(vault),
        "python": args.python,
        "log": str(LOG_FILE),
        "cmd": cmd,
    }
    _write_state(state)

    print(f"Engine started (pid={proc.pid})")
    print(f"Endpoint: http://{args.host}:{args.port}")
    print(f"Log: {LOG_FILE}")
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    state = _read_state()
    if not state:
        print("Engine is not running (no state file).")
        return 0

    pid = int(state.get("pid", 0))
    if not _is_process_running(pid):
        print("Engine is already stopped (stale state removed).")
        _remove_state()
        return 0

    print(f"Stopping engine pid={pid}...")

    try:
        os.kill(pid, signal.SIGTERM)
    except Exception as exc:
        print(f"Failed to send SIGTERM: {exc}")

    if _wait_for_exit(pid, args.timeout):
        _remove_state()
        print("Engine stopped.")
        return 0

    print("Graceful stop timed out; forcing shutdown...")
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True)
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass

    if _wait_for_exit(pid, 3):
        _remove_state()
        print("Engine force-stopped.")
        return 0

    print("Failed to stop engine.")
    return 1


def cmd_status(_: argparse.Namespace) -> int:
    state = _read_state()
    if not state:
        print("status: stopped")
        return 0

    pid = int(state.get("pid", 0))
    if not _is_process_running(pid):
        print("status: stopped (stale state)")
        _remove_state()
        return 0

    print("status: running")
    print(f"pid: {pid}")
    print(f"endpoint: http://{state.get('host', DEFAULT_HOST)}:{state.get('port', DEFAULT_PORT)}")
    print(f"vault: {state.get('vault', str(DEFAULT_VAULT))}")
    print(f"log: {state.get('log', str(LOG_FILE))}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    errors: list[str] = []
    warnings: list[str] = []

    print("[doctor] checking engine script...")
    if not ENGINE_SCRIPT.exists():
        errors.append(f"Missing engine script: {ENGINE_SCRIPT}")

    vault = Path(args.vault).resolve()
    print("[doctor] checking vault path...")
    if not vault.exists():
        errors.append(f"Missing vault path: {vault}")

    print("[doctor] checking runtime dir write access...")
    try:
        _ensure_runtime_dir()
        test_file = RUNTIME_DIR / ".write_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
    except Exception as exc:
        errors.append(f"Runtime dir not writable: {exc}")

    print("[doctor] checking Python dependencies...")
    deps = [
        "lancedb",
        "pyarrow",
        "fastapi",
        "uvicorn",
        "sentence_transformers",
        "watchdog",
    ]
    for dep in deps:
        try:
            importlib.import_module(dep)
        except Exception as exc:
            errors.append(f"Missing or broken dependency '{dep}': {exc}")

    print("[doctor] checking current engine status...")
    state = _read_state()
    if state:
        pid = int(state.get("pid", 0))
        if not _is_process_running(pid):
            warnings.append("Stale state file detected (engine not running).")

    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"- {w}")

    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"- {e}")
        return 1

    print("\nDoctor check passed.")
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    if not LOG_FILE.exists():
        print(f"No log file yet: {LOG_FILE}")
        return 0

    lines = LOG_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
    tail = lines[-args.lines :]
    for line in tail:
        print(line)
    return 0


def cmd_sync_skills(args: argparse.Namespace) -> int:
    from engine.skill_adapter import (
        sync_skills, import_from_runtimes, list_skills_table,
        _SKILLS_SOURCE, ADAPTERS,
    )
    verbose = not getattr(args, "quiet", False)

    if getattr(args, "list_skills", False):
        list_skills_table(_SKILLS_SOURCE)
        return 0

    runtimes = getattr(args, "runtimes", None)
    if runtimes:
        unknown = [r for r in runtimes if r not in ADAPTERS]
        if unknown:
            print(f"Unknown runtime(s): {', '.join(unknown)}. Valid: {', '.join(ADAPTERS)}")
            return 1

    if getattr(args, "reverse", False):
        import_from_runtimes(runtimes=runtimes, vault_skills_path=_SKILLS_SOURCE,
                             dry_run=args.dry_run, verbose=verbose)
    else:
        results = sync_skills(runtimes=runtimes, source=_SKILLS_SOURCE,
                              dry_run=args.dry_run, verbose=verbose)
        errors = [r for rs in results.values() for r in rs if r.action == "error"]
        if errors:
            return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Omniscience launcher")
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", help="Start engine in background")
    p_start.add_argument("--vault", default=str(DEFAULT_VAULT), help="Vault path")
    p_start.add_argument("--host", default=DEFAULT_HOST, help="API host (default: 127.0.0.1)")
    p_start.add_argument("--port", type=int, default=DEFAULT_PORT, help="API port")
    p_start.add_argument("--python", default=sys.executable, help="Python executable")
    p_start.add_argument("--foreground", action="store_true", help="Run attached to terminal")
    p_start.set_defaults(func=cmd_start)

    p_stop = sub.add_parser("stop", help="Stop running engine")
    p_stop.add_argument("--timeout", type=float, default=8.0, help="Graceful stop timeout seconds")
    p_stop.set_defaults(func=cmd_stop)

    p_status = sub.add_parser("status", help="Show current status")
    p_status.set_defaults(func=cmd_status)

    p_doc = sub.add_parser("doctor", help="Validate setup")
    p_doc.add_argument("--vault", default=str(DEFAULT_VAULT), help="Vault path")
    p_doc.set_defaults(func=cmd_doctor)

    p_logs = sub.add_parser("logs", help="Show engine logs")
    p_logs.add_argument("--lines", type=int, default=60, help="Number of log lines")
    p_logs.set_defaults(func=cmd_logs)

    p_sync = sub.add_parser("sync-skills", help="Sync vault/Skills/ to all AI runtimes")
    p_sync.add_argument(
        "--runtime", "-r", action="append", dest="runtimes", metavar="NAME",
        help="Runtime to sync (claude, gemini, codex, custom-ai). Repeat for multiple. Default: all."
    )
    p_sync.add_argument("--dry-run", "-n", action="store_true", help="Preview without writing")
    p_sync.add_argument("--list", "-l", action="store_true", dest="list_skills", help="List vault skills and exit")
    p_sync.add_argument("--reverse", action="store_true", help="Import FROM runtimes INTO vault")
    p_sync.add_argument("--quiet", "-q", action="store_true", help="Suppress output")
    p_sync.set_defaults(func=cmd_sync_skills)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
