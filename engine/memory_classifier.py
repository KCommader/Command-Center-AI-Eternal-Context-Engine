"""
Memory Classifier
=================
Decides where a piece of content belongs in the memory tier hierarchy.

Tiers:
  - cache      → Temporary session context. Cleared nightly. (vault/Cache/)
  - short_term → Project/task state. Auto-expires after 30 days. (vault/Archive/short/)
  - long_term  → Permanent preferences, decisions, identity. Never expires. (vault/Archive/MEMORY.md)

The AI never decides the tier — this module does.
Content is classified by pattern analysis of what was said.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class MemoryTier(str, Enum):
    CACHE = "cache"
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"


@dataclass
class ClassificationResult:
    tier: MemoryTier
    category: str       # human-readable label: "preference", "decision", "task", "context", etc.
    confidence: float   # 0.0–1.0
    reason: str         # why it was classified this way


# ─── Pattern Definitions ──────────────────────────────────────────────────────

# Long-term: preferences, decisions, identity rules — these persist forever
LONG_TERM_PATTERNS = [
    # Explicit preferences
    (r"\b(always|never|prefers?|prefer|hates?|loves?|dislikes?|likes?)\b", "preference", 0.85),
    # Decisions made
    (r"\b(decided|decision|chose|choosing|will use|going with|from now on|rule:)\b", "decision", 0.9),
    # Identity/personality
    (r"\b(i am|i'm|my name|who i am|my identity|my role|my mission)\b", "identity", 0.8),
    # Absolute directives
    (r"\b(0-tolerance|zero tolerance|never commit|always check|mandatory|non-negotiable|core directive)\b", "directive", 0.95),
    # Stack/tool choices
    (r"\b(primary language|tech stack|main tool|use python|use node|use flutter|primary ai)\b", "stack_preference", 0.85),
    # Contact/access info
    (r"\b(my wallet|my address|my api key|my token|ssh host|my server)\b", "credentials_context", 0.75),
]

# Short-term: project state, tasks, ongoing work — useful for days/weeks
SHORT_TERM_PATTERNS = [
    # Active work
    (r"\b(working on|in progress|current task|currently|next step|todo|to do|backlog)\b", "task", 0.8),
    # Project status
    (r"\b(status:|progress:|blocked|blocker|waiting for|pending|needs|requires)\b", "project_status", 0.75),
    # Recent decisions with time bounds
    (r"\b(this week|this sprint|this month|for now|temporarily|short[- ]term)\b", "temp_decision", 0.7),
    # Numbers/metrics that change
    (r"\b(pnl|drawdown|balance|position|trade|order|signal|backtest result)\b", "trading_state", 0.7),
    # File/code locations being worked on
    (r"\b(in file|at line|function|class|module|branch|commit|pr #)\b", "code_context", 0.65),
]

# Cache: session noise, greetings, one-off questions — expires tonight
CACHE_PATTERNS = [
    # Greetings and filler
    (r"^(hi|hello|hey|what'?s up|good morning|good night|thanks?|thank you|ok|okay|sure|got it)\b", "greeting", 0.9),
    # Single-use questions
    (r"\b(what is|how do i|can you|could you|please|just|quick question)\b", "question", 0.6),
    # Session-specific commands
    (r"\b(show me|list|print|display|run|execute|check|verify)\b", "command", 0.55),
    # Time-bounded to today
    (r"\b(today|right now|at the moment|this session|just now)\b", "ephemeral", 0.7),
]

# High-signal override keywords — these force long-term regardless of other signals
FORCE_LONG_TERM = [
    r"\bremember (this|that|me|forever)\b",
    r"\bimportant:?\s",
    r"\bcore rule\b",
    r"\bnever forget\b",
    r"\bpermanent(ly)?\b",
    r"\blong[- ]term\b",
]

# High-signal override keywords — these force cache regardless of other signals
FORCE_CACHE = [
    r"\b(ignore this|test(ing)?|just checking|throwaway|scratch)\b",
    r"\b(lol|haha|hehe|xd)\b",
]


# ─── Classifier ───────────────────────────────────────────────────────────────

def classify(content: str) -> ClassificationResult:
    """
    Classify content into a memory tier.

    This is rule-based by design — fast, offline, no LLM needed.
    Good enough for 90% of cases. Future upgrade: pass to local LLM for edge cases.
    """
    text = content.lower().strip()

    # Force overrides first
    for pattern in FORCE_LONG_TERM:
        if re.search(pattern, text, re.IGNORECASE):
            return ClassificationResult(
                tier=MemoryTier.LONG_TERM,
                category="forced_long_term",
                confidence=0.99,
                reason=f"Force-long-term keyword matched: {pattern}"
            )

    for pattern in FORCE_CACHE:
        if re.search(pattern, text, re.IGNORECASE):
            return ClassificationResult(
                tier=MemoryTier.CACHE,
                category="noise",
                confidence=0.99,
                reason=f"Force-cache keyword matched: {pattern}"
            )

    # Score each tier
    lt_score, lt_cat, lt_reason = _score_patterns(text, LONG_TERM_PATTERNS)
    st_score, st_cat, st_reason = _score_patterns(text, SHORT_TERM_PATTERNS)
    ca_score, ca_cat, ca_reason = _score_patterns(text, CACHE_PATTERNS)

    # Length signal: very short content is likely cache noise
    words = len(text.split())
    if words < 4:
        ca_score = max(ca_score, 0.7)

    # Long, structured content with multiple sentences → probably worth keeping
    if words > 30 and text.count(".") > 2:
        lt_score = max(lt_score, 0.5)
        st_score = max(st_score, 0.45)

    # Decide
    best = max(lt_score, st_score, ca_score)

    if best == 0.0:
        # No signal — default to short-term (better to keep than lose)
        return ClassificationResult(
            tier=MemoryTier.SHORT_TERM,
            category="default",
            confidence=0.3,
            reason="No strong signal — defaulting to short_term"
        )

    if lt_score == best:
        return ClassificationResult(
            tier=MemoryTier.LONG_TERM,
            category=lt_cat,
            confidence=lt_score,
            reason=lt_reason
        )
    elif st_score == best:
        return ClassificationResult(
            tier=MemoryTier.SHORT_TERM,
            category=st_cat,
            confidence=st_score,
            reason=st_reason
        )
    else:
        return ClassificationResult(
            tier=MemoryTier.CACHE,
            category=ca_cat,
            confidence=ca_score,
            reason=ca_reason
        )


def _score_patterns(text: str, patterns: list[tuple]) -> tuple[float, str, str]:
    """Return (best_score, category, reason) from pattern list."""
    best_score = 0.0
    best_cat = "unknown"
    best_reason = ""
    for pattern, category, weight in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            if weight > best_score:
                best_score = weight
                best_cat = category
                best_reason = f"Pattern '{pattern}' matched (category={category})"
    return best_score, best_cat, best_reason


# ─── Tier → Vault Path ────────────────────────────────────────────────────────

from pathlib import Path
from datetime import datetime


def tier_to_vault_path(tier: MemoryTier, vault: Path, category: str = "") -> Path:
    """Map a memory tier to its vault file path."""
    today = datetime.utcnow().strftime("%Y-%m-%d")

    if tier == MemoryTier.CACHE:
        cache_dir = vault / "Cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / f"session-{today}.md"

    elif tier == MemoryTier.SHORT_TERM:
        short_dir = vault / "Archive" / "short"
        short_dir.mkdir(parents=True, exist_ok=True)
        return short_dir / f"{today}.md"

    elif tier == MemoryTier.LONG_TERM:
        archive_dir = vault / "Archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        return archive_dir / "MEMORY.md"

    raise ValueError(f"Unknown tier: {tier}")


def write_to_tier(content: str, tier: MemoryTier, vault: Path, category: str = "", source: str = "ai") -> Path:
    """Write content to the correct vault tier file. Returns the file path."""
    target = tier_to_vault_path(tier, vault, category)
    now_iso = datetime.utcnow().isoformat(timespec="seconds")

    if tier == MemoryTier.LONG_TERM:
        # Long-term: append as a structured bullet (dated, categorized)
        entry = f"- [{now_iso}] — {category} — {content.strip()}\n"
    else:
        # Cache + short-term: timestamped log entry
        entry = f"[{now_iso}] [{source}] {content.strip()}\n"

    with open(target, "a", encoding="utf-8") as f:
        f.write(entry)

    return target
