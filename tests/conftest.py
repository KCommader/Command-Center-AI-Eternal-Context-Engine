"""Shared fixtures for the ECE test suite.

All tests use a temp vault and temp LanceDB directory so nothing touches
the real vault. Fixtures are session-scoped where safe (engine startup
is expensive) and function-scoped where isolation is needed.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

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
    )
    (core / "SOUL.md").write_text(
        "---\ntype: identity\n---\n\n# Soul\n\nBe helpful. Be direct. No filler.\n"
    )

    # Knowledge files with distinct, searchable content
    knowledge = vault / "Knowledge"
    knowledge.mkdir()
    (knowledge / "deployment-guide.md").write_text(
        "---\ntype: knowledge\n---\n\n# Deployment Guide\n\n"
        "## Docker Setup\n\n"
        "Run `docker compose up -d` to start the engine.\n"
        "Volume mount the vault so data stays on the host.\n\n"
        "## systemd Installation\n\n"
        "Copy the unit file to /etc/systemd/system/ and enable it.\n"
        "The engine starts on boot and restarts on crash.\n"
    )
    (knowledge / "search-architecture.md").write_text(
        "---\ntype: knowledge\n---\n\n# Search Architecture\n\n"
        "## Triple Pipeline\n\n"
        "The search engine uses three stages:\n"
        "1. Vector retrieval via LanceDB (semantic similarity)\n"
        "2. BM25 keyword matching (exact token hits)\n"
        "3. CrossEncoder reranking (final relevance scoring)\n\n"
        "## Query Expansion\n\n"
        "Before searching, the engine expands queries with related terms\n"
        "from the vault vocabulary. This catches vocabulary mismatches.\n"
    )
    (knowledge / "privacy-model.md").write_text(
        "---\ntype: knowledge\n---\n\n# Privacy Model\n\n"
        "## Private Namespaces\n\n"
        "Files in vault/Local/ are namespaced as local_only and excluded\n"
        "from default searches. Cloud AIs never see them.\n\n"
        "## Rate Limiting\n\n"
        "Store operations are rate-limited to 30 writes per minute per agent.\n"
        "Duplicate content is detected and skipped automatically.\n"
    )

    # Archive
    archive = vault / "Archive"
    archive.mkdir()
    (archive / "MEMORY.md").write_text(
        "# Long-Term Memory\n\n"
        "- Prefer Python over Node for data pipelines\n"
        "- Local-first architecture\n"
    )

    # Local (private namespace)
    local = vault / "Local"
    local.mkdir()
    (local / "private-notes.md").write_text(
        "# Private Notes\n\nThis should not appear in default searches.\n"
    )

    return vault


@pytest.fixture(scope="session")
def engine_instance(temp_vault: Path, tmp_path_factory: pytest.TempPathFactory):
    """Create and index an OmniscienceEngine against the temp vault."""
    import os

    db_dir = tmp_path_factory.mktemp("lancedb")
    os.environ["OMNI_DB_DIR"] = str(db_dir)

    from engine import OmniscienceEngine

    eng = OmniscienceEngine(vault=temp_vault)
    eng.index_all(force=True)
    return eng
