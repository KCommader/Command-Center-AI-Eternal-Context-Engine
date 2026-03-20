#!/usr/bin/env python3
"""
Omniscience Thin Launcher
=========================
Small wrapper to run Omniscience Engine like an app.

Commands:
  start            Start background engine process
  stop             Stop background engine process
  status           Show process status
  doctor           Validate local setup
  logs             Show recent log output
  watchdog-start   Start engine watchdog in background
  watchdog-stop    Stop the watchdog
  watchdog-status  Show watchdog status
  mcp-start        Start MCP HTTP server in background (for NAS / network)
  mcp-stop         Stop the MCP HTTP server
  mcp-status       Show MCP server status
  setup-ai         Write MCP config for Claude Code, Desktop, Cursor, or Zed
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
MCP_SCRIPT = Path(__file__).resolve().with_name("mcp_server.py")
RUNTIME_DIR = ROOT / ".omniscience"
STATE_FILE = RUNTIME_DIR / "state.json"
LOG_FILE = RUNTIME_DIR / "engine.log"
MCP_STATE_FILE = RUNTIME_DIR / "mcp.json"
MCP_LOG_FILE = RUNTIME_DIR / "mcp.log"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_MCP_PORT = 8766
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

    # Apply vault/config.yaml before spawning — the subprocess inherits these
    # env vars, so OMNI_* constants in engine.py pick them up at import time.
    try:
        sys.path.insert(0, str(ENGINE_SCRIPT.parent))
        from config import apply_yaml_config
        apply_yaml_config(vault)
    except Exception:
        pass  # YAML config is optional — fall through to env vars / defaults

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

    # ── Search quality verification ────────────────────────────────────────
    # Index a known test document, search for it, verify it ranks #1.
    # Proves the full pipeline works, not just "engine is running."
    print("[doctor] running search quality check...")
    try:
        import httpx

        port = int(state.get("port", 8765)) if state else 8765
        base = f"http://127.0.0.1:{port}"

        # Check if engine is reachable
        health = httpx.get(f"{base}/health", timeout=5)
        if health.status_code == 200:
            # Store a unique test document
            test_id = f"_doctor_test_{int(time.time())}"
            test_text = f"ECE search quality verification: {test_id} — this document confirms the search pipeline is healthy."
            capture_resp = httpx.post(
                f"{base}/capture",
                json={"text": test_text, "namespace": "_doctor", "tag": "doctor", "source": "doctor"},
                timeout=10,
            )

            if capture_resp.status_code == 200:
                # Give the engine a moment to index
                time.sleep(1)

                # Search for the test document
                search_resp = httpx.post(
                    f"{base}/search",
                    json={"query": test_id, "k": 3},
                    timeout=10,
                )

                if search_resp.status_code == 200:
                    results = search_resp.json().get("results", [])
                    found = any(test_id in str(r.get("text", "")) for r in results)
                    if found:
                        print("[doctor] search quality: PASS — test document found in results")
                    else:
                        warnings.append(
                            "Search quality: test document was stored but NOT found in search results. "
                            "Consider running a full reindex: python engine/omniscience.py reindex"
                        )
                else:
                    warnings.append(f"Search quality: search request failed ({search_resp.status_code})")
            else:
                warnings.append(f"Search quality: capture request failed ({capture_resp.status_code})")
        else:
            warnings.append("Search quality: engine not reachable — skipping search quality check")
    except Exception as exc:
        warnings.append(f"Search quality check skipped ({exc})")

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


def cmd_watchdog_start(args: argparse.Namespace) -> int:
    """Start the watchdog in the background."""
    pid_file = RUNTIME_DIR / "watchdog.pid"
    if pid_file.exists():
        try:
            existing_pid = int(pid_file.read_text().strip())
            if _is_process_running(existing_pid):
                print(f"Watchdog already running (pid={existing_pid})")
                return 0
        except Exception:
            pass

    watchdog_script = Path(__file__).resolve().with_name("watchdog.py")
    if not watchdog_script.exists():
        print(f"Watchdog script not found: {watchdog_script}")
        return 1

    _ensure_runtime_dir()
    log_path = RUNTIME_DIR / "watchdog.log"
    with log_path.open("a", encoding="utf-8") as logf:
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

        proc = subprocess.Popen([args.python, str(watchdog_script), "run"], **popen_kwargs)

    time.sleep(0.5)
    if proc.poll() is not None:
        print("Watchdog failed to start.")
        return 1

    print(f"Watchdog started (pid={proc.pid})")
    print(f"Log: {log_path}")
    return 0


def cmd_watchdog_stop(_: argparse.Namespace) -> int:
    """Stop the running watchdog."""
    pid_file = RUNTIME_DIR / "watchdog.pid"
    if not pid_file.exists():
        print("Watchdog is not running (no pid file).")
        return 0

    try:
        pid = int(pid_file.read_text().strip())
    except Exception:
        print("Could not read watchdog pid file.")
        pid_file.unlink(missing_ok=True)
        return 1

    if not _is_process_running(pid):
        print("Watchdog already stopped (stale pid file removed).")
        pid_file.unlink(missing_ok=True)
        return 0

    try:
        os.kill(pid, signal.SIGTERM)
        _wait_for_exit(pid, 5.0)
        pid_file.unlink(missing_ok=True)
        print(f"Watchdog stopped (pid={pid}).")
    except Exception as exc:
        print(f"Failed to stop watchdog: {exc}")
        return 1

    return 0


def cmd_watchdog_status(_: argparse.Namespace) -> int:
    """Show whether the watchdog is running."""
    pid_file = RUNTIME_DIR / "watchdog.pid"
    if not pid_file.exists():
        print("watchdog: stopped")
        return 0

    try:
        pid = int(pid_file.read_text().strip())
    except Exception:
        print("watchdog: stopped (unreadable pid file)")
        return 0

    if _is_process_running(pid):
        log_path = RUNTIME_DIR / "watchdog.log"
        print(f"watchdog: running (pid={pid})")
        print(f"log: {log_path}")
    else:
        print("watchdog: stopped (stale pid file)")
        pid_file.unlink(missing_ok=True)

    return 0


def cmd_mcp_start(args: argparse.Namespace) -> int:
    """Start MCP HTTP server as a background process (NAS / network mode)."""
    state = json.loads(MCP_STATE_FILE.read_text()) if MCP_STATE_FILE.exists() else None
    if state and _is_process_running(int(state.get("pid", 0))):
        print(f"MCP server already running (pid={state['pid']})")
        print(f"MCP endpoint: http://0.0.0.0:{state.get('port', DEFAULT_MCP_PORT)}/mcp")
        return 0

    if not MCP_SCRIPT.exists():
        print(f"MCP server script not found: {MCP_SCRIPT}")
        return 1

    vault = Path(args.vault).resolve()
    port = args.port
    python = args.python

    env = os.environ.copy()
    env["OMNI_VAULT_PATH"] = str(vault)
    env["OMNI_ENGINE_URL"] = f"http://127.0.0.1:{DEFAULT_PORT}"
    if args.key:
        env["OMNI_MCP_KEY"] = args.key

    cmd = [python, str(MCP_SCRIPT), "--transport", "http", "--port", str(port)]

    _ensure_runtime_dir()
    with MCP_LOG_FILE.open("a", encoding="utf-8") as logf:
        logf.write(f"\n\n=== MCP START {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        logf.write("CMD: " + " ".join(cmd) + "\n")
        logf.flush()

        popen_kwargs: dict[str, Any] = {
            "cwd": str(ROOT),
            "stdout": logf,
            "stderr": subprocess.STDOUT,
            "env": env,
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
        print("MCP server failed to start. Check logs:")
        print(f"  {MCP_LOG_FILE}")
        return 1

    mcp_state = {
        "pid": proc.pid,
        "started_at": time.time(),
        "port": port,
        "vault": str(vault),
        "log": str(MCP_LOG_FILE),
    }
    _ensure_runtime_dir()
    MCP_STATE_FILE.write_text(json.dumps(mcp_state, indent=2), encoding="utf-8")

    print(f"MCP server started (pid={proc.pid})")
    print(f"MCP endpoint: http://0.0.0.0:{port}/mcp")
    print(f"Auth: {'enabled (OMNI_MCP_KEY set)' if args.key else 'open — pass --key to secure'}")
    print(f"Log: {MCP_LOG_FILE}")
    print()
    print("Connect any AI on your network by adding this to its MCP config:")
    print(f'  "url": "http://YOUR_IP:{port}/mcp"')
    if args.key:
        print(f'  "headers": {{"Authorization": "Bearer {args.key}"}}')
    return 0


def cmd_mcp_stop(_: argparse.Namespace) -> int:
    """Stop the running MCP HTTP server."""
    if not MCP_STATE_FILE.exists():
        print("MCP server is not running (no state file).")
        return 0

    try:
        state = json.loads(MCP_STATE_FILE.read_text())
    except Exception:
        MCP_STATE_FILE.unlink(missing_ok=True)
        return 0

    pid = int(state.get("pid", 0))
    if not _is_process_running(pid):
        print("MCP server already stopped (stale state removed).")
        MCP_STATE_FILE.unlink(missing_ok=True)
        return 0

    try:
        os.kill(pid, signal.SIGTERM)
        _wait_for_exit(pid, 5.0)
        MCP_STATE_FILE.unlink(missing_ok=True)
        print(f"MCP server stopped (pid={pid}).")
    except Exception as exc:
        print(f"Failed to stop MCP server: {exc}")
        return 1
    return 0


def cmd_mcp_status(_: argparse.Namespace) -> int:
    """Show MCP HTTP server status."""
    if not MCP_STATE_FILE.exists():
        print("mcp: stopped")
        return 0

    try:
        state = json.loads(MCP_STATE_FILE.read_text())
    except Exception:
        print("mcp: stopped (unreadable state file)")
        return 0

    pid = int(state.get("pid", 0))
    if _is_process_running(pid):
        port = state.get("port", DEFAULT_MCP_PORT)
        print(f"mcp: running (pid={pid})")
        print(f"endpoint: http://0.0.0.0:{port}/mcp")
        print(f"log: {state.get('log', MCP_LOG_FILE)}")
    else:
        print("mcp: stopped (stale state removed)")
        MCP_STATE_FILE.unlink(missing_ok=True)
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

    # watchdog subcommands
    p_wd_start = sub.add_parser("watchdog-start", help="Start engine watchdog in background")
    p_wd_start.add_argument("--python", default=sys.executable, help="Python executable")
    p_wd_start.set_defaults(func=cmd_watchdog_start)

    p_wd_stop = sub.add_parser("watchdog-stop", help="Stop the engine watchdog")
    p_wd_stop.set_defaults(func=cmd_watchdog_stop)

    p_wd_status = sub.add_parser("watchdog-status", help="Show watchdog status")
    p_wd_status.set_defaults(func=cmd_watchdog_status)

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

    p_setup = sub.add_parser(
        "setup-ai",
        help="Write MCP config + bootstrap instruction for a connected AI runtime",
    )
    p_setup.add_argument(
        "runtime",
        nargs="?",
        default="claude-code",
        choices=["claude-code", "claude-desktop", "cursor", "zed"],
        help="Which AI runtime to configure (default: claude-code)",
    )
    p_setup.add_argument(
        "--vault", default=str(DEFAULT_VAULT), metavar="PATH",
        help="Absolute path to the vault directory",
    )
    p_setup.add_argument(
        "--http", metavar="HOST_OR_IP",
        help="Generate network/NAS config pointing to this IP (e.g. 192.168.1.10 or myvault.local)",
    )
    p_setup.add_argument(
        "--mcp-port", type=int, default=DEFAULT_MCP_PORT, metavar="PORT",
        help=f"MCP HTTP port to use in the generated config (default: {DEFAULT_MCP_PORT})",
    )
    p_setup.set_defaults(func=cmd_setup_ai)

    # MCP HTTP server management
    p_mcp_start = sub.add_parser("mcp-start", help="Start MCP HTTP server in background (NAS / network)")
    p_mcp_start.add_argument("--vault", default=str(DEFAULT_VAULT), help="Vault path")
    p_mcp_start.add_argument("--port", type=int, default=DEFAULT_MCP_PORT, help=f"MCP port (default: {DEFAULT_MCP_PORT})")
    p_mcp_start.add_argument("--key", default=os.environ.get("OMNI_MCP_KEY", ""), help="Bearer token (auth)")
    p_mcp_start.add_argument("--python", default=sys.executable, help="Python executable")
    p_mcp_start.set_defaults(func=cmd_mcp_start)

    p_mcp_stop = sub.add_parser("mcp-stop", help="Stop the MCP HTTP server")
    p_mcp_stop.set_defaults(func=cmd_mcp_stop)

    p_mcp_status = sub.add_parser("mcp-status", help="Show MCP HTTP server status")
    p_mcp_status.set_defaults(func=cmd_mcp_status)

    return parser


def cmd_setup_ai(args: argparse.Namespace) -> int:
    """Write MCP config and bootstrap instructions for the chosen AI runtime."""
    import json as _json

    root = ROOT.resolve()
    vault = Path(args.vault).resolve()
    mcp_script = (root / "engine" / "mcp_server.py").as_posix()
    runtime = args.runtime
    http_host = getattr(args, "http", None)
    mcp_port = getattr(args, "mcp_port", DEFAULT_MCP_PORT)

    # ── Network / NAS mode ────────────────────────────────────────────────────
    if http_host:
        mcp_url = f"http://{http_host}:{mcp_port}/mcp"
        network_block: dict = {"url": mcp_url}
        mcp_key = os.environ.get("OMNI_MCP_KEY", "")
        if mcp_key:
            network_block["headers"] = {"Authorization": f"Bearer {mcp_key}"}

        snippet = _json.dumps({"mcpServers": {"command-center": network_block}}, indent=2)
        print("── Network / NAS MCP config ─────────────────────────────────────────")
        print()
        print("Paste this into your AI client's MCP config (settings.json / mcp.json):")
        print()
        print(snippet)
        print()
        if not mcp_key:
            print("Tip: set OMNI_MCP_KEY on the server for auth, then re-run this command")
            print("     and the Bearer token will appear in the snippet automatically.")
            print()
        print("On your NAS / server, start the MCP HTTP server:")
        print(f"  python engine/omniscience.py mcp-start --port {mcp_port}")
        print()
        print("HTTPS (recommended for internet access):")
        print("  Use Caddy or nginx as a reverse proxy in front of the MCP port.")
        print("  Caddy example (automatic TLS):")
        print(f"    myvault.yourdomain.com {{")
        print(f"      reverse_proxy localhost:{mcp_port}")
        print(f"    }}")
        print()
        print("  Then update your AI config url to: https://myvault.yourdomain.com/mcp")
        return 0

    # ── Local stdio mode ──────────────────────────────────────────────────────
    mcp_block = {
        "mcpServers": {
            "command-center": {
                "command": sys.executable,
                "args": [mcp_script],
                "env": {
                    "OMNI_VAULT_PATH": vault.as_posix(),
                    "OMNI_ENGINE_URL": f"http://127.0.0.1:{DEFAULT_PORT}",
                },
            }
        }
    }

    if runtime == "claude-code":
        config_dir = root / ".claude"
        config_dir.mkdir(exist_ok=True)
        config_path = config_dir / "mcp_config.json"
        config_path.write_text(_json.dumps(mcp_block, indent=2), encoding="utf-8")
        print(f"[setup-ai] Wrote {config_path}")
        print()
        print("Bootstrap is already wired — CLAUDE.md tells Claude Code to call")
        print("bootstrap_agent(reason='session_start') at the top of every session.")
        print()
        print("Start the engine, then open this project in Claude Code and you're live.")
        print(f"  python engine/omniscience.py start")

    elif runtime == "claude-desktop":
        import platform
        if platform.system() == "Darwin":
            dest = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        else:
            dest = Path.home() / ".config" / "claude" / "claude_desktop_config.json"

        existing: dict = {}
        if dest.exists():
            try:
                existing = _json.loads(dest.read_text(encoding="utf-8"))
            except Exception:
                pass
        existing.setdefault("mcpServers", {})
        existing["mcpServers"]["command-center"] = mcp_block["mcpServers"]["command-center"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_json.dumps(existing, indent=2), encoding="utf-8")
        print(f"[setup-ai] Wrote {dest}")
        print()
        print("Restart Claude Desktop to pick up the new MCP server.")
        print("Then start a conversation with:  bootstrap_agent(reason='session_start')")

    elif runtime in ("cursor", "zed"):
        config_path = root / ".cursor" / "mcp.json" if runtime == "cursor" else root / ".zed" / "settings.json"
        config_path.parent.mkdir(exist_ok=True)
        config_path.write_text(_json.dumps(mcp_block, indent=2), encoding="utf-8")
        print(f"[setup-ai] Wrote {config_path}")
        print()
        print(f"Reload {runtime.title()} to pick up the MCP server.")
        print("Call bootstrap_agent(reason='session_start') at the start of each session.")

    print()
    print("Done. Run `python engine/omniscience.py doctor` to verify.")
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
