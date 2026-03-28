"""
History Ingester
================
Parse conversation exports from Claude, ChatGPT, and Gemini.
Extract everything with lasting value. Discard noise.
Store to the Command Center vault and index in LanceDB.

Usage:
    python -m engine.history_ingester <export_file_or_dir> --provider <claude|gpt|gemini>
    python -m engine.history_ingester --help

Providers:
    claude   — conversations.json from claude.ai → Settings → Export Data
    gpt      — conversations.json from chat.openai.com → Settings → Export Data
    gemini   — Takeout/Gemini Apps Activity/*.json from Google Takeout

Output:
    vault/History/<provider>/          — per-conversation notes (full content, not summaries)
    vault/Projects/<name>.md           — extracted project files
    vault/Goals/<name>.md              — extracted goals and intentions
    vault/Archive/MEMORY.md            — long-term preferences and decisions (appended)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator

# ── Vault and engine paths ─────────────────────────────────────────────────────

_HERE = Path(__file__).parent
_DEFAULT_VAULT = _HERE.parent / "vault"

# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class Message:
    role: str           # "human" or "assistant"
    text: str
    timestamp: str = ""


@dataclass
class Conversation:
    id: str
    title: str
    provider: str
    created_at: str
    messages: list[Message] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        parts = []
        for m in self.messages:
            label = "Human" if m.role == "human" else "Assistant"
            parts.append(f"**{label}:** {m.text}")
        return "\n\n".join(parts)

    @property
    def word_count(self) -> int:
        return sum(len(m.text.split()) for m in self.messages)


# ── Parsers ────────────────────────────────────────────────────────────────────

def parse_claude(data: list | dict) -> Iterator[Conversation]:
    """
    Claude export format (claude.ai → Settings → Export Data).
    Top-level list of conversation objects, each with chat_messages.

    {
      "uuid": "...",
      "name": "Conversation title",
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "...",
      "chat_messages": [
        {
          "uuid": "...",
          "sender": "human" | "assistant",
          "text": "...",
          "created_at": "..."
        }
      ]
    }
    """
    if isinstance(data, dict):
        data = [data]

    for conv in data:
        messages = []
        for msg in conv.get("chat_messages", []):
            text = msg.get("text", "").strip()
            if not text:
                # Handle structured content (attachments etc)
                content = msg.get("content", [])
                if isinstance(content, list):
                    text = " ".join(
                        p.get("text", "") for p in content
                        if isinstance(p, dict) and p.get("type") == "text"
                    ).strip()
            if text:
                messages.append(Message(
                    role="human" if msg.get("sender") == "human" else "assistant",
                    text=text,
                    timestamp=msg.get("created_at", ""),
                ))

        if messages:
            yield Conversation(
                id=conv.get("uuid", ""),
                title=conv.get("name", "Untitled"),
                provider="claude",
                created_at=conv.get("created_at", ""),
                messages=messages,
            )


def parse_gpt(data: list | dict) -> Iterator[Conversation]:
    """
    ChatGPT export format (chat.openai.com → Settings → Export Data).
    Top-level list of conversations with a mapping tree.

    {
      "id": "...",
      "title": "...",
      "create_time": 1234567890,
      "mapping": {
        "node-id": {
          "message": {
            "author": {"role": "user"|"assistant"|"system"|"tool"},
            "content": {"parts": ["text..."] | {"content_type": "text", "parts": [...]}},
            "create_time": 1234567890
          },
          "parent": "...",
          "children": ["..."]
        }
      }
    }
    """
    if isinstance(data, dict):
        data = [data]

    for conv in data:
        mapping = conv.get("mapping", {})
        # Walk tree in order (BFS from root)
        ordered = _walk_gpt_tree(mapping)
        messages = []
        for node in ordered:
            msg = node.get("message")
            if not msg:
                continue
            author = msg.get("author", {}).get("role", "")
            if author not in ("user", "assistant"):
                continue

            content = msg.get("content", {})
            text = ""
            if isinstance(content, dict):
                parts = content.get("parts", [])
                text = " ".join(p for p in parts if isinstance(p, str)).strip()
            elif isinstance(content, str):
                text = content.strip()

            if text:
                ts = msg.get("create_time", 0)
                messages.append(Message(
                    role="human" if author == "user" else "assistant",
                    text=text,
                    timestamp=datetime.utcfromtimestamp(ts).isoformat() if ts else "",
                ))

        if messages:
            ct = conv.get("create_time", 0)
            yield Conversation(
                id=conv.get("id", ""),
                title=conv.get("title", "Untitled"),
                provider="gpt",
                created_at=datetime.utcfromtimestamp(ct).isoformat() if ct else "",
                messages=messages,
            )


def _walk_gpt_tree(mapping: dict) -> list[dict]:
    """Traverse GPT mapping tree in message order (find root, walk children)."""
    # Find root (node with no parent or parent not in mapping)
    root_id = None
    for node_id, node in mapping.items():
        parent = node.get("parent")
        if parent is None or parent not in mapping:
            root_id = node_id
            break

    if not root_id:
        # Fallback: return all nodes
        return list(mapping.values())

    result = []
    queue = [root_id]
    visited = set()
    while queue:
        nid = queue.pop(0)
        if nid in visited:
            continue
        visited.add(nid)
        node = mapping.get(nid, {})
        result.append(node)
        for child in node.get("children", []):
            queue.append(child)
    return result


def parse_gemini(data: list | dict) -> Iterator[Conversation]:
    """
    Google Takeout / Gemini export.
    Can be a JSON file or directory of JSON files.

    Typical Gemini Takeout format:
    {
      "conversations": [
        {
          "conversation_id": "...",
          "conversation_state": {
            "conversation_id": {"chat_id": "..."},
            "conversation": {
              "conversation_id": {"chat_id": "..."},
              "current_message": [
                {
                  "create_time": "...",
                  "message_content": {"content": "...", "role": "USER"|"MODEL"}
                }
              ]
            }
          }
        }
      ]
    }

    Also handles simplified format: [{"title": ..., "messages": [...]}]
    """
    if isinstance(data, dict):
        # Takeout wrapper
        convs = data.get("conversations", data.get("conversation", [data]))
        if isinstance(convs, dict):
            convs = [convs]
    else:
        convs = data

    for idx, conv in enumerate(convs):
        messages = []
        title = conv.get("title", conv.get("name", f"Gemini conversation {idx+1}"))
        conv_id = conv.get("conversation_id", conv.get("id", str(idx)))

        # Try simplified format first
        simple_msgs = conv.get("messages", conv.get("chat_messages", []))
        if simple_msgs:
            for msg in simple_msgs:
                role_raw = msg.get("role", msg.get("sender", "")).upper()
                role = "human" if role_raw in ("USER", "HUMAN") else "assistant"
                text = msg.get("content", msg.get("text", "")).strip()
                if text:
                    messages.append(Message(role=role, text=text,
                                            timestamp=msg.get("create_time", msg.get("created_at", ""))))
        else:
            # Try deep Takeout format
            state = conv.get("conversation_state", {})
            inner = state.get("conversation", {})
            msg_list = inner.get("current_message", inner.get("message", []))
            for msg in msg_list:
                content_block = msg.get("message_content", {})
                text = content_block.get("content", content_block.get("text", "")).strip()
                role_raw = content_block.get("role", "MODEL").upper()
                role = "human" if role_raw in ("USER", "HUMAN") else "assistant"
                if text:
                    messages.append(Message(role=role, text=text,
                                            timestamp=msg.get("create_time", "")))

        if messages:
            yield Conversation(
                id=str(conv_id),
                title=str(title),
                provider="gemini",
                created_at=messages[0].timestamp if messages else "",
                messages=messages,
            )


# ── Value filter ───────────────────────────────────────────────────────────────

# Phrases that signal a message is noise (no lasting value)
_NOISE_PATTERNS = re.compile(
    r"^(hi|hello|hey|ok|okay|sure|got it|thanks?|thank you|great|perfect|sounds good|"
    r"yes|no|yep|nope|correct|right|exactly|understood|alright|cool|nice|awesome|wow|"
    r"good morning|good night|see you|bye|goodbye|\.{1,3}|👍|✅)[\s!.]*$",
    re.IGNORECASE,
)

_MIN_WORD_COUNT = 8   # Messages shorter than this are noise unless they contain keywords
_HIGH_VALUE_KEYWORDS = re.compile(
    r"\b(project|build|architecture|deploy|implement|design|plan|goal|strategy|"
    r"always|never|prefer|decide|chose|decision|rule:|directive|stack|framework|"
    r"bug|fix|error|crash|problem|solution|approach|pattern|api|database|"
    r"wallet|contract|trading|position|strategy|bot|signal|token|chain|"
    r"revenue|cost|deadline|launch|release|version|roadmap|milestone|"
    r"remember|important|critical|key|must|should|need to|requirement)\b",
    re.IGNORECASE,
)


def is_valuable(msg: Message) -> bool:
    """Return True if this message has lasting value worth storing."""
    text = msg.text.strip()
    if not text:
        return False
    if _NOISE_PATTERNS.match(text):
        return False
    words = len(text.split())
    if words < _MIN_WORD_COUNT:
        # Short messages: only keep if they contain high-value keywords
        return bool(_HIGH_VALUE_KEYWORDS.search(text))
    return True


def should_keep_conversation(conv: Conversation) -> bool:
    """Return True if this conversation has enough value to store."""
    valuable = [m for m in conv.messages if is_valuable(m)]
    # Keep if at least 2 valuable messages or >100 words of valuable content
    if len(valuable) < 2:
        return False
    total_words = sum(len(m.text.split()) for m in valuable)
    return total_words >= 50


# ── Project / goal extractor ──────────────────────────────────────────────────

_PROJECT_PATTERNS = re.compile(
    r"\b(kaiju|antigravity|smartkitchen|smart kitchen|polymarket|hyperliquid|"
    r"command center|openclaw|flutter|trading bot|fvg|kaiju_poly|kaiju_hl|"
    r"(?:project|app|system|platform|bot|tool|site|service)\s+(?:called|named|for)\s+\w+)\b",
    re.IGNORECASE,
)

_GOAL_PATTERNS = re.compile(
    r"\b(goal|objective|aim|target|want to|trying to|plan to|going to|"
    r"need to achieve|working towards|vision|mission|milestone)\b",
    re.IGNORECASE,
)

_DECISION_PATTERNS = re.compile(
    r"\b(decided|decision|chose|going with|will use|from now on|"
    r"the plan is|architecture is|stack is|approach is)\b",
    re.IGNORECASE,
)


def extract_projects_from_conv(conv: Conversation) -> set[str]:
    """Extract project names mentioned in this conversation."""
    projects = set()
    full = conv.title + " " + conv.full_text
    for match in _PROJECT_PATTERNS.finditer(full):
        name = match.group(0).strip().lower()
        # Normalize
        name = re.sub(r"\s+", "-", name)
        name = re.sub(r"[^a-z0-9\-_]", "", name)
        if len(name) > 2:
            projects.add(name)
    return projects


# ── Vault writer ───────────────────────────────────────────────────────────────

def _slug(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:80].strip("-")


def write_conversation_note(conv: Conversation, vault: Path) -> Path:
    """Write a conversation as a vault note. Returns the path written."""
    dest_dir = vault / "History" / conv.provider
    dest_dir.mkdir(parents=True, exist_ok=True)

    date_prefix = ""
    if conv.created_at:
        try:
            dt = datetime.fromisoformat(conv.created_at.rstrip("Z"))
            date_prefix = dt.strftime("%Y-%m-%d-")
        except Exception:
            pass

    title_slug = _slug(conv.title)[:60]
    file_name = f"{date_prefix}{title_slug}.md"
    dest = dest_dir / file_name

    # Build content — keep ALL valuable messages verbatim
    valuable = [m for m in conv.messages if is_valuable(m)]
    lines = [
        "---",
        f"namespace: history",
        f"source: {conv.provider}",
        f"conversation_id: {conv.id}",
        f"title: {json.dumps(conv.title)}",
        f"created_at: {conv.created_at}",
        f"imported_at: {datetime.utcnow().isoformat()}",
        "---",
        "",
        f"# {conv.title}",
        "",
    ]

    for msg in valuable:
        label = "**You:**" if msg.role == "human" else f"**{conv.provider.title()}:**"
        lines.append(f"{label}")
        lines.append("")
        lines.append(msg.text.strip())
        lines.append("")
        lines.append("---")
        lines.append("")

    dest.write_text("\n".join(lines), encoding="utf-8")
    return dest


def update_project_map(projects: dict[str, list[str]], vault: Path) -> list[Path]:
    """
    Write or update vault/Projects/<name>.md for each extracted project.
    projects: {project_name: [list of conversation titles mentioning it]}
    """
    proj_dir = vault / "Projects"
    proj_dir.mkdir(parents=True, exist_ok=True)
    written = []

    for proj_name, conv_titles in projects.items():
        dest = proj_dir / f"{proj_name}.md"
        if dest.exists():
            # Append new conversation references
            existing = dest.read_text(encoding="utf-8")
            new_refs = [t for t in conv_titles if t not in existing]
            if new_refs:
                with open(dest, "a", encoding="utf-8") as f:
                    f.write("\n".join([f"- {t}" for t in new_refs]) + "\n")
        else:
            # Create new project file
            lines = [
                "---",
                f"namespace: projects",
                f"project: {proj_name}",
                f"created_from: history_import",
                f"created_at: {datetime.utcnow().isoformat()}",
                "---",
                "",
                f"# {proj_name}",
                "",
                "## Conversations referencing this project",
                "",
            ]
            lines += [f"- {t}" for t in conv_titles]
            lines += ["", "## Notes", "", "_Auto-created from history import. Enrich this file manually._", ""]
            dest.write_text("\n".join(lines), encoding="utf-8")
        written.append(dest)

    return written


# ── Index written files ────────────────────────────────────────────────────────

def index_files(files: list[Path], vault: Path, verbose: bool = True) -> int:
    """Index newly written vault files into LanceDB."""
    try:
        from engine.engine import OmniscienceEngine
        engine = OmniscienceEngine(vault=vault)
        count = 0
        for f in files:
            n = engine.index_file(f, quiet=not verbose, force=True, persist_manifest=False, invalidate_cache=False)
            count += n
        engine._save_manifest()
        engine._invalidate_query_cache()
        return count
    except Exception as e:
        if verbose:
            print(f"  ⚠️  Indexing skipped: {e}")
        return 0


# ── Main ingestion pipeline ────────────────────────────────────────────────────

def ingest(
    source: Path,
    provider: str,
    vault: Path = _DEFAULT_VAULT,
    dry_run: bool = False,
    verbose: bool = True,
    skip_index: bool = False,
    limit: int = 0,          # 0 = no limit
) -> dict:
    """
    Main entry point. Parse, filter, extract, store.

    Returns stats dict with counts.
    """
    provider = provider.lower()
    if provider not in ("claude", "gpt", "gemini"):
        raise ValueError(f"Unknown provider: {provider}. Use claude, gpt, or gemini.")

    # ── Load file(s) ──────────────────────────────────────────────────────────
    if source.is_dir():
        json_files = list(source.rglob("*.json"))
        if verbose:
            print(f"📂 Found {len(json_files)} JSON files in {source}")
    else:
        json_files = [source]

    all_conversations: list[Conversation] = []
    for jf in json_files:
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception as e:
            if verbose:
                print(f"  ⚠️  Skipping {jf.name}: {e}")
            continue

        parser = {"claude": parse_claude, "gpt": parse_gpt, "gemini": parse_gemini}[provider]
        try:
            convs = list(parser(data))
            all_conversations.extend(convs)
        except Exception as e:
            if verbose:
                print(f"  ⚠️  Parse error in {jf.name}: {e}")

    if verbose:
        print(f"\n📊 Parsed {len(all_conversations)} conversations from {provider}")

    # ── Filter ────────────────────────────────────────────────────────────────
    valuable_convs = [c for c in all_conversations if should_keep_conversation(c)]
    dropped = len(all_conversations) - len(valuable_convs)

    if limit > 0:
        valuable_convs = valuable_convs[:limit]

    if verbose:
        print(f"🔍 Filter: {len(valuable_convs)} kept, {dropped} dropped (noise/fluff)")

    if dry_run:
        print("\n[DRY RUN] Would write:")
        for c in valuable_convs[:10]:
            print(f"  • {c.title[:70]} ({c.word_count} words, {len(c.messages)} messages)")
        if len(valuable_convs) > 10:
            print(f"  ... and {len(valuable_convs) - 10} more")
        return {"total": len(all_conversations), "kept": len(valuable_convs), "dropped": dropped}

    # ── Write conversation notes ───────────────────────────────────────────────
    written_files: list[Path] = []
    project_map: dict[str, list[str]] = defaultdict(list)

    for idx, conv in enumerate(valuable_convs):
        if verbose and idx % 50 == 0:
            print(f"  Writing {idx+1}/{len(valuable_convs)}...", end="\r")

        path = write_conversation_note(conv, vault)
        written_files.append(path)

        # Track project mentions
        for proj in extract_projects_from_conv(conv):
            project_map[proj].append(conv.title)

    if verbose:
        print(f"  ✅ Wrote {len(written_files)} conversation notes")

    # ── Write project map ─────────────────────────────────────────────────────
    proj_files = []
    if project_map:
        proj_files = update_project_map(project_map, vault)
        if verbose:
            print(f"  🗺️  Updated/created {len(proj_files)} project files:")
            for proj_name in sorted(project_map.keys()):
                print(f"      {proj_name} ({len(project_map[proj_name])} conversations)")

    # ── Index ─────────────────────────────────────────────────────────────────
    all_files = written_files + proj_files
    if not skip_index and all_files:
        if verbose:
            print(f"\n🔢 Indexing {len(all_files)} files into LanceDB...")
        chunks = index_files(all_files, vault, verbose=False)
        if verbose:
            print(f"  ✅ Indexed {chunks} chunks")
    elif skip_index and verbose:
        print(f"\n⏭️  Skipping index (--skip-index). Run `omniscience reindex` later.")

    stats = {
        "total": len(all_conversations),
        "kept": len(valuable_convs),
        "dropped": dropped,
        "files_written": len(written_files),
        "projects_updated": len(proj_files),
        "provider": provider,
    }

    if verbose:
        print(f"\n{'='*55}")
        print(f"✅ Import complete — {provider}")
        print(f"   Conversations parsed:  {stats['total']:>6}")
        print(f"   Kept (valuable):       {stats['kept']:>6}")
        print(f"   Dropped (noise):       {stats['dropped']:>6}")
        print(f"   Notes written:         {stats['files_written']:>6}")
        print(f"   Project files:         {stats['projects_updated']:>6}")
        print(f"   Vault: {vault}")

    return stats


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Import AI conversation history into the Command Center vault.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Import Claude history export
  python -m engine.history_ingester ~/Downloads/claude_export/conversations.json --provider claude

  # Import ChatGPT history
  python -m engine.history_ingester ~/Downloads/chatgpt_export/conversations.json --provider gpt

  # Import Gemini Takeout (directory or single file)
  python -m engine.history_ingester ~/Downloads/Takeout/Gemini\\ Apps\\ Activity/ --provider gemini

  # Dry run — see what would be imported without writing anything
  python -m engine.history_ingester conversations.json --provider claude --dry-run

  # Import but skip LanceDB indexing (index manually later)
  python -m engine.history_ingester conversations.json --provider gpt --skip-index

  # Limit to first 100 conversations (useful for testing)
  python -m engine.history_ingester conversations.json --provider claude --limit 100
        """
    )
    parser.add_argument("source", type=Path, help="Path to export file or directory")
    parser.add_argument("--provider", "-p", required=True,
                        choices=["claude", "gpt", "gemini"],
                        help="Which AI provider this export is from")
    parser.add_argument("--vault", type=Path, default=_DEFAULT_VAULT,
                        help="Vault directory (default: auto-detected)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be imported without writing anything")
    parser.add_argument("--skip-index", action="store_true",
                        help="Write files but skip LanceDB indexing (index manually later)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Only process first N conversations (0 = all)")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Suppress progress output")

    args = parser.parse_args()

    if not args.source.exists():
        print(f"Error: {args.source} does not exist", file=sys.stderr)
        sys.exit(1)

    ingest(
        source=args.source,
        provider=args.provider,
        vault=args.vault,
        dry_run=args.dry_run,
        verbose=not args.quiet,
        skip_index=args.skip_index,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
