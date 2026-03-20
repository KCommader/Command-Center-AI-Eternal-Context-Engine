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
  POST /search/grounded
  GET  /policy/grounding
  POST /capture
  POST /admin/reindex
  POST /admin/cleanup

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
import json
import math
import os
import re
import threading
import time
from collections import OrderedDict, deque
from datetime import datetime
from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa
import uvicorn
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sentence_transformers import CrossEncoder, SentenceTransformer
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# BM25 — optional but strongly recommended. Installed via requirements.txt.
# When present, search_with_grounding retrieves candidates from both vector
# and keyword paths, then merges before the reranker sees them.
try:
    from rank_bm25 import BM25Okapi as _BM25Okapi
    _BM25_AVAILABLE = True
except ImportError:
    _BM25_AVAILABLE = False
    _BM25Okapi = None  # type: ignore[assignment,misc]

# Memory tier classifier (local module)
try:
    from memory_classifier import classify, write_to_tier, MemoryTier
    _CLASSIFIER_AVAILABLE = True
except ImportError:
    _CLASSIFIER_AVAILABLE = False

# ─── Config ───────────────────────────────────────────────────────────────────
DEFAULT_VAULT = "./vault"
DB_DIR = ".lancedb"
TABLE_NAME = "context"
MODEL_NAME = "BAAI/bge-small-en-v1.5"  # local model, first run downloads once
EMBED_DIM = 384
# ── Smart Markdown chunking ───────────────────────────────────────────────────
# Replaces fixed 500-char sliding window. Chunks now respect Markdown structure:
# sections split on headings, code blocks kept whole, heading breadcrumbs
# carried into every child chunk so the reranker knows which section it's in.
CHUNK_MAX_CHARS = int(os.getenv("OMNI_CHUNK_MAX_CHARS", "1500"))
CHUNK_MIN_CHARS = int(os.getenv("OMNI_CHUNK_MIN_CHARS", "80"))
API_PORT = 8765
API_HOST = "127.0.0.1"
IGNORED_DIRS = {".lancedb", ".obsidian", ".git", "__pycache__", "venv", ".venv", "node_modules"}
RUNTIME_DIR_NAME = ".omniscience"
INDEX_MANIFEST_FILE = "index_manifest.json"
QUERY_CACHE_TTL_SEC = int(os.getenv("OMNI_QUERY_CACHE_TTL_SEC", "3600"))
QUERY_CACHE_MAX_ITEMS = int(os.getenv("OMNI_QUERY_CACHE_MAX_ITEMS", "256"))
TMP_FILE_TTL_SEC = int(os.getenv("OMNI_TMP_TTL_SEC", str(48 * 3600)))
TMP_MAX_FILES = int(os.getenv("OMNI_TMP_MAX_FILES", "400"))
LOG_MAX_BYTES = int(os.getenv("OMNI_LOG_MAX_BYTES", str(5 * 1024 * 1024)))


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name, "1" if default else "0").strip().lower()
    return raw not in {"0", "false", "no", "off", ""}


DEFAULT_SEARCH_MODE = os.getenv("OMNI_DEFAULT_SEARCH_MODE", "balanced").strip().lower() or "balanced"
GROUNDING_MIN_SIMILARITY_STRICT = float(os.getenv("OMNI_MIN_SIMILARITY_STRICT", "0.42"))
GROUNDING_MIN_SIMILARITY_BALANCED = float(os.getenv("OMNI_MIN_SIMILARITY_BALANCED", "0.28"))
GROUNDING_MIN_SIMILARITY_EXPLORATORY = float(os.getenv("OMNI_MIN_SIMILARITY_EXPLORATORY", "0.16"))
GROUNDING_MIN_QUERY_TERM_COVERAGE_STRICT = float(os.getenv("OMNI_MIN_QUERY_TERM_COVERAGE_STRICT", "0.12"))
GROUNDING_MIN_QUERY_TERM_COVERAGE_BALANCED = float(os.getenv("OMNI_MIN_QUERY_TERM_COVERAGE_BALANCED", "0.06"))
GROUNDING_MIN_QUERY_TERM_COVERAGE_EXPLORATORY = float(
    os.getenv("OMNI_MIN_QUERY_TERM_COVERAGE_EXPLORATORY", "0.00")
)
LEXICAL_MIN_TOKEN_LEN = int(os.getenv("OMNI_LEXICAL_MIN_TOKEN_LEN", "4"))
RERANK_ENABLED = _env_flag("OMNI_RERANK_ENABLED", True)
RERANK_MODEL_NAME = os.getenv("OMNI_RERANK_MODEL_NAME", "cross-encoder/ms-marco-MiniLM-L-6-v2").strip()
RERANK_CANDIDATES = int(os.getenv("OMNI_RERANK_CANDIDATES", "36"))
RERANK_BATCH_SIZE = int(os.getenv("OMNI_RERANK_BATCH_SIZE", "16"))
ENFORCE_ANSWER_CONTRACT_DEFAULT = _env_flag("OMNI_ENFORCE_ANSWER_CONTRACT", True)

# ── BM25 hybrid search ────────────────────────────────────────────────────────
# Vector retrieval is strong on semantics; BM25 is strong on exact keywords.
# Combining both before the reranker gives the best of both paths.
BM25_ENABLED = _env_flag("OMNI_BM25_ENABLED", True)
BM25_CANDIDATES = int(os.getenv("OMNI_BM25_CANDIDATES", "40"))  # BM25-only candidates to fetch

# ── Query expansion ───────────────────────────────────────────────────────────
# Before searching, expand the query with semantically related terms from the
# vault's own vocabulary. This catches cases where the user's wording doesn't
# match the stored text at all — neither vector nor BM25 can help without it.
# Uses the embedding model (no LLM, no cloud call, no extra dependency).
QUERY_EXPANSION_ENABLED = _env_flag("OMNI_QUERY_EXPANSION_ENABLED", True)
QUERY_EXPANSION_TERMS = int(os.getenv("OMNI_QUERY_EXPANSION_TERMS", "5"))

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "what",
    "when",
    "where",
    "which",
    "who",
    "will",
    "with",
}
def _slug_for_config(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip().lower())
    return cleaned.strip("_") or "default"


def _namespace_set_from_env(name: str, default: str) -> set[str]:
    return {
        _slug_for_config(x)
        for x in os.getenv(name, default).split(",")
        if x.strip()
    }


TRUSTED_NAMESPACES = _namespace_set_from_env(
    "OMNI_TRUSTED_NAMESPACES",
    "company_core,company_memory,knowledge,projects,legal_ip,bots_runtime",
)
LOW_TRUST_NAMESPACES = _namespace_set_from_env(
    "OMNI_LOW_TRUST_NAMESPACES",
    "raw_chats,chat_imports,inbox,scratch,system_runtime,dashboard_md",
)

# ── Privacy namespaces ─────────────────────────────────────────────────────────
# Namespaces listed here are hard-excluded from all default searches.
# vault/Local/ is always private. Add your own via OMNI_PRIVATE_NAMESPACES:
#   OMNI_PRIVATE_NAMESPACES=local_only,diary,medical
# Cloud AIs never see these unless a query explicitly includes the namespace.
PRIVATE_NAMESPACES = _namespace_set_from_env(
    "OMNI_PRIVATE_NAMESPACES",
    "local_only",
)

# ── Store safety ───────────────────────────────────────────────────────────────
# Rate limiter: max writes per minute per source/agent. Prevents vault flooding.
# Dedup: skip storing content that is near-identical to something already indexed.
STORE_RATE_LIMIT = int(os.getenv("OMNI_STORE_RATE_LIMIT", "30"))          # writes/min
STORE_DEDUP_THRESHOLD = float(os.getenv("OMNI_STORE_DEDUP_THRESHOLD", "0.92"))  # 0.0–1.0

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
    exclude_namespaces: list[str] | None = None
    tags: list[str] | None = None
    path_prefix: str | None = None
    mode: str = Field(default=DEFAULT_SEARCH_MODE)
    trusted_only: bool = False
    min_similarity: float | None = Field(default=None, ge=0.0, le=1.0)
    require_grounded: bool = False
    enforce_contract: bool | None = None


class CaptureRequest(BaseModel):
    text: str = Field(min_length=1)
    tag: str = "captured"
    namespace: str = "company_memory"
    source: str = "manual"
    file_name: str | None = None


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _extract_frontmatter(text: str) -> tuple[str, str]:
    """Split YAML frontmatter from body. Returns (frontmatter_block, body)."""
    if not text.startswith("---"):
        return "", text
    end = text.find("\n---", 3)
    if end == -1:
        return "", text
    fm = text[: end + 4].strip()
    body = text[end + 4 :].lstrip("\n")
    return fm, body


def _heading_level(line: str) -> int:
    """Return ATX heading level (1–6) or 0 if the line is not a heading."""
    m = re.match(r"^(#{1,6})\s", line)
    return len(m.group(1)) if m else 0


def _split_into_sections(body: str) -> list[dict[str, str]]:
    """Walk the document and group lines into heading-delimited sections.

    Each section is a dict with:
      heading  — breadcrumb string built from the parent heading chain,
                 e.g. "## Config > ### Auth Tokens"
      content  — the raw lines of the section (heading line included)

    Code fences are tracked so headings inside a fenced block are ignored.
    """
    sections: list[dict[str, str]] = []
    heading_stack: list[tuple[int, str]] = []   # [(level, text), ...]
    current_heading: str = ""
    current_lines: list[str] = []
    in_code_block: bool = False

    def _flush() -> None:
        content = "\n".join(current_lines).strip()
        if content:
            sections.append({"heading": current_heading, "content": content})

    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block

        level = 0 if in_code_block else _heading_level(line)

        if level > 0:
            _flush()
            current_lines = []
            # Trim stack to ancestors only, then push the new heading.
            heading_stack = [(lvl, txt) for lvl, txt in heading_stack if lvl < level]
            heading_stack.append((level, line.lstrip("#").strip()))
            # Build breadcrumb: "## H2 > ### H3"
            current_heading = " > ".join(
                f"{'#' * lvl} {txt}" for lvl, txt in heading_stack
            )
            current_lines.append(line)   # keep the heading itself in the chunk
        else:
            current_lines.append(line)

    _flush()
    return sections


def _split_on_paragraphs(text: str, prefix: str) -> list[str]:
    """Split text on blank-line paragraph boundaries, greedy-merging up to
    CHUNK_MAX_CHARS, and prepend prefix to every resulting chunk.

    Code fences are kept intact — a blank line inside a fence is not a split.
    """
    paragraphs: list[str] = []
    current: list[str] = []
    in_code = False

    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
        if not in_code and line.strip() == "" and current:
            para = "\n".join(current).strip()
            if para:
                paragraphs.append(para)
            current = []
        else:
            current.append(line)

    if current:
        para = "\n".join(current).strip()
        if para:
            paragraphs.append(para)

    if not paragraphs:
        return [text] if len(text.strip()) >= CHUNK_MIN_CHARS else []

    # Greedily merge paragraphs into chunks that stay under CHUNK_MAX_CHARS.
    chunks: list[str] = []
    bucket: list[str] = []
    bucket_len = len(prefix)

    for para in paragraphs:
        addition = len(para) + 2   # +2 for the "\n\n" separator
        if bucket and (bucket_len + addition) > CHUNK_MAX_CHARS:
            chunks.append((prefix + "\n\n".join(bucket)).strip())
            bucket = []
            bucket_len = len(prefix)
        bucket.append(para)
        bucket_len += addition

    if bucket:
        chunks.append((prefix + "\n\n".join(bucket)).strip())

    return [c for c in chunks if len(c.strip()) >= CHUNK_MIN_CHARS]


def chunk_markdown(text: str) -> list[str]:
    """Smart Markdown-aware chunker. Replaces the old fixed sliding window.

    Algorithm:
    1. Strip YAML frontmatter and attach it as a preamble to the first chunk.
    2. Walk the document splitting on ATX headings (# / ## / ###).
       Code fences are treated as atomic — headings inside them are ignored.
    3. For each section that fits within CHUNK_MAX_CHARS, emit as one chunk
       with the heading breadcrumb prepended for reranker context.
    4. Oversized sections are split further on blank-line paragraph boundaries,
       still carrying the heading breadcrumb on every sub-chunk.
    5. Files with no headings fall back to paragraph-based splitting.

    Result: chunks that are semantically coherent, context-annotated, and
    never artificially cut mid-sentence or mid-code-block.
    """
    if not text or not text.strip():
        return []

    frontmatter, body = _extract_frontmatter(text)
    sections = _split_into_sections(body)

    chunks: list[str] = []

    def _attach_frontmatter(chunk: str) -> str:
        if frontmatter and not chunks:
            return (frontmatter + "\n\n" + chunk).strip()
        return chunk

    if not sections:
        # No headings — paragraph-split the whole body.
        raw = _split_on_paragraphs(body.strip(), "")
        if raw:
            raw[0] = _attach_frontmatter(raw[0])
        return raw

    for section in sections:
        heading_crumb = section["heading"]
        content = section["content"]
        prefix = f"{heading_crumb}\n\n" if heading_crumb else ""
        full = (prefix + content).strip()

        if not full or len(full) < CHUNK_MIN_CHARS:
            continue

        if len(full) <= CHUNK_MAX_CHARS:
            chunks.append(_attach_frontmatter(full))
        else:
            sub = _split_on_paragraphs(content, prefix)
            if sub:
                sub[0] = _attach_frontmatter(sub[0])
            chunks.extend(sub)

    return [c for c in chunks if len(c.strip()) >= CHUNK_MIN_CHARS]


# Keep the old name as an alias so any external callers still work.
chunk_text = chunk_markdown


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
    if rel == "dashboard.md":
        return "system_runtime"
    if rel.startswith("archive/chats") or rel.startswith("archive/conversations"):
        return "raw_chats"
    if rel.startswith("imports/chats") or rel.startswith("inbox/chats"):
        return "chat_imports"
    if rel.startswith("knowledge/tradingbooks"):
        return "books_trading"
    if rel.startswith("projects/tradingbots"):
        return "bots_runtime"
    if rel.startswith("knowledge/"):
        return "knowledge"
    if rel.startswith("projects/"):
        return "projects"
    if rel.startswith("legal/"):
        return "legal_ip"
    if rel.startswith("core/"):
        return "company_core"
    if rel.startswith("archive/"):
        return "company_memory"
    # vault/Local/ — private namespace, excluded from all default searches.
    # Used for local-LLM-only content, personal notes, anything that should
    # never reach a cloud AI. See OMNI_PRIVATE_NAMESPACES config.
    if rel.startswith("local/"):
        return "local_only"

    # Per-agent private namespaces. Files under agents/{agent_id}/ are indexed
    # under agent_{agent_id} and only surface in searches that include that
    # namespace — keeping each agent's private memory isolated from the shared vault.
    if rel.startswith("agents/"):
        parts = Path(rel).parts
        agent_id = slug(parts[1]) if len(parts) > 1 else "default"
        return f"agent_{agent_id}"

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
        self.runtime_dir = self.vault.parent / RUNTIME_DIR_NAME
        self.tmp_dir = self.runtime_dir / "tmp"
        self.log_file = self.runtime_dir / "engine.log"
        self.manifest_file = self.runtime_dir / INDEX_MANIFEST_FILE
        self.indexed_at: datetime | None = None
        self._query_cache: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self._manifest: dict[str, dict[str, Any]] = {}
        self._cleanup_counter = 0

        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self._manifest = self._load_manifest()
        self._cleanup_runtime_files()

        print("\n🧠 Omniscience Engine")
        print(f"   Vault : {self.vault}")
        print(f"   DB    : {self.db_path}")
        print(f"   Model : {MODEL_NAME}")

        print("   Loading embedding model (first run downloads ~130MB)...")
        self.model = SentenceTransformer(MODEL_NAME)
        print("   ✅ Model ready.\n")

        self.reranker: CrossEncoder | None = None
        if RERANK_ENABLED and RERANK_MODEL_NAME:
            try:
                print(f"   Loading reranker model ({RERANK_MODEL_NAME})...")
                self.reranker = CrossEncoder(RERANK_MODEL_NAME)
                print("   ✅ Reranker ready.\n")
            except Exception as exc:
                print(f"   ⚠️  Reranker disabled ({exc})\n")
        else:
            print("   Reranker disabled by config.\n")

        # BM25 index — built lazily after first index_all() or vault change.
        # _bm25_dirty flags that the corpus has changed and needs a rebuild
        # before the next search. This avoids rebuilding on every file event.
        self._bm25: Any = None
        self._bm25_ids: list[str] = []
        self._bm25_dirty: bool = True

        # Store safety: per-source rate limit windows and dedup state.
        self._store_rate_window: dict[str, list[float]] = {}

        # Query expansion: vocabulary embedding index — built alongside BM25.
        self._vocab_tokens: list[str] = []
        self._vocab_embeddings: Any = None  # numpy array (n_tokens, embed_dim)

        self.db = lancedb.connect(self.db_path)
        self.table = self._ensure_table()

    def _load_manifest(self) -> dict[str, dict[str, Any]]:
        if not self.manifest_file.exists():
            return {}
        try:
            data = json.loads(self.manifest_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {}

    def _save_manifest(self) -> None:
        tmp = self.manifest_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._manifest, indent=2), encoding="utf-8")
        tmp.replace(self.manifest_file)

    def _prune_manifest(self) -> None:
        keep: dict[str, dict[str, Any]] = {}
        for rel, meta in self._manifest.items():
            if (self.vault / rel).exists():
                keep[rel] = meta
        self._manifest = keep

    def _content_hash(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()

    def _normalize_filters(
        self,
        namespaces: list[str] | None,
        tags: list[str] | None,
        path_prefix: str | None,
    ) -> tuple[tuple[str, ...], tuple[str, ...], str]:
        ns = tuple(sorted(slug(x) for x in namespaces)) if namespaces else ()
        tg = tuple(sorted(slug(x) for x in tags)) if tags else ()
        pp = (path_prefix or "").strip().lower()
        return ns, tg, pp

    def _query_cache_key(
        self,
        query: str,
        top_k: int,
        namespaces: list[str] | None,
        exclude_namespaces: list[str] | None,
        tags: list[str] | None,
        path_prefix: str | None,
        mode: str,
        trusted_only: bool,
        min_similarity: float | None,
        require_grounded: bool,
        enforce_contract: bool,
    ) -> str:
        ns, tg, pp = self._normalize_filters(namespaces, tags, path_prefix)
        ex, _, _ = self._normalize_filters(exclude_namespaces, None, None)
        payload = json.dumps(
            {
                "q": query.strip(),
                "k": top_k,
                "ns": ns,
                "ex": ex,
                "tags": tg,
                "pp": pp,
                "mode": mode,
                "trusted_only": trusted_only,
                "min_similarity": min_similarity,
                "require_grounded": require_grounded,
                "enforce_contract": enforce_contract,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _query_cache_get(self, key: str) -> dict[str, Any] | None:
        now = time.time()
        hit = self._query_cache.get(key)
        if hit is None:
            return None
        ts, payload = hit
        if (now - ts) > QUERY_CACHE_TTL_SEC:
            self._query_cache.pop(key, None)
            return None
        self._query_cache.move_to_end(key)
        return payload

    def _query_cache_set(self, key: str, payload: dict[str, Any]) -> None:
        self._query_cache[key] = (time.time(), payload)
        self._query_cache.move_to_end(key)
        while len(self._query_cache) > QUERY_CACHE_MAX_ITEMS:
            self._query_cache.popitem(last=False)

    def _invalidate_query_cache(self) -> None:
        self._query_cache.clear()
        self._bm25_dirty = True  # corpus may have changed — rebuild before next search

    # ── BM25 hybrid index ──────────────────────────────────────────────────────

    def _rebuild_bm25_index(self) -> None:
        """Build a BM25 index from all chunks currently in LanceDB.

        Called lazily before the first search after any vault change. For
        personal vaults (~hundreds to low thousands of chunks) this takes
        under a second. The index lives in memory only — nothing written to disk.
        """
        if not BM25_ENABLED or not _BM25_AVAILABLE:
            return
        try:
            df = self.table.to_pandas()[["id", "text"]]
            if df.empty:
                return
            corpus = [list(self._tokenize_for_overlap(str(t))) for t in df["text"]]
            self._bm25_ids = df["id"].tolist()
            self._bm25 = _BM25Okapi(corpus)
        except Exception as exc:
            print(f"   ⚠️  BM25 index build failed ({exc})")
            self._bm25 = None
            self._bm25_ids = []

    def _ensure_bm25_fresh(self) -> None:
        """Rebuild BM25 + vocab indexes if the corpus has changed since last build."""
        if self._bm25_dirty:
            self._rebuild_bm25_index()
            self._rebuild_vocab_index()
            self._bm25_dirty = False

    def _bm25_candidate_ids(self, query: str, k: int) -> list[str]:
        """Return chunk IDs of the top-k BM25 matches for query.

        Only returns IDs with a BM25 score above zero — chunks with no
        query term overlap are excluded regardless of k.
        """
        if self._bm25 is None or not self._bm25_ids:
            return []
        tokens = list(self._tokenize_for_overlap(query))
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        top_k = min(k, len(scores))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [self._bm25_ids[i] for i in ranked if scores[i] > 0]

    def _fetch_by_ids(self, ids: list[str]) -> list[dict[str, Any]]:
        """Fetch rows from LanceDB by chunk ID.

        Used to hydrate BM25-only candidates that the vector search didn't
        retrieve. These rows carry no _distance value — they're tagged as
        bm25-sourced so downstream filters treat them correctly.
        """
        if not ids:
            return []
        try:
            id_set = set(ids)
            cols = ["id", "path", "chunk_index", "text", "tags", "namespace", "source", "indexed_at"]
            df = self.table.to_pandas()[cols]
            rows = df[df["id"].isin(id_set)].to_dict("records")
            for row in rows:
                row["_distance"] = None       # no vector distance — BM25-sourced
                row["_retrieval_source"] = "bm25"
            return rows
        except Exception:
            return []

    # ── Query expansion ──────────────────────────────────────────────────────

    def _rebuild_vocab_index(self) -> None:
        """Build a vocabulary embedding index from all unique tokens in the vault.

        Each token that appears in the indexed corpus gets embedded once. The
        result is a small matrix: (n_tokens, embed_dim). On query, we embed
        the query, find the nearest tokens in this matrix, and append them to
        the query string. This catches vocabulary mismatches that neither
        vector search nor BM25 can solve alone.

        Built lazily alongside the BM25 index — same trigger, same lifecycle.
        """
        if not QUERY_EXPANSION_ENABLED:
            return
        try:
            df = self.table.to_pandas()["text"]
            # Collect unique tokens from the corpus
            all_tokens: set[str] = set()
            for text in df:
                all_tokens |= self._tokenize_for_overlap(str(text))
            # Filter to meaningful tokens (length > 3, not stopwords)
            vocab = sorted(t for t in all_tokens if len(t) > 3 and t not in STOPWORDS)
            if not vocab:
                self._vocab_tokens = []
                self._vocab_embeddings = None
                return
            # Cap at 5000 to keep embedding time reasonable
            if len(vocab) > 5000:
                vocab = vocab[:5000]
            self._vocab_tokens = vocab
            self._vocab_embeddings = self.embed(vocab)
        except Exception as exc:
            print(f"   ⚠️  Vocab index build failed ({exc})")
            self._vocab_tokens = []
            self._vocab_embeddings = None

    def _expand_query(self, query: str) -> str:
        """Expand a query with semantically related terms from the vault vocabulary.

        Embeds the query, finds the N nearest tokens in the vocabulary index,
        and appends them to the original query. The expanded query is used for
        both vector search and BM25 — broadening recall from both paths.

        Returns the expanded query string. If expansion is disabled or the
        vocabulary is empty, returns the original query unchanged.
        """
        if (
            not QUERY_EXPANSION_ENABLED
            or not self._vocab_tokens
            or self._vocab_embeddings is None
        ):
            return query

        try:
            import numpy as np

            q_vec = np.array(self.embed([query])[0])
            v_mat = np.array(self._vocab_embeddings)
            # Cosine similarity: dot product of normalized vectors
            q_norm = q_vec / (np.linalg.norm(q_vec) + 1e-9)
            v_norms = v_mat / (np.linalg.norm(v_mat, axis=1, keepdims=True) + 1e-9)
            sims = v_norms @ q_norm

            query_tokens = self._tokenize_for_overlap(query)
            top_indices = np.argsort(sims)[::-1]
            expansion_terms: list[str] = []
            for idx in top_indices:
                if len(expansion_terms) >= QUERY_EXPANSION_TERMS:
                    break
                token = self._vocab_tokens[idx]
                # Don't add tokens already in the query
                if token not in query_tokens:
                    expansion_terms.append(token)

            if expansion_terms:
                return query + " " + " ".join(expansion_terms)
        except Exception:
            pass
        return query

    def _trim_log_file(self) -> None:
        if not self.log_file.exists():
            return
        try:
            size = self.log_file.stat().st_size
            if size <= LOG_MAX_BYTES:
                return
            with self.log_file.open("rb") as fh:
                fh.seek(0, os.SEEK_END)
                end = fh.tell()
                start = max(0, end - LOG_MAX_BYTES)
                fh.seek(start, os.SEEK_SET)
                tail = fh.read()
            with self.log_file.open("wb") as fh:
                fh.write(tail)
        except Exception:
            pass

    def _cleanup_runtime_files(self) -> None:
        now = time.time()
        files: list[Path] = []
        for p in self.tmp_dir.rglob("*"):
            if p.is_file():
                files.append(p)

        # Age-based cleanup.
        for p in files:
            try:
                if (now - p.stat().st_mtime) > TMP_FILE_TTL_SEC:
                    p.unlink(missing_ok=True)
            except Exception:
                pass

        # Count-based cleanup.
        files = [p for p in self.tmp_dir.rglob("*") if p.is_file()]
        if len(files) > TMP_MAX_FILES:
            files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            for stale in files[TMP_MAX_FILES:]:
                try:
                    stale.unlink(missing_ok=True)
                except Exception:
                    pass

        self._trim_log_file()

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

    def index_file(
        self,
        file_path: Path,
        quiet: bool = False,
        force: bool = False,
        persist_manifest: bool = True,
        invalidate_cache: bool = True,
    ) -> int:
        rel = str(file_path.relative_to(self.vault))
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        content_hash = self._content_hash(content)

        existing = self._manifest.get(rel)
        if (not force) and existing and existing.get("content_hash") == content_hash:
            if not quiet:
                print(f"  ⏭️  {rel} unchanged (cache hit)")
            return int(existing.get("chunks", 0) or 0)

        chunks = chunk_markdown(content)
        if not chunks:
            safe_rel = rel.replace("'", "''")
            try:
                self.table.delete(f"path = '{safe_rel}'")
            except Exception:
                pass
            self._manifest.pop(rel, None)
            if persist_manifest:
                self._save_manifest()
            if invalidate_cache:
                self._invalidate_query_cache()
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
        self._manifest[rel] = {
            "content_hash": content_hash,
            "chunks": len(chunks),
            "namespace": namespace,
            "indexed_at": now,
        }
        if persist_manifest:
            self._save_manifest()
        if invalidate_cache:
            self._invalidate_query_cache()
        if not quiet:
            print(f"  📄 {rel} → {len(chunks)} chunks [{namespace}]")
        return len(chunks)

    def index_all(self, force: bool = False):
        files = vault_md_files(self.vault)
        total = 0
        print(f"🔍 Indexing {len(files)} files...\n")
        self._prune_manifest()
        for file_path in files:
            total += self.index_file(
                file_path,
                force=force,
                persist_manifest=False,
                invalidate_cache=False,
            )

        self.indexed_at = datetime.utcnow()
        self._save_manifest()
        self._invalidate_query_cache()
        self._cleanup_runtime_files()
        print(f"\n✅ Done. {len(files)} files → {total} chunks in LanceDB.\n")
        self._update_dashboard(len(files), total)
        # Build BM25 + vocab indexes now while the full corpus is warm in memory.
        # _invalidate_query_cache already set _bm25_dirty, but we build eagerly
        # here so the first search after startup doesn't pay the build cost.
        self._rebuild_bm25_index()
        self._rebuild_vocab_index()
        self._bm25_dirty = False

    def _row_matches_filters(
        self,
        row: dict[str, Any],
        namespaces: set[str] | None,
        exclude_namespaces: set[str] | None,
        tags: set[str] | None,
        path_prefix: str | None,
    ) -> bool:
        row_ns = slug(str(row.get("namespace", "")))
        if namespaces and row_ns not in namespaces:
            return False
        if exclude_namespaces and row_ns in exclude_namespaces:
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

    def _resolve_mode(self, mode: str) -> str:
        candidate = slug(mode or DEFAULT_SEARCH_MODE)
        if candidate not in {"strict", "balanced", "exploratory"}:
            return "balanced"
        return candidate

    def _resolve_min_similarity(self, mode: str, min_similarity: float | None) -> float:
        if min_similarity is not None:
            return max(0.0, min(1.0, float(min_similarity)))
        if mode == "strict":
            return GROUNDING_MIN_SIMILARITY_STRICT
        if mode == "exploratory":
            return GROUNDING_MIN_SIMILARITY_EXPLORATORY
        return GROUNDING_MIN_SIMILARITY_BALANCED

    def _distance_to_similarity(self, distance: Any) -> float:
        if distance is None:
            return 0.0
        try:
            d = abs(float(distance))
            return 1.0 / (1.0 + d)
        except Exception:
            return 0.0

    def _tokenize_for_overlap(self, text: str) -> set[str]:
        return {
            tok
            for tok in re.findall(r"[a-zA-Z0-9_]+", (text or "").lower())
            if len(tok) >= LEXICAL_MIN_TOKEN_LEN and tok not in STOPWORDS
        }

    def _resolve_min_query_term_coverage(self, mode: str) -> float:
        if mode == "strict":
            return GROUNDING_MIN_QUERY_TERM_COVERAGE_STRICT
        if mode == "exploratory":
            return GROUNDING_MIN_QUERY_TERM_COVERAGE_EXPLORATORY
        return GROUNDING_MIN_QUERY_TERM_COVERAGE_BALANCED

    def _normalize_rerank_score(self, score: float | None) -> float:
        if score is None:
            return 0.0
        x = max(-20.0, min(20.0, float(score)))
        return 1.0 / (1.0 + math.exp(-x))

    def _apply_reranker(self, query: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows or self.reranker is None:
            return rows

        candidate_n = max(1, min(len(rows), RERANK_CANDIDATES))
        head = rows[:candidate_n]
        tail = rows[candidate_n:]
        pairs = [[query, str(r.get("text", ""))] for r in head]

        try:
            scores = self.reranker.predict(
                pairs,
                batch_size=RERANK_BATCH_SIZE,
                show_progress_bar=False,
            )
        except Exception:
            return rows

        scored: list[dict[str, Any]] = []
        for row, score in zip(head, scores):
            item = dict(row)
            rerank_score = float(score)
            item["rerank_score"] = round(rerank_score, 4)
            item["rerank_score_norm"] = round(self._normalize_rerank_score(rerank_score), 4)
            scored.append(item)

        scored.sort(
            key=lambda r: (float(r.get("rerank_score_norm", 0.0)), float(r.get("similarity", 0.0))),
            reverse=True,
        )
        return scored + tail

    def _score_confidence(self, rows: list[dict[str, Any]]) -> float:
        if not rows:
            return 0.0
        sims = [float(r.get("similarity", 0.0)) for r in rows]
        sims.sort(reverse=True)
        top = sims[0]
        avg = sum(sims) / len(sims)
        spread = top - sims[-1] if len(sims) > 1 else top

        if any("rerank_score_norm" in r for r in rows):
            reranks = [float(r.get("rerank_score_norm", 0.0)) for r in rows]
            reranks.sort(reverse=True)
            rr_top = reranks[0]
            rr_avg = sum(reranks) / len(reranks)
            confidence = (0.40 * top) + (0.20 * avg) + (0.30 * rr_top) + (0.10 * rr_avg)
        else:
            confidence = (0.55 * top) + (0.35 * avg) + (0.10 * min(1.0, spread + 0.2))

        return round(max(0.0, min(1.0, confidence)), 4)

    def search_with_grounding(
        self,
        query: str,
        top_k: int = 5,
        namespaces: list[str] | None = None,
        exclude_namespaces: list[str] | None = None,
        tags: list[str] | None = None,
        path_prefix: str | None = None,
        mode: str = DEFAULT_SEARCH_MODE,
        trusted_only: bool = False,
        min_similarity: float | None = None,
        require_grounded: bool = False,
        enforce_contract: bool | None = None,
    ) -> dict[str, Any]:
        resolved_mode = self._resolve_mode(mode)
        sim_floor = self._resolve_min_similarity(resolved_mode, min_similarity)
        term_coverage_floor = self._resolve_min_query_term_coverage(resolved_mode)
        query_terms = self._tokenize_for_overlap(query)
        contract_enforced = ENFORCE_ANSWER_CONTRACT_DEFAULT if enforce_contract is None else bool(enforce_contract)

        ns_set = {slug(x) for x in namespaces} if namespaces else None
        ex_set = {slug(x) for x in exclude_namespaces} if exclude_namespaces else set()
        tag_set = {slug(x) for x in tags} if tags else None

        if trusted_only or (resolved_mode == "strict" and ns_set is None):
            ns_set = set(TRUSTED_NAMESPACES)

        # Balanced/strict defaults should avoid low-trust chat namespaces unless explicitly requested.
        if ns_set is None and resolved_mode in {"strict", "balanced"} and not trusted_only:
            ex_set |= set(LOW_TRUST_NAMESPACES)
        if trusted_only:
            ex_set |= set(LOW_TRUST_NAMESPACES)

        # Private namespaces (vault/Local/, user-defined via OMNI_PRIVATE_NAMESPACES)
        # are always excluded unless the query explicitly requests them.
        if PRIVATE_NAMESPACES and ns_set is None:
            ex_set |= set(PRIVATE_NAMESPACES)
        if ns_set:
            ex_set -= ns_set

        qkey = self._query_cache_key(
            query=query,
            top_k=top_k,
            namespaces=sorted(ns_set) if ns_set else None,
            exclude_namespaces=sorted(ex_set) if ex_set else None,
            tags=tags,
            path_prefix=path_prefix,
            mode=resolved_mode,
            trusted_only=trusted_only,
            min_similarity=sim_floor,
            require_grounded=require_grounded,
            enforce_contract=contract_enforced,
        )
        cached = self._query_cache_get(qkey)
        if cached is not None:
            return cached

        # ── Query expansion ─────────────────────────────────────────────────
        # Expand the query with semantically related terms from the vault's
        # own vocabulary. Broadens recall for both vector and BM25 paths.
        expanded_query = self._expand_query(query)

        vec = self.embed([expanded_query])[0]
        fetch_k = max(top_k * 8, 20)

        rows = (
            self.table.search(vec)
            .limit(fetch_k)
            .select(["id", "path", "chunk_index", "text", "tags", "namespace", "source", "indexed_at", "_distance"])
            .to_list()
        )
        for row in rows:
            row.setdefault("_retrieval_source", "vector")

        # ── BM25 augmentation ─────────────────────────────────────────────────
        # Fetch candidates the keyword path finds but vector may have missed.
        # These go through the same reranker — quality is sorted there, not here.
        if BM25_ENABLED and _BM25_AVAILABLE:
            self._ensure_bm25_fresh()
            bm25_ids = self._bm25_candidate_ids(expanded_query, BM25_CANDIDATES)
            if bm25_ids:
                vec_id_set = {r.get("id") for r in rows if r.get("id")}
                extra_ids = [i for i in bm25_ids if i not in vec_id_set]
                if extra_ids:
                    rows = rows + self._fetch_by_ids(extra_ids)

        filtered: list[dict[str, Any]] = []
        for row in rows:
            if not self._row_matches_filters(row, ns_set, ex_set, tag_set, path_prefix):
                continue
            similarity = self._distance_to_similarity(row.get("_distance"))
            # BM25-sourced rows carry no vector distance. Let them through the
            # similarity floor — the reranker decides their final rank.
            if similarity < sim_floor and row.get("_retrieval_source") != "bm25":
                continue

            row_terms = self._tokenize_for_overlap(str(row.get("text", "")))
            lexical_overlap = 1.0
            if query_terms:
                lexical_overlap = len(query_terms & row_terms) / len(query_terms)

            item = dict(row)
            item["similarity"] = round(similarity, 4)
            item["query_term_overlap"] = round(max(0.0, min(1.0, lexical_overlap)), 4)
            item["evidence_id"] = f"{item.get('path', '')}:{int(item.get('chunk_index', 0))}"
            filtered.append(item)

        ordered = self._apply_reranker(query, filtered)
        results = ordered[:top_k]

        matched_query_terms: set[str] = set()
        if query_terms and results:
            for row in results:
                matched_query_terms |= (query_terms & self._tokenize_for_overlap(str(row.get("text", ""))))
        term_coverage = 1.0 if not query_terms else (len(matched_query_terms) / len(query_terms))

        confidence = self._score_confidence(results)
        verdict = "grounded"
        reason = "sufficient evidence found"
        if not results:
            verdict = "insufficient_context"
            reason = "no evidence passed filters/thresholds"
        elif query_terms and term_coverage < term_coverage_floor:
            verdict = "insufficient_context" if term_coverage == 0 else "weak_grounding"
            reason = (
                "query-term coverage too low "
                f"({term_coverage:.2f} < {term_coverage_floor:.2f})"
            )
        elif confidence < max(0.35, sim_floor):
            verdict = "low_confidence"
            reason = "evidence relevance is weak"
        elif len(results) < min(2, top_k):
            verdict = "weak_grounding"
            reason = "only one supporting chunk found"

        allow_answer = verdict == "grounded"
        if (require_grounded or contract_enforced) and not allow_answer:
            results = []

        grounding = {
            "mode": resolved_mode,
            "trusted_only": bool(trusted_only),
            "min_similarity": round(sim_floor, 4),
            "min_query_term_coverage": round(term_coverage_floor, 4),
            "query_terms_count": len(query_terms),
            "query_term_coverage": round(max(0.0, min(1.0, term_coverage)), 4),
            "confidence": confidence,
            "verdict": verdict,
            "reason": reason,
            "allowed_namespaces": sorted(ns_set) if ns_set else None,
            "excluded_namespaces": sorted(ex_set) if ex_set else [],
            "require_grounded": bool(require_grounded),
            "answer_contract": {
                "enforced": bool(contract_enforced),
                "required_verdict": "grounded",
                "allow_answer": bool(allow_answer),
                "action": (
                    "answer_with_citations_only"
                    if allow_answer
                    else "reject_answer_and_request_more_context"
                ),
            },
            "reranker": {
                "enabled": bool(self.reranker is not None),
                "model": RERANK_MODEL_NAME if self.reranker is not None else None,
                "candidates": min(len(filtered), RERANK_CANDIDATES),
            },
            "policy": {
                "if_insufficient": "respond with 'insufficient evidence' and ask for narrower scope or more sources",
                "citation_required": True,
            },
        }

        payload = {"results": results, "grounding": grounding}
        self._query_cache_set(qkey, payload)
        self._cleanup_counter += 1
        if self._cleanup_counter >= 50:
            self._cleanup_counter = 0
            self._cleanup_runtime_files()
        return payload

    def search(
        self,
        query: str,
        top_k: int = 5,
        namespaces: list[str] | None = None,
        tags: list[str] | None = None,
        path_prefix: str | None = None,
    ) -> list[dict[str, Any]]:
        payload = self.search_with_grounding(
            query=query,
            top_k=top_k,
            namespaces=namespaces,
            tags=tags,
            path_prefix=path_prefix,
            mode="balanced",
            trusted_only=False,
            min_similarity=None,
            require_grounded=False,
            enforce_contract=None,
        )
        return payload["results"]

    def _check_store_rate(self, source: str) -> bool:
        """Return True if the source/agent is within the write rate limit."""
        if STORE_RATE_LIMIT <= 0:
            return True
        now = time.time()
        key = f"rate:{slug(source)}"
        window = self._store_rate_window.get(key, [])
        # Trim entries older than 60 seconds
        window = [t for t in window if (now - t) < 60.0]
        if len(window) >= STORE_RATE_LIMIT:
            return False
        window.append(now)
        self._store_rate_window[key] = window
        return True

    def _check_store_dedup(self, text: str) -> bool:
        """Return True if the content is sufficiently unique to store.

        Runs a quick vector similarity check against existing chunks.
        If anything scores above STORE_DEDUP_THRESHOLD, it's a duplicate.
        """
        if STORE_DEDUP_THRESHOLD <= 0.0 or STORE_DEDUP_THRESHOLD >= 1.0:
            return True  # dedup disabled
        try:
            vec = self.embed([text])[0]
            hits = (
                self.table.search(vec)
                .limit(3)
                .select(["text", "_distance"])
                .to_list()
            )
            for hit in hits:
                sim = self._distance_to_similarity(hit.get("_distance"))
                if sim >= STORE_DEDUP_THRESHOLD:
                    return False  # duplicate found
        except Exception:
            pass  # on error, allow the write
        return True

    def capture(self, req: CaptureRequest) -> dict[str, Any]:
        now_iso = datetime.utcnow().isoformat()

        # ── Store safety: rate limit ───────────────────────────────────────────
        if not self._check_store_rate(req.source):
            return {
                "status": "rate_limited",
                "message": f"Exceeded {STORE_RATE_LIMIT} writes/min for source '{req.source}'. Try again shortly.",
                "timestamp": now_iso,
            }

        # ── Store safety: dedup check ──────────────────────────────────────────
        if not self._check_store_dedup(req.text):
            return {
                "status": "duplicate_skipped",
                "message": "Content is near-identical to an existing memory. Skipped to keep vault clean.",
                "timestamp": now_iso,
            }

        # Smart tier routing: classifier decides cache / short_term / long_term
        if _CLASSIFIER_AVAILABLE and not req.file_name:
            result = classify(req.text)
            target = write_to_tier(
                content=req.text,
                tier=result.tier,
                vault=self.vault,
                category=result.category,
                source=slug(req.source),
            )
            tier = result.tier.value
            category = result.category
        else:
            # Fallback: original behaviour — write to Archive/
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
            entry = f"- [{now_iso}] #{tag} [namespace={namespace}] [source={source}] — {req.text}\n"
            with open(target, "a", encoding="utf-8") as f:
                f.write(entry)
            tier = "archive"
            category = tag

        self.index_file(target, quiet=True)
        self._invalidate_query_cache()

        return {
            "status": "captured",
            "file": str(target),
            "tier": tier,
            "category": category,
            "source": req.source,
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
            "query_cache_items": len(self._query_cache),
            "query_cache_ttl_sec": QUERY_CACHE_TTL_SEC,
            "query_cache_max_items": QUERY_CACHE_MAX_ITEMS,
            "tmp_ttl_sec": TMP_FILE_TTL_SEC,
            "tmp_max_files": TMP_MAX_FILES,
            "default_search_mode": DEFAULT_SEARCH_MODE,
            "enforce_answer_contract_default": ENFORCE_ANSWER_CONTRACT_DEFAULT,
            "reranker_enabled": bool(self.reranker is not None),
            "reranker_model": RERANK_MODEL_NAME if self.reranker is not None else None,
            "rerank_candidates": RERANK_CANDIDATES,
            "bm25_enabled": BM25_ENABLED and _BM25_AVAILABLE,
            "bm25_corpus_size": len(self._bm25_ids),
            "trusted_namespaces": sorted(TRUSTED_NAMESPACES),
            "low_trust_namespaces": sorted(LOW_TRUST_NAMESPACES),
            "private_namespaces": sorted(PRIVATE_NAMESPACES),
            "store_rate_limit": STORE_RATE_LIMIT,
            "store_dedup_threshold": STORE_DEDUP_THRESHOLD,
            "query_expansion_enabled": QUERY_EXPANSION_ENABLED,
            "query_expansion_terms": QUERY_EXPANSION_TERMS,
            "vocab_size": len(self._vocab_tokens),
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
        if p.name.lower() == "dashboard.md":
            return False
        return p.suffix == ".md" and not any(part in IGNORED_DIRS for part in p.parts)

    def on_modified(self, event):
        if not event.is_directory and self._relevant(event.src_path):
            self._pending.add(event.src_path)

    def on_created(self, event):
        if not event.is_directory and self._relevant(event.src_path):
            self._pending.add(event.src_path)

    def flush(self):
        if not self._pending:
            return
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
    app = FastAPI(title="Omniscience Engine", version="1.4.0")

    auth_cfg = load_auth_config()
    token_roles = build_token_roles(auth_cfg)

    # ── Activity tracking ──────────────────────────────────────────────────────
    activity_log: deque[dict] = deque(maxlen=200)
    activity_lock = threading.Lock()

    def _agent_name(authorization: str | None, x_agent_name: str | None) -> str:
        """Resolve a human-readable agent name from headers."""
        if x_agent_name:
            return x_agent_name[:64].strip()
        if authorization and authorization.startswith("Bearer ") and token_roles:
            token = authorization.split(" ", 1)[1].strip()
            role = token_roles.get(token)
            if role:
                return f"token:{role}"
        return "anonymous"

    def _log(agent: str, endpoint: str, detail: str = "") -> None:
        entry = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "agent": agent,
            "endpoint": endpoint,
            "detail": detail,
        }
        with activity_lock:
            activity_log.appendleft(entry)

    # ── Auth ───────────────────────────────────────────────────────────────────
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
    def health(
        authorization: str | None = Header(default=None, alias="Authorization"),
        x_agent_name: str | None = Header(default=None, alias="X-Agent-Name"),
    ):
        require_role("read", authorization)
        _log(_agent_name(authorization, x_agent_name), "/health")
        return JSONResponse(engine.stats())

    @app.get("/agents/activity")
    def agents_activity(
        authorization: str | None = Header(default=None, alias="Authorization"),
        x_agent_name: str | None = Header(default=None, alias="X-Agent-Name"),
    ):
        require_role("read", authorization)
        _log(_agent_name(authorization, x_agent_name), "/agents/activity")

        with activity_lock:
            snapshot = list(activity_log)

        # Build per-agent summary from log
        seen: dict[str, dict] = {}
        for entry in snapshot:
            a = entry["agent"]
            if a == "anonymous" and not seen.get(a):
                pass  # still track anonymous
            if a not in seen:
                seen[a] = {
                    "name": a,
                    "first_seen": entry["ts"],
                    "last_seen": entry["ts"],
                    "last_action": entry["endpoint"],
                    "calls": 0,
                }
            seen[a]["calls"] += 1
            # snapshot is newest-first; first entry per agent = most recent
            seen[a]["last_seen"] = entry["ts"]
            seen[a]["last_action"] = entry["endpoint"]

        # Flip: snapshot is newest-first, so iterate reversed for first_seen
        for entry in reversed(snapshot):
            a = entry["agent"]
            if a in seen:
                seen[a]["first_seen"] = entry["ts"]

        agents_list = sorted(seen.values(), key=lambda x: x["last_seen"], reverse=True)

        return JSONResponse({
            "agents": agents_list,
            "recent": snapshot[:50],
            "total_logged": len(snapshot),
        })

    @app.post("/search")
    def search(
        req: SearchRequest,
        authorization: str | None = Header(default=None, alias="Authorization"),
        x_agent_name: str | None = Header(default=None, alias="X-Agent-Name"),
    ):
        require_role("read", authorization)
        _log(_agent_name(authorization, x_agent_name), "/search", req.query)
        payload = engine.search_with_grounding(
            query=req.query,
            top_k=req.k,
            namespaces=req.namespaces,
            exclude_namespaces=req.exclude_namespaces,
            tags=req.tags,
            path_prefix=req.path_prefix,
            mode=req.mode,
            trusted_only=req.trusted_only,
            min_similarity=req.min_similarity,
            require_grounded=req.require_grounded,
            enforce_contract=req.enforce_contract,
        )
        return JSONResponse(
            {
                "query": req.query,
                "k": req.k,
                "filters": {
                    "namespaces": req.namespaces,
                    "exclude_namespaces": req.exclude_namespaces,
                    "tags": req.tags,
                    "path_prefix": req.path_prefix,
                    "mode": req.mode,
                    "trusted_only": req.trusted_only,
                    "min_similarity": req.min_similarity,
                    "require_grounded": req.require_grounded,
                    "enforce_contract": req.enforce_contract,
                },
                "grounding": payload["grounding"],
                "results": payload["results"],
            }
        )

    @app.post("/search/grounded")
    def search_grounded(
        req: SearchRequest,
        authorization: str | None = Header(default=None, alias="Authorization"),
        x_agent_name: str | None = Header(default=None, alias="X-Agent-Name"),
    ):
        require_role("read", authorization)
        _log(_agent_name(authorization, x_agent_name), "/search/grounded", req.query)
        payload = engine.search_with_grounding(
            query=req.query,
            top_k=req.k,
            namespaces=req.namespaces,
            exclude_namespaces=req.exclude_namespaces,
            tags=req.tags,
            path_prefix=req.path_prefix,
            mode=req.mode,
            trusted_only=req.trusted_only,
            min_similarity=req.min_similarity,
            require_grounded=req.require_grounded,
            enforce_contract=req.enforce_contract,
        )
        return JSONResponse(
            {
                "query": req.query,
                "k": req.k,
                "grounding": payload["grounding"],
                "results": payload["results"],
            }
        )

    @app.get("/policy/grounding")
    def policy_grounding(
        authorization: str | None = Header(default=None, alias="Authorization"),
        x_agent_name: str | None = Header(default=None, alias="X-Agent-Name"),
    ):
        require_role("read", authorization)
        _log(_agent_name(authorization, x_agent_name), "/policy/grounding")
        return JSONResponse(
            {
                "version": "1.4.0",
                "rules": [
                    "Use only returned evidence chunks as factual basis.",
                    "If verdict is not grounded, explicitly say evidence is insufficient.",
                    "Do not infer facts that are absent from evidence.",
                    "Require non-trivial query-term coverage in strict/balanced modes.",
                    "Reject final answers when answer_contract.allow_answer is false.",
                    "Use reranker priority when reranker is enabled.",
                    "Cite evidence_id/path for each critical claim.",
                    "Prefer trusted namespaces for operational decisions.",
                ],
                "recommended_system_prompt": (
                    "Answer only using supplied evidence. "
                    "If grounding verdict is insufficient_context, low_confidence, or weak_grounding, "
                    "or answer_contract.allow_answer is false, state that evidence is insufficient and ask for narrower query or more sources. "
                    "Never invent missing facts."
                ),
            }
        )

    @app.post("/capture")
    def capture(
        req: CaptureRequest,
        authorization: str | None = Header(default=None, alias="Authorization"),
        x_agent_name: str | None = Header(default=None, alias="X-Agent-Name"),
    ):
        require_role("write", authorization)
        _log(_agent_name(authorization, x_agent_name), "/capture", req.text[:80] if req.text else "")
        return JSONResponse(engine.capture(req))

    @app.post("/admin/reindex")
    def admin_reindex(
        authorization: str | None = Header(default=None, alias="Authorization"),
        x_agent_name: str | None = Header(default=None, alias="X-Agent-Name"),
    ):
        require_role("admin", authorization)
        _log(_agent_name(authorization, x_agent_name), "/admin/reindex")

        def _run():
            engine.index_all(force=True)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return JSONResponse({"status": "started", "action": "reindex"})

    @app.post("/admin/cleanup")
    def admin_cleanup(
        authorization: str | None = Header(default=None, alias="Authorization"),
        x_agent_name: str | None = Header(default=None, alias="X-Agent-Name"),
    ):
        require_role("admin", authorization)
        _log(_agent_name(authorization, x_agent_name), "/admin/cleanup")
        engine._cleanup_runtime_files()
        return JSONResponse({"status": "ok", "action": "cleanup"})

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

    if args.reindex:
        engine.index_all(force=True)
    elif engine.table.count_rows() == 0:
        engine.index_all(force=True)

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
