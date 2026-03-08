"""
Vault Writer — Obsidian-native output with full color callouts.

Each category gets its own color callout type, TOC, internal links,
key discussion cards, and auto-generated summary paragraphs.
Output: vault/Migration/<PROVIDER>_<DATE>_ANALYSIS.md (gitignored)
"""
from __future__ import annotations

import datetime
from collections import defaultdict, Counter
from pathlib import Path

from migration.base import ExportSummary, Conversation

# ── Category metadata — callout type + color label + auto-summary keywords ──

CATEGORY_META: dict[str, dict] = {
    "Crypto Trading": {
        "callout": "crypto",
        "label": "Crypto Trading",
        "themes": ["LTR", "signal strategy", "exchange", "prediction market", "orderflow",
                   "hedge fund", "futures", "signal-framework", "volume indicator", "gap analysis", "trading platform", "order flow tool"],
    },
    "AI / Bots / Automation": {
        "callout": "ai-bots",
        "label": "AI / Bots / Automation",
        "themes": ["Claude", "MCP", "Command Center", "automation", "agents",
                   "n8n", "automation framework", "AI council", "ai-project", "local AI"],
    },
    "NFTs / Web3": {
        "callout": "web3",
        "label": "NFTs / Web3",
        "themes": ["NFT project", "NFT", "smart contract", "DAO",
                   "Solidity", "OpenSea", "trademark", "DePIN"],
    },
    "Flutter / Mobile": {
        "callout": "flutter",
        "label": "Flutter / Mobile Apps",
        "themes": ["Mobile-App", "Fitness App", "Flutter", "Dart",
                   "athlete", "workout tracking", "Odyssey"],
    },
    "Web Development": {
        "callout": "webdev",
        "label": "Web Development",
        "themes": ["React", "Next.js", "web project", "landing page",
                   "3D scroll", "website", "Three.js"],
    },
    "Fitness / Health": {
        "callout": "fitness",
        "label": "Fitness / Health",
        "themes": ["certification", "fitness competition", "health optimization", "athlete",
                   "nutrition", "supplement stack", "Fitness App"],
    },
    "Business / Brand": {
        "callout": "business",
        "label": "Business / Brand",
        "themes": ["Commander Capital", "AlphaEngine", "dropshipping", "ecommerce project",
                   "brand identity", "trademark", "revenue model"],
    },
    "Writing / Creative": {
        "callout": "creative",
        "label": "Writing / Creative",
        "themes": ["content empire", "YouTube channel", "faceless brand",
                   "fund journey timeline", "brand identity", "social media"],
    },
    "Personal / General": {
        "callout": "personal",
        "label": "Personal / General",
        "themes": ["Puerto Rico", "homestead", "garden", "credit strategy",
                   "resume", "legal docs", "fermentation"],
    },
    "DevOps / Infra": {
        "callout": "devops",
        "label": "DevOps / Infrastructure",
        "themes": ["Linux", "Ubuntu", "Docker", "server", "GPU", "ROCm",
                   "systemd", "Arch", "Hyper-V"],
    },
    "Python / Data": {
        "callout": "python",
        "label": "Python / Data Science",
        "themes": ["pandas", "SQL", "data pipeline", "backtesting",
                   "scraping", "machine learning"],
    },
    "Other": {
        "callout": "other",
        "label": "Other / Uncategorized",
        "themes": [],
    },
}

# Fallback for any category not in the meta dict
_DEFAULT_META = {"callout": "other", "label": "Other", "themes": []}

# ── Heading slug for Obsidian internal links ──

def _slug(text: str) -> str:
    """Convert category label to Obsidian heading link slug."""
    return text.replace("/", "").replace("  ", " ").strip()


# ── Category summary auto-generator ──

def _build_summary(cat: str, convos: list[Conversation]) -> str:
    """Generate a 2-sentence summary of a category from conversation data."""
    meta = CATEGORY_META.get(cat, _DEFAULT_META)
    themes = meta["themes"]
    total = len(convos)
    dates = [c.date for c in convos if c.date != "Unknown"]
    dr = f"{dates[0]} → {dates[-1]}" if dates else "unknown period"

    # Find matching themes in the actual conversations
    all_text = " ".join(
        (c.title + " " + c.user_msg + " " + c.asst_msg).lower()
        for c in convos
    )
    matched = [t for t in themes if t.lower() in all_text][:5]

    # Build sentence
    if matched:
        themes_str = ", ".join(matched)
        line1 = f"{total} conversations across {dr}. Key topics: **{themes_str}**."
    else:
        line1 = f"{total} conversations across {dr}."

    # Find most common title words as activity signal
    title_words = []
    for c in convos:
        title_words.extend(
            w for w in c.title.lower().split()
            if len(w) > 4 and w not in {
                "analysis", "breakdown", "overview", "request", "guide",
                "strategy", "update", "review", "about", "with", "from",
                "what", "this", "that", "your", "their"
            }
        )
    top_words = [w for w, _ in Counter(title_words).most_common(5)]

    if top_words:
        line2 = f"Most active themes: *{', '.join(top_words)}*."
    else:
        line2 = ""

    return f"{line1} {line2}".strip()


# ── Tech stack frequency ──

def _tech_freq(conversations: list[Conversation]) -> dict[str, int]:
    techs = [
        "python", "flutter", "react", "c#", "typescript", "node",
        "fastapi", "openai", "claude", "nextjs", "next.js", "dart",
        "solidity", "rust", "go", "java", "unity", "godot",
    ]
    freq: dict[str, int] = defaultdict(int)
    for c in conversations:
        text = (c.title + " " + c.user_msg + " " + c.asst_msg).lower()
        for t in techs:
            if t in text:
                freq[t] += 1
    return {k: v for k, v in sorted(freq.items(), key=lambda x: -x[1]) if v > 0}


# ── Artifact preview ──

def _artifact_section(artifact: dict, max_chars: int = 2000) -> list[str]:
    ext = artifact.get("ext", "")
    content = artifact.get("content", "")
    lang_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".cs": "csharp", ".go": "go", ".rs": "rust", ".html": "html",
        ".css": "css", ".sh": "bash", ".sql": "sql", ".md": "markdown",
    }
    lang = lang_map.get(ext, "")
    lines = [f"#### `{artifact['name']}`", ""]
    lines.append(f"> **Path:** `{artifact['path']}`  ")
    lines.append(f"> **Size:** {artifact['size']:,} chars")
    lines.append("")
    if ext == ".md":
        lines.append(content[:max_chars])
    else:
        lines.append(f"```{lang}")
        lines.append(content[:max_chars])
        lines.append("```")
    lines.append("")
    return lines


# ── Main writer ──

def write_analysis(
    summary: ExportSummary,
    vault_path: str | Path,
    output_name: str | None = None,
) -> Path:
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

    # Sort categories by count desc
    sorted_cats = sorted(grouped.items(), key=lambda x: -len(x[1]))

    lines: list[str] = []

    # ── Frontmatter ──────────────────────────────────────────────────────────
    tags = ["migration", f"provider/{summary.provider}"] + [
        f"category/{cat.lower().replace(' ', '-').replace('/', '')}"
        for cat in grouped
    ]
    lines += [
        "---",
        f"created: {today}",
        f"provider: {summary.provider}",
        f"total_conversations: {summary.total}",
        f"date_range: \"{summary.date_range[0]} → {summary.date_range[1]}\"",
        f"tags: [{', '.join(tags)}]",
        "---",
        "",
    ]

    # ── Migration banner callout ──────────────────────────────────────────────
    lines += [
        "> [!migration] Migration Analysis — " + summary.provider.title(),
        f"> **{summary.total} conversations** imported · {summary.date_range[0]} → {summary.date_range[1]}",
        f"> Generated {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} · {len(grouped)} categories · {len(summary.artifacts)} code artifacts",
        "",
    ]

    # ── Table of Contents ─────────────────────────────────────────────────────
    lines += ["## Navigation", ""]
    for cat, cat_convos in sorted_cats:
        meta = CATEGORY_META.get(cat, _DEFAULT_META)
        label = meta["label"]
        slug = _slug(label)
        lines.append(f"- [[#{slug}|{label}]] — {len(cat_convos)} conversations")
    lines += [
        f"- [[#Tech Stack|Tech Stack]]",
        f"- [[#Code Artifacts|Code Artifacts]]",
        f"- [[#Full Conversation Index|Full Index ({summary.total} conversations)]]",
        "",
        "---",
        "",
    ]

    # ── Volume summary table (plain markdown) ────────────────────────────────
    lines += [
        "## Volume by Category",
        "",
        "| Category | Count | Date Range |",
        "|---|---|---|",
    ]
    for cat, cat_convos in sorted_cats:
        meta = CATEGORY_META.get(cat, _DEFAULT_META)
        label = meta["label"]
        slug = _slug(label)
        dates = [c.date for c in cat_convos if c.date != "Unknown"]
        dr = f"{dates[0]} → {dates[-1]}" if dates else "—"
        lines.append(f"| [[#{slug}\\|**{label}**]] | {len(cat_convos)} | {dr} |")
    lines += ["", "---", ""]

    # ── Per-category sections ─────────────────────────────────────────────────
    lines.append("## Projects Breakdown")
    lines.append("")

    for cat, cat_convos in sorted_cats:
        meta = CATEGORY_META.get(cat, _DEFAULT_META)
        callout = meta["callout"]
        label = meta["label"]
        sorted_c = sorted(cat_convos, key=lambda x: x.timestamp)
        recent = sorted(cat_convos, key=lambda x: x.timestamp, reverse=True)
        dates = [c.date for c in sorted_c if c.date != "Unknown"]
        dr = f"{dates[0]} → {dates[-1]}" if dates else "—"
        slug = _slug(label)
        summary_text = _build_summary(cat, cat_convos)

        # Category header callout
        lines += [
            f"### {label}",
            "",
            f"> [!{callout}] {label} — {len(cat_convos)} conversations",
            f"> {dr}",
            f">",
            f"> {summary_text}",
            "",
        ]

        # All conversations list (collapsed after 20 via Obsidian fold)
        lines += ["#### All Conversations", ""]
        for c in sorted_c:
            lines.append(f"- `{c.date}` {c.title}")
        lines.append("")

        # Key discussions as callout cards
        if any(c.user_msg for c in recent):
            lines += ["#### Key Discussions", ""]
            shown = 0
            for c in recent:
                if shown >= 6:
                    break
                if not c.user_msg:
                    continue
                lines += [
                    f"> [!discussion] {c.title} · {c.date}",
                    f"> **User:** {c.user_msg[:280]}",
                ]
                if c.asst_msg:
                    lines += [
                        f">",
                        f"> **Assistant:** {c.asst_msg[:280]}",
                    ]
                lines.append("")
                shown += 1

        # Last state
        last = recent[0]
        lines += [
            "#### Last Known State",
            f"> Most recent: **{last.title}** ({last.date})",
        ]
        if last.user_msg:
            lines.append(f"> {last.user_msg[:200]}")
        lines += ["", "---", ""]

    # ── Tech stack ────────────────────────────────────────────────────────────
    tech = _tech_freq(convos)
    if tech:
        lines += [
            "## Tech Stack",
            "",
            "> [!ai-bots] Technologies Referenced Across All Conversations",
            ">",
        ]
        for t, count in tech.items():
            bar = "█" * min(count // 5 + 1, 20)
            lines.append(f"> `{t}` {bar} {count}")
        lines += ["", ""]

    # ── Code artifacts ────────────────────────────────────────────────────────
    if summary.artifacts:
        lines += [
            "## Code Artifacts",
            "",
            f"> [!knowledge] {len(summary.artifacts)} files exported from AI sessions",
            "",
        ]
        for art in summary.artifacts:
            lines.extend(_artifact_section(art))

    # ── Full chronological index ──────────────────────────────────────────────
    lines += [
        "## Full Conversation Index",
        "",
        f"All {summary.total} conversations in chronological order:",
        "",
        "| Date | Category | Title |",
        "|---|---|---|",
    ]
    for c in convos:
        safe_title = c.title.replace("|", "-").replace("\n", " ")
        meta = CATEGORY_META.get(c.category or "Other", _DEFAULT_META)
        lines.append(f"| `{c.date}` | {meta['label']} | {safe_title} |")
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
