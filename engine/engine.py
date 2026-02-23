"""
Omniscience Engine
==================
A local, AI-agnostic eternal context system for personal AI assistants.

Combines:
  - Obsidian Markdown vault (human-readable, visually browsable)
  - LanceDB vector database (lightning-fast semantic search)

Usage:
  python engine.py --vault ./vault --watch    # Watch vault and serve API
  python engine.py --vault ./vault --reindex  # Force full re-index
  python engine.py --vault ./vault --search "your query here"

API Endpoints (default http://127.0.0.1:8765):
  GET  /health
  POST /search
  POST /capture
  POST /admin/reindex

Auth:
  - Default single key (full access): OMNI_API_KEY
  - Optional role split keys:
      OMNI_API_KEYS_READ=token1,token2
      OMNI_API_KEYS_WRITE=token3
      OMNI_API_KEYS_ADMIN=token4
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa
import uvicorn
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# ─── Config ───────────────────────────────────────────────────────────────────
DEFAULT_VAULT = "./vault"
DB_DIR = ".lancedb"
TABLE_NAME = "context"
MODEL_NAME = "BAAI/bge-small-en-v1.5"  # local model, first run downloads once
EMBED_DIM = 384
CHUNK_SIZE = 500
CHUNK_OVERLAP = 80
API_PORT = 8765
API_HOST = "127.0.0.1"
IGNORED_DIRS = {".lancedb", ".obsidian", ".git", "__pycache__", "venv", ".venv", "node_modules"}

ROLE_RANK = {"read": 1, "write": 2, "admin": 3}

SCHEMA = pa.schema(
    [
        pa.field("id", pa.string()),
        pa.field("path", pa.string()),
        pa.field("chunk_index", pa.int32()),
        pa.field("text", pa.string()),
        pa.field("tags", pa.string()),
        pa.field("namespace", pa.string()),
        pa.field("source", pa.string()),
        pa.field("vector", pa.list_(pa.float32(), EMBED_DIM)),
        pa.field("indexed_at", pa.string()),
    ]
)


# ─── API Models ───────────────────────────────────────────────────────────────
class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(default=5, ge=1, le=50)
    namespaces: list[str] | None = None
    tags: list[str] | None = None
    path_prefix: str | None = None


class CaptureRequest(BaseModel):
    text: str = Field(min_length=1)
    tag: str = "captured"
    namespace: str = "company_memory"
    source: str = "manual"
    file_name: str | None = None


# ─── Helpers ──────────────────────────────────────────────────────────────────
def chunk_text(text: str) -> list[str]:
    chunks, start = [], 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunk = text[start:end].strip()
        if len(chunk) > 30:
            chunks.append(chunk)
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def extract_tags(text: str) -> str:
    tags = re.findall(r"#([a-zA-Z0-9_-]+)", text)
    return " ".join(sorted(set(tags)))


def chunk_id(rel_path: str, idx: int) -> str:
    return hashlib.sha256(f"{rel_path}:{idx}".encode()).hexdigest()[:16]


def vault_md_files(vault: Path) -> list[Path]:
    result = []
    for root, dirs, files in os.walk(vault):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        for file_name in files:
            if file_name.endswith(".md"):
                result.append(Path(root) / file_name)
    return result


def slug(s: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", s.strip().lower())
    return cleaned.strip("_") or "default"


def infer_namespace(rel_path: str) -> str:
    rel = rel_path.replace("\\", "/").lower()
    if rel.startswith("knowledge/books"):
        return "books_trading"
    if rel.startswith("projects/bots"):
        return "bots_runtime"
    if rel.startswith("core/"):
        return "company_core"
    if rel.startswith("archive/"):
        return "company_memory"

    first = Path(rel).parts[0] if Path(rel).parts else "default"
    return slug(first)


def _parse_key_list(name: str) -> set[str]:
    raw = os.getenv(name, "")
    return {x.strip() for x in raw.split(",") if x.strip()}


def load_auth_config() -> dict[str, set[str]]:
    return {
        "single": {os.getenv("OMNI_API_KEY", "").strip()} - {""},
        "read": _parse_key_list("OMNI_API_KEYS_READ"),
        "write": _parse_key_list("OMNI_API_KEYS_WRITE"),
        "admin": _parse_key_list("OMNI_API_KEYS_ADMIN"),
    }


def build_token_roles(auth_cfg: dict[str, set[str]]) -> dict[str, str]:
    token_role: dict[str, str] = {}

    # Single key default: full admin-level access.
    for token in auth_cfg["single"]:
        token_role[token] = "admin"

    for role in ("read", "write", "admin"):
        for token in auth_cfg[role]:
            prev = token_role.get(token)
            if prev is None or ROLE_RANK[role] > ROLE_RANK[prev]:
                token_role[token] = role

    return token_role


# ─── Engine ───────────────────────────────────────────────────────────────────
class OmniscienceEngine:
    def __init__(self, vault_path: str):
        self.vault = Path(vault_path).resolve()
        self.db_path = str(self.vault.parent / DB_DIR)
        self.indexed_at: datetime | None = None

        print("\n🧠 Omniscience Engine")
        print(f"   Vault : {self.vault}")
        print(f"   DB    : {self.db_path}")
        print(f"   Model : {MODEL_NAME}")

        print("   Loading embedding model (first run downloads ~130MB)...")
        self.model = SentenceTransformer(MODEL_NAME)
        print("   ✅ Model ready.\n")

        self.db = lancedb.connect(self.db_path)
        self.table = self._ensure_table()

    def _ensure_table(self):
        names = set(self.db.table_names())
        if TABLE_NAME not in names:
            return self.db.create_table(TABLE_NAME, schema=SCHEMA)

        table = self.db.open_table(TABLE_NAME)
        existing_fields = [field.name for field in table.schema]
        expected_fields = [field.name for field in SCHEMA]

        if existing_fields == expected_fields:
            return table

        print("⚠️  Existing table schema is outdated. Recreating table from markdown source...")
        self.db.drop_table(TABLE_NAME)
        return self.db.create_table(TABLE_NAME, schema=SCHEMA)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, show_progress_bar=False).tolist()

    def index_file(self, file_path: Path, quiet: bool = False) -> int:
        rel = str(file_path.relative_to(self.vault))
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        chunks = chunk_text(content)
        if not chunks:
            return 0

        vectors = self.embed(chunks)
        tags = extract_tags(content)
        now = datetime.utcnow().isoformat()
        namespace = infer_namespace(rel)

        source = "user_note"
        if rel.lower().startswith("archive/"):
            source = "captured"

        safe_rel = rel.replace("'", "''")
        try:
            self.table.delete(f"path = '{safe_rel}'")
        except Exception:
            pass

        rows = [
            {
                "id": chunk_id(rel, i),
                "path": rel,
                "chunk_index": i,
                "text": chunk,
                "tags": tags,
                "namespace": namespace,
                "source": source,
                "vector": vec,
                "indexed_at": now,
            }
            for i, (chunk, vec) in enumerate(zip(chunks, vectors))
        ]

        self.table.add(rows)
        if not quiet:
            print(f"  📄 {rel} → {len(chunks)} chunks [{namespace}]")
        return len(chunks)

    def index_all(self):
        files = vault_md_files(self.vault)
        total = 0
        print(f"🔍 Indexing {len(files)} files...\n")
        for file_path in files:
            total += self.index_file(file_path)

        self.indexed_at = datetime.utcnow()
        print(f"\n✅ Done. {len(files)} files → {total} chunks in LanceDB.\n")
        self._update_dashboard(len(files), total)

    def _row_matches_filters(
        self,
        row: dict[str, Any],
        namespaces: set[str] | None,
        tags: set[str] | None,
        path_prefix: str | None,
    ) -> bool:
        if namespaces and str(row.get("namespace", "")) not in namespaces:
            return False

        if tags:
            row_tags = {t.lower() for t in str(row.get("tags", "")).split() if t.strip()}
            if not (row_tags & tags):
                return False

        if path_prefix:
            rp = str(row.get("path", "")).lower()
            if not rp.startswith(path_prefix.lower()):
                return False

        return True

    def search(
        self,
        query: str,
        top_k: int = 5,
        namespaces: list[str] | None = None,
        tags: list[str] | None = None,
        path_prefix: str | None = None,
    ) -> list[dict[str, Any]]:
        vec = self.embed([query])[0]
        fetch_k = max(top_k, top_k * 4)

        rows = (
            self.table.search(vec)
            .limit(fetch_k)
            .select(["path", "chunk_index", "text", "tags", "namespace", "source"])
            .to_list()
        )

        ns_set = {slug(x) for x in namespaces} if namespaces else None
        tag_set = {slug(x) for x in tags} if tags else None

        filtered = [r for r in rows if self._row_matches_filters(r, ns_set, tag_set, path_prefix)]
        return filtered[:top_k]

    def capture(self, req: CaptureRequest) -> dict[str, Any]:
        archive_dir = self.vault / "Archive"
        archive_dir.mkdir(parents=True, exist_ok=True)

        namespace = slug(req.namespace)
        tag = slug(req.tag)
        source = slug(req.source)

        if req.file_name:
            base = slug(req.file_name)
            file_name = f"{base}.md" if not base.endswith(".md") else base
        else:
            date_stamp = datetime.utcnow().strftime("%Y-%m-%d")
            file_name = f"capture-{date_stamp}.md"

        target = archive_dir / file_name
        now_iso = datetime.utcnow().isoformat()

        entry = f"- [{now_iso}] #{tag} [namespace={namespace}] [source={source}] — {req.text}\n"
        with open(target, "a", encoding="utf-8") as f:
            f.write(entry)

        self.index_file(target, quiet=True)

        return {
            "status": "captured",
            "file": str(target),
            "namespace": namespace,
            "tag": tag,
            "source": source,
            "timestamp": now_iso,
        }

    def stats(self) -> dict[str, Any]:
        files = vault_md_files(self.vault)
        rows = self.table.count_rows()
        auth_cfg = load_auth_config()
        token_roles = build_token_roles(auth_cfg)

        return {
            "status": "online",
            "vault": str(self.vault),
            "files": len(files),
            "lancedb_rows": rows,
            "last_indexed": self.indexed_at.isoformat() if self.indexed_at else "never",
            "auth_enabled": bool(token_roles),
        }

    def _update_dashboard(self, file_count: int, chunk_count: int):
        dash = self.vault / "DASHBOARD.md"
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            "# 🧠 Omniscience Engine — Dashboard",
            "",
            "**Status**: 🟢 Online",
            f"**Last Indexed**: {now}",
            f"**Files Indexed**: {file_count}",
            f"**LanceDB Vectors**: {chunk_count}",
            "",
            "---",
            "",
            "## Quick Search",
            "POST `/search` with JSON body: `{\"query\":\"...\",\"k\":5}`",
            "",
            "## File Index",
        ]

        for file_path in vault_md_files(self.vault):
            rel = str(file_path.relative_to(self.vault))
            lines.append(f"- [[{rel.replace(chr(92), '/')}]]")

        dash.write_text("\n".join(lines), encoding="utf-8")


# ─── File Watcher ─────────────────────────────────────────────────────────────
class VaultWatcher(FileSystemEventHandler):
    def __init__(self, engine: OmniscienceEngine):
        self.engine = engine
        self._pending: set[str] = set()

    def _relevant(self, path: str) -> bool:
        p = Path(path)
        return p.suffix == ".md" and not any(part in IGNORED_DIRS for part in p.parts)

    def on_modified(self, event):
        if not event.is_directory and self._relevant(event.src_path):
            self._pending.add(event.src_path)

    def on_created(self, event):
        if not event.is_directory and self._relevant(event.src_path):
            self._pending.add(event.src_path)

    def flush(self):
        for path in list(self._pending):
            try:
                self.engine.index_file(Path(path))
            except Exception as exc:
                print(f"⚠️  {path}: {exc}")

        self._pending.clear()
        self.engine._update_dashboard(
            len(vault_md_files(self.engine.vault)),
            self.engine.table.count_rows(),
        )


# ─── FastAPI Server ───────────────────────────────────────────────────────────
def create_app(engine: OmniscienceEngine) -> FastAPI:
    app = FastAPI(title="Omniscience Engine", version="1.1.0")

    auth_cfg = load_auth_config()
    token_roles = build_token_roles(auth_cfg)

    def require_role(required: str, authorization: str | None):
        # Open mode when no auth keys are configured.
        if not token_roles:
            return

        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing bearer token")

        token = authorization.split(" ", 1)[1].strip()
        role = token_roles.get(token)
        if role is None:
            raise HTTPException(status_code=403, detail="Invalid API token")

        if ROLE_RANK[role] < ROLE_RANK[required]:
            raise HTTPException(status_code=403, detail="Insufficient role for endpoint")

    @app.get("/health")
    def health(authorization: str | None = Header(default=None, alias="Authorization")):
        require_role("read", authorization)
        return JSONResponse(engine.stats())

    @app.post("/search")
    def search(req: SearchRequest, authorization: str | None = Header(default=None, alias="Authorization")):
        require_role("read", authorization)
        results = engine.search(
            query=req.query,
            top_k=req.k,
            namespaces=req.namespaces,
            tags=req.tags,
            path_prefix=req.path_prefix,
        )
        return JSONResponse(
            {
                "query": req.query,
                "k": req.k,
                "filters": {
                    "namespaces": req.namespaces,
                    "tags": req.tags,
                    "path_prefix": req.path_prefix,
                },
                "results": results,
            }
        )

    @app.post("/capture")
    def capture(req: CaptureRequest, authorization: str | None = Header(default=None, alias="Authorization")):
        require_role("write", authorization)
        return JSONResponse(engine.capture(req))

    @app.post("/admin/reindex")
    def admin_reindex(authorization: str | None = Header(default=None, alias="Authorization")):
        require_role("admin", authorization)

        def _run():
            engine.index_all()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return JSONResponse({"status": "started", "action": "reindex"})

    return app


# ─── CLI ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Omniscience Engine — Eternal Context for AI")
    parser.add_argument("--vault", default=DEFAULT_VAULT, help="Path to Obsidian vault")
    parser.add_argument("--watch", action="store_true", help="Watch vault + serve API")
    parser.add_argument("--reindex", action="store_true", help="Force full re-index")
    parser.add_argument("--search", type=str, help="Run a one-shot semantic search")
    parser.add_argument("--port", type=int, default=API_PORT, help="API port (default: 8765)")
    parser.add_argument("--host", default=API_HOST, help="API host (default: 127.0.0.1)")
    args = parser.parse_args()

    engine = OmniscienceEngine(args.vault)

    if args.search:
        if engine.table.count_rows() == 0:
            engine.index_all()

        results = engine.search(args.search)
        print(f"\n🔎 '{args.search}'\n")
        for result in results:
            print(
                f"  📄 {result['path']} [chunk {result['chunk_index']}] "
                f"[{result.get('namespace', 'default')}]"
            )
            print(f"     {result['text'][:200]}\n")
        return

    if args.reindex or engine.table.count_rows() == 0:
        engine.index_all()

    if args.watch:
        watcher = VaultWatcher(engine)
        observer = Observer()
        observer.schedule(watcher, str(engine.vault), recursive=True)
        observer.start()

        print("👁️  Watching vault for changes...")
        print(f"🌐  API running at http://{args.host}:{args.port}\n")

        app = create_app(engine)
        try:
            uvicorn_thread = threading.Thread(
                target=uvicorn.run,
                kwargs={"app": app, "host": args.host, "port": args.port, "log_level": "error"},
                daemon=True,
            )
            uvicorn_thread.start()
            while True:
                time.sleep(3)
                watcher.flush()
        except KeyboardInterrupt:
            observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
