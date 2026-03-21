"""Shared fixtures for the ECE test suite.

All tests use a temp vault and temp LanceDB directory so nothing touches
the real vault. Fixtures are session-scoped where safe (engine startup
is expensive) and function-scoped where isolation is needed.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

# ── Test-friendly similarity floors ──────────────────────────────────────────
# Must be set BEFORE any engine import because engine.py reads these at
# module level.  The multilingual model produces larger L2 distances than
# the English-only model, so the default floors would filter out
# every result in a small test vault.
os.environ.setdefault("OMNI_MIN_SIMILARITY_BALANCED", "0.01")
os.environ.setdefault("OMNI_MIN_SIMILARITY_EXPLORATORY", "0.005")
os.environ.setdefault("OMNI_MIN_SIMILARITY_STRICT", "0.02")
# Dedup threshold for multilingual model — L2 distances are larger,
# so the similarity score for identical text may be slightly below 0.92.
os.environ.setdefault("OMNI_STORE_DEDUP_THRESHOLD", "0.80")

# Ensure engine/ is importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))


@pytest.fixture(scope="session")
def temp_vault(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a minimal vault with known content for testing."""
    vault = tmp_path_factory.mktemp("vault")

    # Core files
    core = vault / "Core"
    core.mkdir()
    (core / "USER.md").write_text(
        "---\ntype: identity\n---\n\n# User\n\nTest user for ECE test suite.\n"
        "- Timezone: UTC\n- Stack: Python, FastAPI\n"
        "- Preference: local-first architecture, no cloud databases\n"
        "- Operating system: Linux, with occasional macOS usage\n"
    )
    (core / "SOUL.md").write_text(
        "---\ntype: identity\n---\n\n# Soul\n\nBe helpful. Be direct. No filler.\n"
        "Always prioritize accuracy over speed. When uncertain, say so.\n"
        "Never make up information that isn't grounded in vault evidence.\n"
    )

    # Knowledge files with distinct, searchable content
    knowledge = vault / "Knowledge"
    knowledge.mkdir()
    (knowledge / "deployment-guide.md").write_text(
        "---\ntype: knowledge\n---\n\n# Deployment Guide\n\n"
        "## Docker Setup\n\n"
        "Run `docker compose up -d` to start the engine.\n"
        "Volume mount the vault so data stays on the host.\n"
        "The container uses restart: unless-stopped for crash recovery.\n"
        "Health checks run every 30 seconds on the /health endpoint.\n\n"
        "## systemd Installation\n\n"
        "Copy the unit file to /etc/systemd/system/ and enable it.\n"
        "The engine starts on boot and restarts on crash.\n"
        "Logs go to journald — view with journalctl -u command-center.\n"
    )
    (knowledge / "search-architecture.md").write_text(
        "---\ntype: knowledge\n---\n\n# Search Architecture\n\n"
        "## Triple Pipeline\n\n"
        "The search engine uses three stages:\n"
        "1. Vector retrieval via LanceDB (semantic similarity)\n"
        "2. BM25 keyword matching (exact token hits)\n"
        "3. CrossEncoder reranking (final relevance scoring)\n\n"
        "The reranker uses cross-encoder/ms-marco-MiniLM-L-12-v2 by default.\n"
        "It scores each candidate against the query for precise relevance.\n\n"
        "## Query Expansion\n\n"
        "Before searching, the engine expands queries with related terms\n"
        "from the vault vocabulary. This catches vocabulary mismatches\n"
        "where the user's wording differs from the stored text.\n"
    )
    (knowledge / "privacy-model.md").write_text(
        "---\ntype: knowledge\n---\n\n# Privacy Model\n\n"
        "## Private Namespaces\n\n"
        "Files in vault/Local/ are namespaced as local_only and excluded\n"
        "from default searches. Cloud AIs never see them.\n"
        "Users can add custom private namespaces via config.yaml.\n\n"
        "## Rate Limiting\n\n"
        "Store operations are rate-limited to 30 writes per minute per agent.\n"
        "Duplicate content is detected and skipped automatically.\n"
        "This prevents vault flooding from misbehaving AI agents.\n"
    )

    # Archive
    archive = vault / "Archive"
    archive.mkdir()
    (archive / "MEMORY.md").write_text(
        "# Long-Term Memory\n\n"
        "- Prefer Python over Node for data pipelines\n"
        "- Local-first architecture is a core design principle\n"
        "- Always use semantic versioning for releases\n"
    )

    # Local (private namespace)
    local = vault / "Local"
    local.mkdir()
    (local / "private-notes.md").write_text(
        "# Private Notes\n\nThis should not appear in default searches.\n"
        "Contains personal information that must stay local.\n"
        "Only visible when the local_only namespace is explicitly requested.\n"
    )

    return vault


@pytest.fixture(scope="session")
def engine_instance(temp_vault: Path, tmp_path_factory: pytest.TempPathFactory):
    """Create and index an OmniscienceEngine against the temp vault."""
    db_dir = tmp_path_factory.mktemp("lancedb")
    os.environ["OMNI_DB_DIR"] = str(db_dir)

    from engine import OmniscienceEngine

    eng = OmniscienceEngine(str(temp_vault))
    eng.index_all(force=True)
    return eng
