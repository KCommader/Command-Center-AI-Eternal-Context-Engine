"""
Vault Writer

Converts a classified ExportSummary into a structured Markdown file
written to vault/Migration/<PROVIDER>_<DATE>_ANALYSIS.md

Output stays LOCAL — vault/Migration/ is gitignored.
Only this tool ships in the repo.
"""
from __future__ import annotations

import datetime
import re
from collections import defaultdict
from pathlib import Path

from migration.base import ExportSummary, Conversation


def _tech_freq(conversations: list[Conversation]) -> dict[str, int]:
    techs = [
        "python", "flutter", "react", "c#", "typescript", "node",
        "fastapi", "openai", "claude", "nextjs", "next.js", "dart",
        "solidity", "rust", "go", "java", "swift", "kotlin", "php",
        "unity", "godot",
    ]
    freq: dict[str, int] = defaultdict(int)
    for c in conversations:
        text = (c.title + " " + c.user_msg + " " + c.asst_msg).lower()
        for t in techs:
            if t in text:
                freq[t] += 1
    return dict(sorted(freq.items(), key=lambda x: -x[1]))


def _usage_patterns(conversations: list[Conversation]) -> dict[str, int]:
    patterns = {
        "Building / Creating": ["build", "create", "add", "implement", "make", "generate", "write", "new"],
        "Debugging / Fixing": ["fix", "bug", "error", "issue", "debug", "problem", "not working", "broken", "crash"],
        "Learning / Asking": ["how to", "how do", "explain", "what is", "understand", "learn", "why does"],
        "Refactoring": ["refactor", "clean", "optimize", "improve", "rewrite", "update"],
        "Planning / Strategy": ["plan", "strategy", "roadmap", "should i", "best way", "approach"],
    }
    counts: dict[str, int] = {}
    for label, keywords in patterns.items():
        counts[label] = sum(
            1 for c in conversations
            if any(kw in c.title.lower() for kw in keywords)
        )
    return counts


def _artifact_preview(artifact: dict, max_chars: int = 2000) -> str:
    ext = artifact.get("ext", "")
    content = artifact.get("content", "")
    lang_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".cs": "csharp", ".go": "go", ".rs": "rust", ".java": "java",
        ".html": "html", ".css": "css", ".sh": "bash", ".sql": "sql",
        ".md": "markdown",
    }
    lang = lang_map.get(ext, "")

    lines = []
    lines.append(f"**File:** `{artifact['name']}`  ")
    lines.append(f"**Size:** {artifact['size']:,} chars  ")

    if ext == ".md":
        lines.append("")
        lines.append(content[:max_chars])
    else:
        lines.append("")
        lines.append(f"```{lang}")
        lines.append(content[:max_chars])
        lines.append("```")

    return "\n".join(lines)


def write_analysis(
    summary: ExportSummary,
    vault_path: str | Path,
    output_name: str | None = None,
) -> Path:
    """
    Write the full analysis Markdown to vault/Migration/.
    Returns the output file path.
    """
    vault = Path(vault_path)
    migration_dir = vault / "Migration"
    migration_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.date.today().strftime("%Y-%m-%d")
    if not output_name:
        output_name = f"{summary.provider.upper()}_{today}_ANALYSIS.md"
    output_path = migration_dir / output_name

    convos = summary.conversations
    grouped: dict[str, list[Conversation]] = defaultdict(list)
    for c in convos:
        grouped[c.category or "Other"].append(c)

    lines: list[str] = []

    # ── Header ───────────────────────────────────────────────────────────────
    lines += [
        f"# {summary.provider.title()} History Analysis",
        "",
        f"> Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"> Provider: {summary.provider.title()}",
        f"> Total conversations: {summary.total}",
        f"> Date range: {summary.date_range[0]} → {summary.date_range[1]}",
        "",
    ]

    # ── Volume table ─────────────────────────────────────────────────────────
    lines += [
        "## Volume by Category",
        "",
        "| Category | Conversations |",
        "|---|---|",
    ]
    for cat, cat_convos in sorted(grouped.items(), key=lambda x: -len(x[1])):
        lines.append(f"| {cat} | {len(cat_convos)} |")
    lines += ["", "---", ""]

    # ── Per-category breakdown ────────────────────────────────────────────────
    lines.append("## Projects Breakdown")
    lines.append("")

    for cat, cat_convos in sorted(grouped.items(), key=lambda x: -len(x[1])):
        sorted_c = sorted(cat_convos, key=lambda x: x.timestamp)
        recent = sorted(cat_convos, key=lambda x: x.timestamp, reverse=True)
        dr = f"{sorted_c[0].date} → {sorted_c[-1].date}"

        lines += [
            f"### {cat}",
            "",
            f"**{len(cat_convos)} conversations** | {dr}",
            "",
            "#### All Conversations",
            "",
        ]
        for c in sorted_c:
            lines.append(f"- `{c.date}` {c.title}")
        lines.append("")

        lines += ["#### Key Discussions", ""]
        shown = 0
        for c in recent:
            if shown >= 8:
                break
            if not c.user_msg:
                continue
            lines.append(f"**{c.title}** ({c.date})")
            lines.append(f"> **User:** {c.user_msg[:350]}")
            if c.asst_msg:
                lines += [">", f"> **Assistant:** {c.asst_msg[:350]}"]
            lines.append("")
            shown += 1

        last = recent[0]
        lines += [
            "#### Last Known State",
            f"Most recent: **{last.title}** ({last.date})",
        ]
        if last.user_msg:
            lines.append(f"Topic: {last.user_msg[:250]}")
        lines += ["", "---", ""]

    # ── Tech stack ───────────────────────────────────────────────────────────
    tech = _tech_freq(convos)
    if tech:
        lines += [
            "## Tech Stack Identified",
            "",
            "| Technology | Conversations |",
            "|---|---|",
        ]
        for t, count in tech.items():
            if count > 0:
                lines.append(f"| {t} | {count} |")
        lines.append("")

    # ── Usage patterns ───────────────────────────────────────────────────────
    patterns = _usage_patterns(convos)
    lines += [
        "## Usage Patterns",
        "",
        "| Pattern | Count |",
        "|---|---|",
    ]
    for label, count in patterns.items():
        lines.append(f"| {label} | {count} |")
    lines.append("")

    # ── Code artifacts ────────────────────────────────────────────────────────
    if summary.artifacts:
        lines += [
            "## Code Artifacts",
            "",
            f"{len(summary.artifacts)} files exported from conversations:",
            "",
        ]
        for art in summary.artifacts:
            lines.append(f"### `{art['name']}`")
            lines.append("")
            lines.append(_artifact_preview(art))
            lines.append("")

    # ── Full chronological index ──────────────────────────────────────────────
    lines += [
        "## Full Conversation Index",
        "",
        "| Date | Category | Title |",
        "|---|---|---|",
    ]
    for c in convos:
        safe_title = c.title.replace("|", "-").replace("\n", " ")
        lines.append(f"| {c.date} | {c.category or 'Other'} | {safe_title} |")
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
