"""Tests for the memory tier classifier.

Verifies that memory_classifier.py routes content to the correct tier:
- Force keywords always win (remember, never forget, permanent)
- Long-term signals: decisions, preferences, directives
- Short-term signals: tasks, sprint, working on
- Cache signals: greetings, one-off questions
- Edge cases: very short, very long, mixed signals
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine"))

try:
    from memory_classifier import classify, MemoryTier
    _CLASSIFIER_AVAILABLE = True
except ImportError:
    _CLASSIFIER_AVAILABLE = False


@pytest.mark.skipif(not _CLASSIFIER_AVAILABLE, reason="memory_classifier not available")
class TestForceKeywords:
    def test_remember_this(self):
        result = classify("Remember this: always use Python for data pipelines")
        assert result.tier == MemoryTier.LONG_TERM

    def test_never_forget(self):
        result = classify("Never forget: the API key rotates every 30 days")
        assert result.tier == MemoryTier.LONG_TERM

    def test_permanent(self):
        result = classify("Permanent rule: no cloud databases for core systems")
        assert result.tier == MemoryTier.LONG_TERM

    def test_from_now_on(self):
        result = classify("From now on, always run tests before committing")
        assert result.tier == MemoryTier.LONG_TERM


@pytest.mark.skipif(not _CLASSIFIER_AVAILABLE, reason="memory_classifier not available")
class TestLongTermSignals:
    def test_decision(self):
        result = classify("Decided to use FastAPI instead of Flask for the engine")
        assert result.tier == MemoryTier.LONG_TERM

    def test_preference(self):
        result = classify("I always prefer local-first architecture over cloud solutions")
        assert result.tier == MemoryTier.LONG_TERM

    def test_tech_stack(self):
        result = classify("My tech stack is Python, FastAPI, LanceDB, and Obsidian")
        assert result.tier == MemoryTier.LONG_TERM


@pytest.mark.skipif(not _CLASSIFIER_AVAILABLE, reason="memory_classifier not available")
class TestShortTermSignals:
    def test_working_on(self):
        result = classify("Currently working on the BM25 hybrid search implementation")
        assert result.tier == MemoryTier.SHORT_TERM

    def test_current_task(self):
        result = classify("Current task: fix the chunker to respect code fences")
        assert result.tier == MemoryTier.SHORT_TERM

    def test_blocked(self):
        result = classify("Blocked on the Docker setup, need to configure volumes")
        assert result.tier == MemoryTier.SHORT_TERM


@pytest.mark.skipif(not _CLASSIFIER_AVAILABLE, reason="memory_classifier not available")
class TestCacheSignals:
    def test_greeting(self):
        result = classify("Hello!")
        assert result.tier == MemoryTier.CACHE

    def test_short_question(self):
        result = classify("What time is it?")
        assert result.tier == MemoryTier.CACHE

    def test_just_checking(self):
        result = classify("Just checking if the engine is running")
        assert result.tier == MemoryTier.CACHE


@pytest.mark.skipif(not _CLASSIFIER_AVAILABLE, reason="memory_classifier not available")
class TestEdgeCases:
    def test_very_short_content(self):
        result = classify("Hi")
        assert result.tier == MemoryTier.CACHE, "Very short content should be cache"

    def test_mixed_signals_long_wins(self):
        # Contains both short-term and long-term signals — long should win
        result = classify(
            "Decided from now on to always run the current task through "
            "the test suite before marking it done"
        )
        assert result.tier == MemoryTier.LONG_TERM, "Force keyword should override short-term signal"

    def test_empty_string(self):
        result = classify("")
        # Should not crash, tier doesn't matter as long as it returns
        assert result.tier in (MemoryTier.CACHE, MemoryTier.SHORT_TERM, MemoryTier.LONG_TERM)
