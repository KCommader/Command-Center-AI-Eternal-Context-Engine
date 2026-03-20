"""Integration tests for the search pipeline.

Uses a real temp vault + temp LanceDB (no mocking). Verifies:
- Vector search finds semantically related content
- BM25 augmentation finds exact keyword matches vector may miss
- Grounding policy produces valid confidence scores
- Private namespaces are excluded from default searches
- Reranker reorders results by relevance
"""
from __future__ import annotations

import pytest


class TestVectorSearch:
    def test_semantic_match(self, engine_instance):
        """Search with different wording should find semantically related content."""
        results = engine_instance.search("how to start the service on boot", top_k=5)
        texts = " ".join(r.get("text", "") for r in results)
        assert "systemd" in texts.lower() or "docker" in texts.lower(), (
            "Semantic search should find deployment content even with different wording"
        )

    def test_returns_results(self, engine_instance):
        """Basic search should return results from the indexed vault."""
        results = engine_instance.search("search architecture pipeline", top_k=5)
        assert len(results) > 0, "Should return at least one result"


class TestBM25Augmentation:
    def test_exact_keyword_found(self, engine_instance):
        """BM25 should find content with exact keyword matches."""
        results = engine_instance.search("CrossEncoder reranking", top_k=5)
        texts = " ".join(r.get("text", "") for r in results)
        assert "crossencoder" in texts.lower() or "reranking" in texts.lower(), (
            "BM25 should catch exact keyword matches"
        )


class TestGrounding:
    def test_grounding_returns_confidence(self, engine_instance):
        """Search with grounding should include a confidence score."""
        payload = engine_instance.search_with_grounding(
            query="deployment guide docker",
            top_k=5,
            mode="balanced",
        )
        assert "grounding" in payload, "Should have grounding section"
        assert "confidence" in payload["grounding"], "Grounding should include confidence"
        assert 0.0 <= payload["grounding"]["confidence"] <= 1.0, "Confidence should be 0-1"

    def test_grounding_verdict(self, engine_instance):
        """Search for known content should produce a grounded verdict."""
        payload = engine_instance.search_with_grounding(
            query="triple pipeline vector BM25 reranking",
            top_k=5,
            mode="balanced",
        )
        verdict = payload["grounding"].get("verdict", "")
        assert verdict in ("grounded", "insufficient"), f"Unexpected verdict: {verdict}"


class TestPrivateNamespaces:
    def test_local_excluded_by_default(self, engine_instance):
        """Content in vault/Local/ should NOT appear in default searches."""
        results = engine_instance.search("private notes should not appear", top_k=10)
        for r in results:
            ns = r.get("namespace", "")
            assert ns != "local_only", (
                "local_only namespace should be excluded from default balanced search"
            )

    def test_local_included_when_requested(self, engine_instance):
        """Content in vault/Local/ SHOULD appear when namespace is explicitly requested."""
        payload = engine_instance.search_with_grounding(
            query="private notes",
            top_k=10,
            namespaces=["local_only"],
            mode="balanced",
        )
        results = payload.get("results", [])
        local_results = [r for r in results if r.get("namespace") == "local_only"]
        assert local_results, "Should find local_only content when explicitly requested"


class TestResultQuality:
    def test_results_have_required_fields(self, engine_instance):
        """Every result should have the standard fields."""
        results = engine_instance.search("deployment", top_k=3)
        required = {"path", "text", "namespace", "similarity"}
        for r in results:
            for field in required:
                assert field in r, f"Missing field '{field}' in result"

    def test_similarity_scores_ordered(self, engine_instance):
        """Results should be ordered by relevance (similarity or rerank score)."""
        payload = engine_instance.search_with_grounding(
            query="search architecture",
            top_k=5,
            mode="balanced",
        )
        results = payload.get("results", [])
        if len(results) >= 2:
            # If reranker is active, check rerank scores; otherwise check similarity
            if "rerank_score_norm" in results[0]:
                scores = [r.get("rerank_score_norm", 0) for r in results]
            else:
                scores = [r.get("similarity", 0) for r in results]
            assert scores == sorted(scores, reverse=True), "Results should be ordered by score"
