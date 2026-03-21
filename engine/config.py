"""ECE YAML configuration loader.

Reads an optional ``config.yaml`` from the vault root and maps its keys to
the ``OMNI_*`` environment variables that the engine reads at startup.

Environment variables always win — the YAML file only provides defaults for
settings that are not already set. This means:

    1. No YAML file → everything works exactly as before (env vars / built-ins).
    2. YAML file present → provides human-readable defaults for any key not
       overridden by the environment.
    3. Env var set → overrides the YAML value for that key.

Call ``apply_yaml_config(vault_path)`` before any engine module is imported.
The function is idempotent — safe to call more than once.

YAML format (vault/config.yaml):

    search:
      mode: balanced
      bm25_enabled: true
      bm25_candidates: 40
      rerank_enabled: true
      rerank_model: cross-encoder/ms-marco-MiniLM-L-12-v2
      rerank_candidates: 36
      query_expansion_enabled: true
      query_expansion_terms: 5

    chunking:
      max_chars: 1500
      min_chars: 80

    memory:
      classifier_mode: regex   # regex | llm | hybrid (v1.9.0+)
      store_rate_limit: 30
      store_dedup_threshold: 0.92

    privacy:
      private_namespaces:
        - local_only
        - diary

    advanced:
      api_port: 8765
      api_host: 127.0.0.1
      query_cache_ttl_sec: 3600
      query_cache_max_items: 256
      rerank_batch_size: 16
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any


# Maps YAML path (dot-notation) → OMNI_* env var name.
# Only listed here if there is a direct OMNI_* counterpart in engine.py.
_YAML_TO_ENV: dict[str, str] = {
    "embedding.model":                   "OMNI_EMBEDDING_MODEL",
    "search.mode":                       "OMNI_DEFAULT_SEARCH_MODE",
    "search.bm25_enabled":               "OMNI_BM25_ENABLED",
    "search.bm25_candidates":            "OMNI_BM25_CANDIDATES",
    "search.rerank_enabled":             "OMNI_RERANK_ENABLED",
    "search.rerank_model":               "OMNI_RERANK_MODEL_NAME",
    "search.rerank_candidates":          "OMNI_RERANK_CANDIDATES",
    "search.rerank_batch_size":          "OMNI_RERANK_BATCH_SIZE",
    "search.query_expansion_enabled":    "OMNI_QUERY_EXPANSION_ENABLED",
    "search.query_expansion_terms":      "OMNI_QUERY_EXPANSION_TERMS",
    "chunking.max_chars":                "OMNI_CHUNK_MAX_CHARS",
    "chunking.min_chars":                "OMNI_CHUNK_MIN_CHARS",
    "memory.classifier_mode":            "OMNI_CLASSIFIER_MODE",
    "memory.store_rate_limit":           "OMNI_STORE_RATE_LIMIT",
    "memory.store_dedup_threshold":      "OMNI_STORE_DEDUP_THRESHOLD",
    "advanced.api_port":                 "OMNI_API_PORT",
    "advanced.api_host":                 "OMNI_API_HOST",
    "advanced.query_cache_ttl_sec":      "OMNI_QUERY_CACHE_TTL_SEC",
    "advanced.query_cache_max_items":    "OMNI_QUERY_CACHE_MAX_ITEMS",
}

# Keys whose YAML values are lists — joined to comma-separated strings.
_LIST_KEYS: set[str] = {
    "privacy.private_namespaces",
}


def _get_nested(data: dict[str, Any], dotpath: str) -> Any:
    keys = dotpath.split(".")
    node: Any = data
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
        if node is None:
            return None
    return node


def _scalar(value: Any) -> str:
    """Convert a YAML scalar to the string form the engine expects."""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def apply_yaml_config(vault_path: str | Path) -> None:
    """Read ``{vault}/config.yaml`` and inject missing OMNI_* env vars.

    Silently no-ops if the file is missing, unreadable, or malformed.
    Existing env vars are never overwritten.
    """
    config_path = Path(vault_path) / "config.yaml"
    if not config_path.exists():
        return

    try:
        import yaml  # PyYAML — optional dependency
        with config_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except ImportError:
        # PyYAML not installed — skip silently, env vars still work
        return
    except Exception:
        return

    if not isinstance(data, dict):
        return

    for dotpath, env_key in _YAML_TO_ENV.items():
        if env_key in os.environ:
            continue  # env var wins
        value = _get_nested(data, dotpath)
        if value is None:
            continue
        os.environ[env_key] = _scalar(value)

    # Handle list keys (e.g. private_namespaces → comma-separated)
    for dotpath in _LIST_KEYS:
        env_key = "OMNI_PRIVATE_NAMESPACES"
        if env_key in os.environ:
            continue
        value = _get_nested(data, dotpath)
        if isinstance(value, list):
            os.environ[env_key] = ",".join(str(v) for v in value)
        elif isinstance(value, str):
            os.environ[env_key] = value
