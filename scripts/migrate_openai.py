#!/usr/bin/env python3
"""
migrate_openai.py — Import ChatGPT history into Command Center vault

Reads OpenAI's conversations.json export, uses Claude to extract projects,
decisions, and preferences, then writes structured Markdown into vault/Migration/.

Usage:
    python scripts/migrate_openai.py --input ~/Downloads/conversations.json
    python scripts/migrate_openai.py --input ~/Downloads/openai-export/ --vault ./vault
    python scripts/migrate_openai.py --input conversations.json --dry-run
    python scripts/migrate_openai.py --input conversations.json --min-exchanges 3 --model claude-haiku-4-5-20251001

Requirements:
    pip install anthropic
    ANTHROPIC_API_KEY must be set in environment
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_conversations(input_path: Path) -> list[dict]:
    """Load conversations.json — handles file or directory (zip extract)."""
    if input_path.is_dir():
        candidate = input_path / "conversations.json"
        if not candidate.exists():
            sys.exit(f"No conversations.json found in {input_path}")
        input_path = candidate

    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data
    # Sometimes wrapped in a dict
    if isinstance(data, dict) and "conversations" in data:
        return data["conversations"]

    sys.exit("Unexpected conversations.json format.")


def extract_messages(conversation: dict) -> list[dict]:
    """
    Flatten the message tree (mapping) into a linear list ordered by time.
    Returns list of {role, text, ts} dicts.
    """
    mapping = conversation.get("mapping", {})
    if not mapping:
        return []

    # Build parent→children map and find root
    nodes = {}
    for node_id, node_data in mapping.items():
        msg = node_data.get("message")
        parent = node_data.get("parent")
        nodes[node_id] = {"msg": msg, "parent": parent, "children": node_data.get("children", [])}

    # Find root (no parent or parent is None/"")
    root_id = None
    for node_id, node in nodes.items():
        if not node["parent"] or node["parent"] not in nodes:
            root_id = node_id
            break

    if not root_id:
        return []

    # Walk tree depth-first following first child (main branch)
    messages = []
    current = root_id
    visited = set()

    while current and current not in visited:
        visited.add(current)
        node = nodes.get(current)
        if not node:
            break

        msg = node["msg"]
        if msg:
            role = msg.get("author", {}).get("role", "")
            content = msg.get("content", {})
            parts = content.get("parts", []) if isinstance(content, dict) else []
            text = " ".join(p for p in parts if isinstance(p, str)).strip()
            ts = msg.get("create_time") or 0

            if role in ("user", "assistant") and text:
                messages.append({"role": role, "text": text, "ts": ts})

        # Follow first child (main conversation branch)
        children = node.get("children", [])
        current = children[0] if children else None

    messages.sort(key=lambda m: m["ts"])
    return messages


def conversation_text(messages: list[dict], max_chars: int = 12000) -> str:
    """Format messages as readable text, truncated for API budget."""
    lines = []
    total = 0
    for m in messages:
        prefix = "USER" if m["role"] == "user" else "ASSISTANT"
        line = f"{prefix}: {m['text'][:1500]}\n"
        total += len(line)
        if total > max_chars:
            lines.append("... [truncated for length] ...")
            break
        lines.append(line)
    return "\n".join(lines)


def date_from_ts(ts: float | None) -> str:
    if not ts:
        return "unknown"
    return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")


def slug(text: str) -> str:
    """Make a safe filename from a title."""
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text[:60] or "untitled"


# ── Claude extraction ─────────────────────────────────────────────────────────

EXTRACTION_PROMPT = """You are analyzing a conversation from ChatGPT history to extract structured knowledge for a personal AI memory vault.

Conversation title: {title}
Date: {date}

Conversation:
{text}

Extract the following as JSON. Be specific and factual — only include what's actually discussed:

{{
  "skip": false,  // true if this is trivial (greetings, tests, random questions with no lasting value)
  "importance": 1,  // 1-5: 5=major project/decision, 4=significant, 3=useful, 2=minor, 1=trivial
  "category": "project|decision|preference|research|tool|planning|other",
  "project_name": "name of the project or null if no specific project",
  "summary": "2-4 sentence summary of what was discussed and concluded",
  "key_points": ["specific fact, decision, or insight 1", "fact 2", ...],  // max 8
  "tech_stack": ["technology1", "technology2"],  // tools, languages, APIs mentioned
  "decisions_made": ["decision 1", "decision 2"],  // concrete choices/conclusions
  "action_items": ["thing to do 1"],  // things planned or TODO'd
  "preferences_revealed": ["user preference 1"]  // how the user likes things done
}}

Return only valid JSON, no markdown fences."""


def analyze_conversation(client, conversation: dict, messages: list[dict], model: str) -> dict | None:
    """Call Claude to extract structured data from a conversation."""
    title = conversation.get("title", "Untitled")
    date = date_from_ts(conversation.get("create_time"))
    text = conversation_text(messages)

    prompt = EXTRACTION_PROMPT.format(title=title, date=date, text=text)

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        # Strip markdown fences if model added them anyway
        raw = re.sub(r"^```(?:json)?\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        return json.loads(raw)
    except (json.JSONDecodeError, Exception) as e:
        print(f"  [warn] Failed to parse response: {e}")
        return None


# ── Markdown writers ──────────────────────────────────────────────────────────

def write_project_note(vault: Path, project: str, entries: list[dict]):
    """Write a Knowledge note for a project with all its conversations."""
    path = vault / "Migration" / "Projects" / f"{slug(project)}.md"
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"---",
        f"project: {project}",
        f"migrated: {datetime.utcnow().strftime('%Y-%m-%d')}",
        f"source: openai-export",
        f"---",
        f"",
        f"# {project}",
        f"",
        f"*Migrated from ChatGPT history — {len(entries)} conversation(s)*",
        f"",
    ]

    # Collect all tech stack, decisions, action items across conversations
    all_tech = sorted(set(t for e in entries for t in (e.get("tech_stack") or [])))
    all_decisions = [d for e in entries for d in (e.get("decisions_made") or [])]
    all_actions = [a for e in entries for a in (e.get("action_items") or [])]
    all_prefs = [p for e in entries for p in (e.get("preferences_revealed") or [])]

    if all_tech:
        lines += ["## Tech Stack", ""]
        lines += [f"- {t}" for t in all_tech]
        lines += [""]

    if all_decisions:
        lines += ["## Decisions Made", ""]
        lines += [f"- {d}" for d in all_decisions]
        lines += [""]

    if all_actions:
        lines += ["## Action Items / Plans", ""]
        lines += [f"- [ ] {a}" for a in all_actions]
        lines += [""]

    if all_prefs:
        lines += ["## Preferences", ""]
        lines += [f"- {p}" for p in all_prefs]
        lines += [""]

    lines += ["## Conversation Log", ""]
    for e in sorted(entries, key=lambda x: x["date"]):
        lines += [
            f"### {e['title']} — {e['date']}",
            f"",
            e["summary"],
            f"",
        ]
        if e.get("key_points"):
            lines += [f"- {p}" for p in e["key_points"]]
            lines += [""]

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_preferences_note(vault: Path, entries: list[dict]):
    """Write a consolidated preferences/behavior note."""
    path = vault / "Migration" / "Preferences.md"
    path.parent.mkdir(parents=True, exist_ok=True)

    prefs = [p for e in entries for p in (e.get("preferences_revealed") or [])]
    decisions = [d for e in entries for d in (e.get("decisions_made") or [])
                 if e.get("category") == "preference"]

    lines = [
        "---",
        "migrated: " + datetime.utcnow().strftime("%Y-%m-%d"),
        "source: openai-export",
        "---",
        "",
        "# Preferences & Behavioral Patterns",
        "",
        "*Extracted from ChatGPT history — how you like things done.*",
        "",
    ]

    if prefs:
        lines += ["## Preferences", ""]
        seen = set()
        for p in prefs:
            if p.lower() not in seen:
                seen.add(p.lower())
                lines.append(f"- {p}")
        lines.append("")

    if decisions:
        lines += ["## Recurring Decisions", ""]
        for d in decisions:
            lines.append(f"- {d}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_summary(vault: Path, stats: dict, all_projects: set):
    """Write the master migration summary."""
    path = vault / "Migration" / "MIGRATION-SUMMARY.md"

    lines = [
        "---",
        "migrated: " + datetime.utcnow().strftime("%Y-%m-%d"),
        "source: openai-export",
        "---",
        "",
        "# Migration Summary — ChatGPT History",
        "",
        f"Migrated on {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC",
        "",
        "## Stats",
        "",
        f"| | |",
        f"|---|---|",
        f"| Conversations processed | {stats['processed']} |",
        f"| Skipped (trivial) | {stats['skipped']} |",
        f"| Projects identified | {len(all_projects)} |",
        f"| Notes created | {stats['notes_written']} |",
        "",
        "## Projects Found",
        "",
    ]
    for p in sorted(all_projects):
        lines.append(f"- [[Migration/Projects/{slug(p)}|{p}]]")

    lines += [
        "",
        "## Next Steps",
        "",
        "- Review each project note and merge into [[Knowledge/]] if relevant",
        "- Copy key preferences into [[Core/USER.md]]",
        "- Copy key decisions into [[Archive/MEMORY.md]]",
        "- Delete `Migration/` folder once integrated",
        "",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Migrate ChatGPT history into Command Center vault")
    parser.add_argument("--input", required=True, help="Path to conversations.json or export folder")
    parser.add_argument("--vault", default="./vault", help="Path to vault (default: ./vault)")
    parser.add_argument("--model", default="claude-haiku-4-5-20251001",
                        help="Claude model to use (default: claude-haiku-4-5-20251001)")
    parser.add_argument("--min-exchanges", type=int, default=2,
                        help="Minimum user+assistant exchanges to process a conversation (default: 2)")
    parser.add_argument("--importance", type=int, default=2,
                        help="Minimum importance score 1-5 to write a note (default: 2)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Analyze without writing files")
    parser.add_argument("--limit", type=int, default=0,
                        help="Process only first N conversations (for testing)")
    args = parser.parse_args()

    # Validate
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ANTHROPIC_API_KEY not set.")

    input_path = Path(args.input).expanduser()
    if not input_path.exists():
        sys.exit(f"Input not found: {input_path}")

    vault = Path(args.vault).expanduser()
    if not vault.exists():
        sys.exit(f"Vault not found: {vault}")

    # Load
    try:
        import anthropic
    except ImportError:
        sys.exit("anthropic not installed. Run: pip install anthropic")

    client = anthropic.Anthropic(api_key=api_key)

    print(f"\nCommand Center AI — OpenAI Migration")
    print(f"Input:  {input_path}")
    print(f"Vault:  {vault}")
    print(f"Model:  {args.model}")
    print(f"Mode:   {'DRY RUN' if args.dry_run else 'WRITE'}")
    print()

    conversations = load_conversations(input_path)
    if args.limit:
        conversations = conversations[:args.limit]

    print(f"Found {len(conversations)} conversations\n")

    # Process
    stats = {"processed": 0, "skipped": 0, "notes_written": 0}
    project_entries: dict[str, list] = {}  # project_name → list of entry dicts
    non_project_entries: list[dict] = []

    for i, conv in enumerate(conversations):
        title = conv.get("title", "Untitled")
        messages = extract_messages(conv)
        exchanges = sum(1 for m in messages if m["role"] == "user")

        if exchanges < args.min_exchanges:
            stats["skipped"] += 1
            continue

        print(f"[{i+1}/{len(conversations)}] {title[:70]}")

        result = analyze_conversation(client, conv, messages, args.model)
        if not result:
            stats["skipped"] += 1
            continue

        if result.get("skip") or result.get("importance", 0) < args.importance:
            print(f"  → skip (importance={result.get('importance', '?')})")
            stats["skipped"] += 1
            continue

        entry = {
            "title": title,
            "date": date_from_ts(conv.get("create_time")),
            "summary": result.get("summary", ""),
            "key_points": result.get("key_points", []),
            "tech_stack": result.get("tech_stack", []),
            "decisions_made": result.get("decisions_made", []),
            "action_items": result.get("action_items", []),
            "preferences_revealed": result.get("preferences_revealed", []),
            "category": result.get("category", "other"),
            "importance": result.get("importance", 1),
        }

        project = result.get("project_name")
        if project:
            project_entries.setdefault(project, []).append(entry)
        else:
            non_project_entries.append(entry)

        print(f"  → {result.get('category')} | importance={result.get('importance')} | project={project or 'none'}")
        stats["processed"] += 1

        # Polite rate limiting
        time.sleep(0.3)

    # Write files
    if not args.dry_run:
        print(f"\nWriting notes...")
        for project, entries in project_entries.items():
            path = write_project_note(vault, project, entries)
            print(f"  {path.relative_to(vault)}")
            stats["notes_written"] += 1

        if non_project_entries:
            path = write_preferences_note(vault, non_project_entries)
            print(f"  {path.relative_to(vault)}")
            stats["notes_written"] += 1

        path = write_summary(vault, stats, set(project_entries.keys()))
        print(f"  {path.relative_to(vault)}")
        stats["notes_written"] += 1

    # Report
    print(f"\n{'─'*50}")
    print(f"Processed : {stats['processed']}")
    print(f"Skipped   : {stats['skipped']}")
    print(f"Notes     : {stats['notes_written']}")
    print(f"Projects  : {len(project_entries)}")
    if project_entries:
        for p in sorted(project_entries.keys()):
            print(f"  · {p} ({len(project_entries[p])} conversations)")
    if args.dry_run:
        print("\n[DRY RUN — no files written]")
    else:
        print(f"\nOpen vault/Migration/ in Obsidian to review.")
        print(f"When done, merge into Knowledge/ and delete Migration/.")


if __name__ == "__main__":
    main()
