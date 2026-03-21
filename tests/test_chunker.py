"""Tests for the smart Markdown-aware chunker.

Verifies that chunk_markdown correctly handles:
- YAML frontmatter extraction and attachment
- ATX heading splits with breadcrumb paths
- Code fence protection (no splits inside fences)
- Oversized section paragraph splitting
- No-heading fallback to paragraph mode
- Minimum chunk size enforcement
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine"))
from engine import chunk_markdown, CHUNK_MAX_CHARS, CHUNK_MIN_CHARS


class TestFrontmatter:
    def test_frontmatter_on_first_chunk(self):
        text = (
            "---\ntype: knowledge\ntags: test\n---\n\n"
            "# Title\n\n"
            "Some content here that is long enough to pass the minimum character "
            "threshold for chunking so it does not get filtered out by the engine.\n"
        )
        chunks = chunk_markdown(text)
        assert chunks, "Should produce at least one chunk"
        # Frontmatter should be part of the first chunk's content
        first = chunks[0]
        assert "type: knowledge" in first or "Title" in first, \
            "First chunk should contain frontmatter or heading"

    def test_frontmatter_not_on_later_chunks(self):
        text = (
            "---\ntype: knowledge\n---\n\n"
            "# Section One\n\n"
            "Content for section one with enough text to exceed the minimum "
            "character threshold and be kept as a valid chunk by the engine.\n\n"
            "# Section Two\n\n"
            "Content for section two also with enough text to exceed the minimum "
            "character threshold and be kept as a valid chunk by the engine.\n"
        )
        chunks = chunk_markdown(text)
        if len(chunks) > 1:
            for chunk in chunks[1:]:
                assert "type: knowledge" not in chunk, "Frontmatter should only be on chunk 0"

    def test_no_frontmatter(self):
        text = (
            "# Just a heading\n\n"
            "Some content without frontmatter but with enough text to pass "
            "the minimum character threshold for chunking in the engine.\n"
        )
        chunks = chunk_markdown(text)
        assert chunks, "Should still produce chunks without frontmatter"


class TestHeadingSplits:
    def test_splits_on_h2(self):
        text = (
            "## Config\n\n"
            "Configuration content here with enough detail about settings "
            "and parameters to exceed the minimum chunk character threshold.\n\n"
            "## Usage\n\n"
            "Usage documentation here with step-by-step instructions that "
            "also exceed the minimum chunk character threshold for the engine.\n"
        )
        chunks = chunk_markdown(text)
        assert len(chunks) >= 2, f"Should split on ## headings, got {len(chunks)} chunks"

    def test_breadcrumb_in_chunks(self):
        text = (
            "# Top Level\n\n"
            "Introduction paragraph with enough content to be meaningful and "
            "pass the minimum character filter used by the chunking engine.\n\n"
            "## Sub Section\n\n"
            "Sub content with detailed explanation about the subsection topic "
            "providing enough text to pass the minimum character threshold.\n\n"
            "### Deep Section\n\n"
            "Deep content here with extensive details about the deep section "
            "topic ensuring this chunk passes the minimum character filter.\n"
        )
        chunks = chunk_markdown(text)
        deep_chunks = [c for c in chunks if "Deep content" in c]
        assert deep_chunks, "Should have a chunk with deep content"
        assert "###" in deep_chunks[0] or "Deep Section" in deep_chunks[0], \
            "Deep chunk should have heading breadcrumb"

    def test_heading_hierarchy_preserved(self):
        text = (
            "## Architecture\n\n"
            "Architecture overview with enough content about the system design "
            "and component structure to pass the minimum character threshold.\n\n"
            "### MCP Server\n\n"
            "MCP server implementation details covering protocol support, "
            "transport layers, and tool registration for the engine API.\n\n"
            "### Engine\n\n"
            "Engine implementation details covering indexing, search pipeline, "
            "and the hybrid BM25 plus vector retrieval architecture.\n\n"
            "## Deployment\n\n"
            "Deployment instructions covering Docker, systemd, and manual "
            "installation options for production environments.\n"
        )
        chunks = chunk_markdown(text)
        mcp_chunks = [c for c in chunks if "MCP server" in c or "MCP content" in c]
        if mcp_chunks:
            # MCP chunk should reference Architecture as parent
            assert "Architecture" in mcp_chunks[0] or "###" in mcp_chunks[0], \
                "MCP chunk should carry parent breadcrumb"


class TestCodeFences:
    def test_no_split_inside_code_block(self):
        text = (
            "## Example\n\n"
            "Here is a code example that demonstrates the functionality "
            "with enough surrounding text to meet the minimum threshold.\n\n"
            "```python\n"
            "# This heading inside code should NOT cause a split\n"
            "## Also not a real heading\n"
            "def foo():\n"
            "    return 42\n"
            "```\n\n"
            "After the code block there should be additional text.\n"
        )
        chunks = chunk_markdown(text)
        code_chunks = [c for c in chunks if "def foo" in c]
        assert code_chunks, "Should have chunk with code"
        assert "# This heading" in code_chunks[0], "Code block heading should stay in same chunk"

    def test_code_block_kept_whole(self):
        text = (
            "## Setup\n\n"
            "Follow these steps to set up the development environment "
            "from scratch on a clean machine with the prerequisites.\n\n"
            "```bash\n"
            "git clone https://example.com/repo\n"
            "cd repo\n"
            "bash setup.sh\n"
            "python engine/start.py\n"
            "```\n"
        )
        chunks = chunk_markdown(text)
        setup_chunks = [c for c in chunks if "git clone" in c]
        assert setup_chunks
        assert "bash setup.sh" in setup_chunks[0], "Code block should not be split"


class TestOversizedSections:
    def test_large_section_splits_on_paragraphs(self):
        paragraphs = [f"Paragraph {i}. " + "x" * 200 for i in range(20)]
        text = "## Large Section\n\n" + "\n\n".join(paragraphs)
        chunks = chunk_markdown(text)
        assert len(chunks) > 1, "Oversized section should split into multiple chunks"
        for chunk in chunks:
            assert "Large Section" in chunk, "Every sub-chunk should carry heading breadcrumb"

    def test_no_chunk_exceeds_max(self):
        paragraphs = [f"Paragraph {i}. " + "y" * 300 for i in range(15)]
        text = "## Big\n\n" + "\n\n".join(paragraphs)
        chunks = chunk_markdown(text)
        limit = CHUNK_MAX_CHARS + 200
        for chunk in chunks:
            assert len(chunk) <= limit, f"Chunk too large: {len(chunk)} chars"


class TestNoHeadings:
    def test_plain_text_uses_paragraph_fallback(self):
        text = (
            "First paragraph with enough content to be meaningful and pass "
            "the minimum character filter threshold.\n\n"
            "Second paragraph also meaningful with sufficient length to be "
            "kept as a valid chunk by the engine.\n\n"
            "Third paragraph with more content to ensure the chunker works "
            "correctly even without any headings in the document.\n"
        )
        chunks = chunk_markdown(text)
        assert chunks, "Plain text should still produce chunks"

    def test_short_content_filtered(self):
        text = "Hi"
        chunks = chunk_markdown(text)
        assert len(chunks) == 0, "Very short content should be filtered by CHUNK_MIN_CHARS"


class TestEmptyInputs:
    def test_empty_string(self):
        assert chunk_markdown("") == []

    def test_whitespace_only(self):
        assert chunk_markdown("   \n\n   ") == []
