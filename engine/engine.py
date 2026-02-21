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

API Endpoints (runs on http://localhost:8765):
  GET /search?q=<query>&k=<top_k>   → returns top-k matching context chunks
  GET /health                        → returns engine status + index stats
  POST /capture                      → manually store a memory

Requirements:
  pip install -r requirements.txt
"""

import argparse
import hashlib
import os
import time
from datetime import datetime
from pathlib import Path

import lancedb
import pyarrow as pa
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sentence_transformers import SentenceTransformer
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# ─── Config ───────────────────────────────────────────────────────────────────
DEFAULT_VAULT    = "./vault"
DB_DIR           = ".lancedb"
TABLE_NAME       = "context"
MODEL_NAME       = "BAAI/bge-small-en-v1.5"  # Free, local, 130MB
EMBED_DIM        = 384
CHUNK_SIZE       = 500
CHUNK_OVERLAP    = 80
API_PORT         = 8765
IGNORED_DIRS     = {".lancedb", ".obsidian", ".git", "__pycache__", "venv", "node_modules"}

SCHEMA = pa.schema([
    pa.field("id",          pa.string()),
    pa.field("path",        pa.string()),
    pa.field("chunk_index", pa.int32()),
    pa.field("text",        pa.string()),
    pa.field("tags",        pa.string()),           # space-separated tags from frontmatter
    pa.field("vector",      pa.list_(pa.float32(), EMBED_DIM)),
    pa.field("indexed_at",  pa.string()),
])

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
    """Extract #tags from markdown frontmatter or body."""
    import re
    tags = re.findall(r"#([a-zA-Z0-9_-]+)", text)
    return " ".join(set(tags))


def chunk_id(rel_path: str, idx: int) -> str:
    return hashlib.sha256(f"{rel_path}:{idx}".encode()).hexdigest()[:16]


def vault_md_files(vault: Path) -> list[Path]:
    result = []
    for root, dirs, files in os.walk(vault):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        for f in files:
            if f.endswith(".md"):
                result.append(Path(root) / f)
    return result


# ─── Engine ───────────────────────────────────────────────────────────────────
class OmniscienceEngine:
    def __init__(self, vault_path: str):
        self.vault      = Path(vault_path).resolve()
        self.db_path    = str(self.vault.parent / DB_DIR)
        self.indexed_at = None

        print(f"\n🧠 Omniscience Engine")
        print(f"   Vault : {self.vault}")
        print(f"   DB    : {self.db_path}")
        print(f"   Model : {MODEL_NAME}")

        print("   Loading embedding model (first run downloads ~130MB)...")
        self.model = SentenceTransformer(MODEL_NAME)
        print("   ✅ Model ready.\n")

        self.db = lancedb.connect(self.db_path)
        if TABLE_NAME not in self.db.table_names():
            self.table = self.db.create_table(TABLE_NAME, schema=SCHEMA)
        else:
            self.table = self.db.open_table(TABLE_NAME)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, show_progress_bar=False).tolist()

    def index_file(self, file_path: Path, quiet=False):
        rel     = str(file_path.relative_to(self.vault))
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        chunks  = chunk_text(content)
        if not chunks:
            return 0

        vectors = self.embed(chunks)
        tags    = extract_tags(content)
        now     = datetime.utcnow().isoformat()

        try:
            self.table.delete(f"path = '{rel}'")
        except Exception:
            pass

        rows = [
            {
                "id":          chunk_id(rel, i),
                "path":        rel,
                "chunk_index": i,
                "text":        chunk,
                "tags":        tags,
                "vector":      vec,
                "indexed_at":  now,
            }
            for i, (chunk, vec) in enumerate(zip(chunks, vectors))
        ]
        self.table.add(rows)
        if not quiet:
            print(f"  📄 {rel} → {len(chunks)} chunks")
        return len(chunks)

    def index_all(self):
        files   = vault_md_files(self.vault)
        total   = 0
        print(f"🔍 Indexing {len(files)} files...\n")
        for f in files:
            total += self.index_file(f)
        self.indexed_at = datetime.utcnow()
        print(f"\n✅ Done. {len(files)} files → {total} chunks in LanceDB.\n")
        self._update_dashboard(len(files), total)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        vec     = self.embed([query])[0]
        results = (
            self.table.search(vec)
            .limit(top_k)
            .select(["path", "chunk_index", "text", "tags"])
            .to_list()
        )
        return results

    def capture(self, text: str, tag: str = "captured"):
        """Capture a raw memory string directly into the vault and index."""
        ts       = datetime.utcnow().strftime("%Y-%m-%d")
        fname    = self.vault / "Archive" / f"capture-{ts}.md"
        entry    = f"\n- [{datetime.utcnow().isoformat()}] #{tag} — {text}\n"
        with open(fname, "a", encoding="utf-8") as f:
            f.write(entry)
        self.index_file(fname, quiet=True)
        return {"status": "captured", "file": str(fname)}

    def stats(self) -> dict:
        files = vault_md_files(self.vault)
        rows  = self.table.count_rows()
        return {
            "status":      "online",
            "vault":       str(self.vault),
            "files":       len(files),
            "lancedb_rows": rows,
            "last_indexed": self.indexed_at.isoformat() if self.indexed_at else "never",
        }

    def _update_dashboard(self, file_count: int, chunk_count: int):
        dash  = self.vault / "DASHBOARD.md"
        now   = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            "# 🧠 Omniscience Engine — Dashboard",
            "",
            f"**Status**: 🟢 Online",
            f"**Last Indexed**: {now}",
            f"**Files Indexed**: {file_count}",
            f"**LanceDB Vectors**: {chunk_count}",
            "",
            "---",
            "",
            "## Quick Search",
            "Use the engine API: `http://localhost:8765/search?q=your+query`",
            "",
            "## File Index",
        ]
        for f in vault_md_files(self.vault):
            rel = str(f.relative_to(self.vault))
            lines.append(f"- [[{rel.replace(chr(92), '/')}]]")
        dash.write_text("\n".join(lines), encoding="utf-8")


# ─── File Watcher ─────────────────────────────────────────────────────────────
class VaultWatcher(FileSystemEventHandler):
    def __init__(self, engine: OmniscienceEngine):
        self.engine   = engine
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
            except Exception as e:
                print(f"⚠️  {path}: {e}")
        self._pending.clear()
        self.engine._update_dashboard(
            len(vault_md_files(self.engine.vault)),
            self.engine.table.count_rows(),
        )


# ─── FastAPI Server ────────────────────────────────────────────────────────────
def create_app(engine: OmniscienceEngine) -> FastAPI:
    app = FastAPI(title="Omniscience Engine", version="1.0.0")

    @app.get("/health")
    def health():
        return JSONResponse(engine.stats())

    @app.get("/search")
    def search(q: str, k: int = 5):
        results = engine.search(q, k)
        return JSONResponse({"query": q, "results": results})

    @app.post("/capture")
    def capture(text: str, tag: str = "captured"):
        return JSONResponse(engine.capture(text, tag))

    return app


# ─── CLI ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Omniscience Engine — Eternal Context for AI")
    parser.add_argument("--vault",   default=DEFAULT_VAULT, help="Path to Obsidian vault")
    parser.add_argument("--watch",   action="store_true",   help="Watch vault + serve API")
    parser.add_argument("--reindex", action="store_true",   help="Force full re-index")
    parser.add_argument("--search",  type=str,              help="Run a one-shot semantic search")
    parser.add_argument("--port",    type=int, default=API_PORT, help="API port (default: 8765)")
    args = parser.parse_args()

    engine = OmniscienceEngine(args.vault)

    if args.search:
        if engine.table.count_rows() == 0:
            engine.index_all()
        results = engine.search(args.search)
        print(f"\n🔎 '{args.search}'\n")
        for r in results:
            print(f"  📄 {r['path']} [chunk {r['chunk_index']}]")
            print(f"     {r['text'][:200]}\n")
        return

    if args.reindex or engine.table.count_rows() == 0:
        engine.index_all()

    if args.watch:
        watcher  = VaultWatcher(engine)
        observer = Observer()
        observer.schedule(watcher, str(engine.vault), recursive=True)
        observer.start()
        print(f"👁️  Watching vault for changes...")
        print(f"🌐  API running at http://localhost:{args.port}\n")
        app = create_app(engine)
        try:
            uvicorn_thread = __import__("threading").Thread(
                target=uvicorn.run,
                kwargs={"app": app, "host": "127.0.0.1", "port": args.port, "log_level": "error"},
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
