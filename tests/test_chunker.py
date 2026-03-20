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
        text = "---\ntype: knowledge\ntags: test\n---\n\n# Title\n\nSome content here."
        chunks = chunk_markdown(text)
        assert chunks, "Should produce at least one chunk"
        assert "---" in chunks[0], "First chunk should contain frontmatter"
        assert "type: knowledge" in chunks[0]

    def test_frontmatter_not_on_later_chunks(self):
        text = (
            "---\ntype: knowledge\n---\n\n"
            "# Section One\n\nContent for section one.\n\n"
            "# Section Two\n\nContent for section two.\n"
        )
        chunks = chunk_markdown(text)
        if len(chunks) > 1:
            for chunk in chunks[1:]:
                assert "type: knowledge" not in chunk, "Frontmatter should only be on chunk 0"

    def test_no_frontmatter(self):
        text = "# Just a heading\n\nSome content without frontmatter."
        chunks = chunk_markdown(text)
        assert chunks, "Should still produce chunks without frontmatter"


class TestHeadingSplits:
    def test_splits_on_h2(self):
        text = "## Config\n\nConfig content here.\n\n## Usage\n\nUsage content here."
        chunks = chunk_markdown(text)
        assert len(chunks) >= 2, "Should split on ## headings"

    def test_breadcrumb_in_chunks(self):
        text = (
            "# Top Level\n\nIntro.\n\n"
            "## Sub Section\n\nSub content.\n\n"
            "### Deep Section\n\nDeep content.\n"
        )
        chunks = chunk_markdown(text)
        # Find the chunk with "Deep content"
        deep_chunks = [c for c in chunks if "Deep content" in c]
        assert deep_chunks, "Should have a chunk with deep content"
        assert "###" in deep_chunks[0], "Deep chunk should have heading breadcrumb"

    def test_heading_hierarchy_preserved(self):
        text = (
            "## Architecture\n\nArch content.\n\n"
            "### MCP Server\n\nMCP content.\n\n"
            "### Engine\n\nEngine content.\n\n"
            "## Deployment\n\nDeploy content.\n"
        )
        chunks = chunk_markdown(text)
        mcp_chunks = [c for c in chunks if "MCP content" in c]
        assert mcp_chunks, "Should find MCP chunk"
        # MCP chunk should reference Architecture as parent
        assert "Architecture" in mcp_chunks[0], "MCP chunk should carry parent breadcrumb"


class TestCodeFences:
    def test_no_split_inside_code_block(self):
        text = (
            "## Example\n\n"
            "```python\n"
            "# This heading inside code should NOT cause a split\n"
            "## Also not a real heading\n"
            "def foo():\n"
            "    return 42\n"
            "```\n\n"
            "After code block.\n"
        )
        chunks = chunk_markdown(text)
        # All code should be in one chunk
        code_chunks = [c for c in chunks if "def foo" in c]
        assert code_chunks, "Should have chunk with code"
        assert "# This heading" in code_chunks[0], "Code block heading should stay in same chunk"

    def test_code_block_kept_whole(self):
        text = (
            "## Setup\n\n"
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
        # Create a section larger than CHUNK_MAX_CHARS
        paragraphs = [f"Paragraph {i}. " + "x" * 200 for i in range(20)]
        text = "## Large Section\n\n" + "\n\n".join(paragraphs)
        chunks = chunk_markdown(text)
        assert len(chunks) > 1, "Oversized section should split into multiple chunks"
        # Each chunk should carry the heading breadcrumb
        for chunk in chunks:
            assert "Large Section" in chunk, "Every sub-chunk should carry heading breadcrumb"

    def test_no_chunk_exceeds_max(self):
        paragraphs = [f"Paragraph {i}. " + "y" * 300 for i in range(15)]
        text = "## Big\n\n" + "\n\n".join(paragraphs)
        chunks = chunk_markdown(text)
        # Allow some tolerance for heading breadcrumb + frontmatter
        limit = CHUNK_MAX_CHARS + 200
        for chunk in chunks:
            assert len(chunk) <= limit, f"Chunk too large: {len(chunk)} chars"


class TestNoHeadings:
    def test_plain_text_uses_paragraph_fallback(self):
        text = "First paragraph with enough content to be meaningful.\n\nSecond paragraph also meaningful.\n\nThird one too."
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
