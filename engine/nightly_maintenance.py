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

from context_state import ensure_state_files, refresh_freshness_report

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


def purge_cache_tier(vault: Path) -> int:
    """Delete all files from vault/Cache/ — session memory, not worth keeping."""
    cache_dir = vault / "Cache"
    if not cache_dir.exists():
        _log("cache_purge: Cache/ directory not found, skipping")
        return 0
    removed = 0
    for f in cache_dir.glob("*.md"):
        try:
            f.unlink()
            _log(f"cache_purge: removed {f.name}")
            removed += 1
        except Exception as exc:
            _log(f"cache_purge: failed to remove {f.name}: {exc}")
    _log(f"cache_purge: done removed={removed}")
    return removed


def expire_short_term(vault: Path, ttl_days: int = 30) -> int:
    """Remove short-term memory files older than ttl_days."""
    short_dir = vault / "Archive" / "short"
    if not short_dir.exists():
        return 0
    cutoff = time.time() - (ttl_days * 86400)
    removed = 0
    for f in short_dir.glob("*.md"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                _log(f"short_term_expire: removed {f.name} (>{ttl_days}d old)")
                removed += 1
        except Exception as exc:
            _log(f"short_term_expire: failed {f.name}: {exc}")
    _log(f"short_term_expire: done removed={removed}")
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="Nightly maintenance")
    parser.add_argument("--python", default=sys.executable, help="Python executable")
    parser.add_argument("--vault", default=str(ROOT / "vault"), help="Vault path")
    parser.add_argument("--short-term-ttl", type=int, default=30, help="Days before short-term memory expires")
    args = parser.parse_args()

    vault = Path(args.vault).resolve()
    _log("nightly: start")

    # 1. Engine health check
    doctor_rc = run_doctor(args.python, vault)

    # 2. Engine admin cleanup (cache, temp files)
    cleanup_ok = try_admin_cleanup(_read_state())

    # 3. Purge vault/Cache/ (session-level noise)
    purge_cache_tier(vault)

    # 4. Expire old short-term memory files
    expire_short_term(vault, ttl_days=args.short_term_ttl)

    # 5. Refresh operating-state files and the freshness snapshot
    ensure_state_files(vault)
    freshness = refresh_freshness_report(vault, stale_days=args.short_term_ttl, write=True)
    _log(
        "freshness: "
        f"fresh={freshness['counts']['fresh']} "
        f"stale={freshness['counts']['stale']} "
        f"missing={freshness['counts']['missing']}"
    )

    _log(f"nightly: done doctor_rc={doctor_rc} cleanup_ok={cleanup_ok}")
    return 0 if doctor_rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
