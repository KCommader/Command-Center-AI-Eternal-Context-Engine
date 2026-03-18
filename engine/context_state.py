from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ACTIVE_CONTEXT_PATH = "Core/ACTIVE_CONTEXT.md"
SESSION_HANDOFF_PATH = "Core/SESSION_HANDOFF.md"
FRESHNESS_PATH = "Core/FRESHNESS.md"

STATE_FILE_PATHS = {
    "active_context": ACTIVE_CONTEXT_PATH,
    "session_handoff": SESSION_HANDOFF_PATH,
    "freshness": FRESHNESS_PATH,
}

TRACKED_FRESHNESS_FILES = [
    "Core/USER.md",
    "Core/SOUL.md",
    "Core/COMPANY-SOUL.md",
    ACTIVE_CONTEXT_PATH,
    SESSION_HANDOFF_PATH,
    "Archive/MEMORY.md",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _json_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    return json.dumps("" if value is None else str(value))


def _frontmatter_text(metadata: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in metadata.items():
        if isinstance(value, list):
            rendered = ", ".join(_json_scalar(item) for item in value)
            lines.append(f"{key}: [{rendered}]")
        else:
            lines.append(f"{key}: {_json_scalar(value)}")
    lines.append("---")
    return "\n".join(lines)


def _parse_listish(value: str) -> list[str]:
    text = (value or "").strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    return [
        item.strip().strip("\"'")
        for item in text.split(",")
        if item.strip()
    ]


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    metadata: dict[str, Any] = {}
    for idx in range(1, len(lines)):
        line = lines[idx]
        if line.strip() == "---":
            body = "\n".join(lines[idx + 1:]).lstrip()
            return metadata, body
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        raw = value.strip()
        if raw.startswith("[") and raw.endswith("]"):
            metadata[key] = _parse_listish(raw)
            continue
        if raw.lower() in {"true", "false"}:
            metadata[key] = raw.lower() == "true"
            continue
        try:
            metadata[key] = json.loads(raw)
            continue
        except Exception:
            metadata[key] = raw.strip("\"'")
    return {}, text


def read_markdown(vault: Path, relative_path: str) -> tuple[dict[str, Any], str, Path]:
    full_path = (vault / relative_path).resolve()
    if not str(full_path).startswith(str(vault.resolve())):
        raise PermissionError("Path traversal not allowed")
    if not full_path.exists():
        return {}, "", full_path
    text = full_path.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(text)
    return metadata, body, full_path


def write_markdown(vault: Path, relative_path: str, metadata: dict[str, Any], body: str) -> Path:
    full_path = (vault / relative_path).resolve()
    if not str(full_path).startswith(str(vault.resolve())):
        raise PermissionError("Path traversal not allowed")
    full_path.parent.mkdir(parents=True, exist_ok=True)
    text = _frontmatter_text(metadata).rstrip() + "\n\n" + body.rstrip() + "\n"
    full_path.write_text(text, encoding="utf-8")
    return full_path


def _render_bullets(items: list[str], empty_label: str) -> str:
    clean = [item.strip() for item in items if item and item.strip()]
    if not clean:
        return f"- {empty_label}"
    return "\n".join(f"- {item}" for item in clean)


def _split_sections(body: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", body, re.MULTILINE))
    if not matches:
        return sections
    for idx, match in enumerate(matches):
        title = match.group(1).strip().lower()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        sections[title] = body[start:end].strip()
    return sections


def _extract_bullets(section: str) -> list[str]:
    return [
        line[2:].strip()
        for line in section.splitlines()
        if line.strip().startswith("- ")
    ]


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def ensure_state_files(vault: Path) -> list[Path]:
    created: list[Path] = []
    now = utc_now_iso()
    templates = {
        ACTIVE_CONTEXT_PATH: (
            {
                "type": "state",
                "state_id": "active-context",
                "status": "active",
                "last_verified": now,
                "review_after_days": 3,
                "updated_by": "command-center",
                "active_project": "",
                "active_mission": "",
            },
            (
                "# Active Context\n\n"
                "## Mission\n"
                "Set the current mission for the session or operating window.\n\n"
                "## Current Summary\n"
                "Capture the current state in a few tight sentences.\n\n"
                "## Current Priorities\n"
                "- Add the highest-leverage priorities here.\n\n"
                "## Constraints\n"
                "- Add constraints, guardrails, or non-negotiables here.\n\n"
                "## Open Questions\n"
                "- Add unresolved questions here.\n\n"
                "## Next Actions\n"
                "- Add the next concrete actions here.\n\n"
                "## Relevant Files\n"
                "- Add paths or systems that matter right now.\n"
            ),
        ),
        SESSION_HANDOFF_PATH: (
            {
                "type": "state",
                "state_id": "session-handoff",
                "status": "active",
                "last_verified": now,
                "review_after_days": 2,
                "updated_by": "command-center",
            },
            (
                "# Session Handoff\n\n"
                "## Latest Summary\n"
                "Write the latest durable handoff summary here.\n\n"
                "## Next Actions\n"
                "- Add the next actions here.\n\n"
                "## Changed Files\n"
                "- Add changed files or systems here.\n\n"
                "## Open Questions\n"
                "- Add unresolved questions here.\n\n"
                "## Risks\n"
                "- Add live risks or watch items here.\n"
            ),
        ),
        FRESHNESS_PATH: (
            {
                "type": "state",
                "state_id": "freshness-report",
                "status": "active",
                "last_verified": now,
                "review_after_days": 1,
                "updated_by": "command-center",
            },
            (
                "# Freshness Report\n\n"
                "Run `freshness_report()` to regenerate this file.\n"
            ),
        ),
    }

    for relative_path, (metadata, body) in templates.items():
        full_path = vault / relative_path
        if full_path.exists():
            continue
        created.append(write_markdown(vault, relative_path, metadata, body))
    return created


def read_working_set(vault: Path) -> dict[str, Any]:
    ensure_state_files(vault)
    metadata, body, path = read_markdown(vault, ACTIVE_CONTEXT_PATH)
    sections = _split_sections(body)
    return {
        "path": path,
        "metadata": metadata,
        "mission": sections.get("mission", "").strip(),
        "summary": sections.get("current summary", "").strip(),
        "priorities": _extract_bullets(sections.get("current priorities", "")),
        "constraints": _extract_bullets(sections.get("constraints", "")),
        "open_questions": _extract_bullets(sections.get("open questions", "")),
        "next_actions": _extract_bullets(sections.get("next actions", "")),
        "files": _extract_bullets(sections.get("relevant files", "")),
        "body": body,
    }


def update_working_set(
    vault: Path,
    *,
    project: str = "",
    mission: str = "",
    summary: str = "",
    priorities: list[str] | None = None,
    constraints: list[str] | None = None,
    open_questions: list[str] | None = None,
    next_actions: list[str] | None = None,
    files: list[str] | None = None,
    source: str = "agent",
) -> Path:
    current = read_working_set(vault)
    metadata = dict(current["metadata"])
    metadata.update(
        {
            "type": "state",
            "state_id": "active-context",
            "status": "active",
            "last_verified": utc_now_iso(),
            "review_after_days": int(metadata.get("review_after_days", 3) or 3),
            "updated_by": source,
            "active_project": project or metadata.get("active_project", ""),
            "active_mission": mission or metadata.get("active_mission", ""),
        }
    )

    body = (
        "# Active Context\n\n"
        "## Mission\n"
        f"{(mission or current['mission'] or 'No mission set.').strip()}\n\n"
        "## Current Summary\n"
        f"{(summary or current['summary'] or 'No summary set.').strip()}\n\n"
        "## Current Priorities\n"
        f"{_render_bullets(priorities if priorities is not None else current['priorities'], 'No priorities set.')}\n\n"
        "## Constraints\n"
        f"{_render_bullets(constraints if constraints is not None else current['constraints'], 'No constraints set.')}\n\n"
        "## Open Questions\n"
        f"{_render_bullets(open_questions if open_questions is not None else current['open_questions'], 'No open questions.')}\n\n"
        "## Next Actions\n"
        f"{_render_bullets(next_actions if next_actions is not None else current['next_actions'], 'No next actions set.')}\n\n"
        "## Relevant Files\n"
        f"{_render_bullets(files if files is not None else current['files'], 'No files listed.')}\n"
    )
    return write_markdown(vault, ACTIVE_CONTEXT_PATH, metadata, body)


def read_handoff(vault: Path) -> dict[str, Any]:
    ensure_state_files(vault)
    metadata, body, path = read_markdown(vault, SESSION_HANDOFF_PATH)
    sections = _split_sections(body)
    return {
        "path": path,
        "metadata": metadata,
        "summary": sections.get("latest summary", "").strip(),
        "next_actions": _extract_bullets(sections.get("next actions", "")),
        "changed_files": _extract_bullets(sections.get("changed files", "")),
        "open_questions": _extract_bullets(sections.get("open questions", "")),
        "risks": _extract_bullets(sections.get("risks", "")),
        "body": body,
    }


def record_handoff(
    vault: Path,
    *,
    summary: str,
    next_actions: list[str] | None = None,
    changed_files: list[str] | None = None,
    open_questions: list[str] | None = None,
    risks: list[str] | None = None,
    source: str = "agent",
) -> Path:
    current = read_handoff(vault)
    metadata = dict(current["metadata"])
    metadata.update(
        {
            "type": "state",
            "state_id": "session-handoff",
            "status": "active",
            "last_verified": utc_now_iso(),
            "review_after_days": int(metadata.get("review_after_days", 2) or 2),
            "updated_by": source,
        }
    )
    body = (
        "# Session Handoff\n\n"
        "## Latest Summary\n"
        f"{summary.strip()}\n\n"
        "## Next Actions\n"
        f"{_render_bullets(next_actions or current['next_actions'], 'No next actions set.')}\n\n"
        "## Changed Files\n"
        f"{_render_bullets(changed_files or current['changed_files'], 'No changed files recorded.')}\n\n"
        "## Open Questions\n"
        f"{_render_bullets(open_questions or current['open_questions'], 'No open questions.')}\n\n"
        "## Risks\n"
        f"{_render_bullets(risks or current['risks'], 'No active risks recorded.')}\n"
    )
    return write_markdown(vault, SESSION_HANDOFF_PATH, metadata, body)


def verify_vault_file(
    vault: Path,
    *,
    relative_path: str,
    status: str = "active",
    note: str = "",
    review_after_days: int | None = None,
    source: str = "agent",
) -> Path:
    metadata, body, full_path = read_markdown(vault, relative_path)
    if not full_path.exists():
        raise FileNotFoundError(f"Not found: {relative_path}")
    metadata = dict(metadata)
    metadata["last_verified"] = utc_now_iso()
    metadata["status"] = status.strip() or metadata.get("status", "active")
    metadata["verified_by"] = source
    if note.strip():
        metadata["verified_note"] = note.strip()
    if review_after_days is not None:
        metadata["review_after_days"] = int(review_after_days)
    elif "review_after_days" not in metadata:
        metadata["review_after_days"] = 7
    return write_markdown(vault, relative_path, metadata, body or full_path.read_text(encoding="utf-8"))


def refresh_freshness_report(
    vault: Path,
    *,
    stale_days: int = 7,
    write: bool = True,
) -> dict[str, Any]:
    ensure_state_files(vault)
    now = datetime.now(timezone.utc)
    entries: list[dict[str, Any]] = []

    for relative_path in TRACKED_FRESHNESS_FILES:
        metadata, _body, full_path = read_markdown(vault, relative_path)
        if not full_path.exists():
            entries.append(
                {
                    "path": relative_path,
                    "freshness": "missing",
                    "status": "missing",
                    "last_verified": "",
                    "review_after_days": "",
                    "age_days": "",
                    "notes": "File missing",
                }
            )
            continue

        last_verified = str(metadata.get("last_verified", "")).strip()
        review_after = int(metadata.get("review_after_days", stale_days) or stale_days)
        note_parts: list[str] = []
        dt = _parse_iso(last_verified)

        if dt is None:
            dt = datetime.fromtimestamp(full_path.stat().st_mtime, tz=timezone.utc)
            last_verified = dt.replace(microsecond=0).isoformat()
            note_parts.append("using file mtime")

        age_days = round((now - dt).total_seconds() / 86400, 1)
        freshness = "stale" if age_days > review_after else "fresh"
        status = str(metadata.get("status", "active")).strip() or "active"
        if "review_after_days" not in metadata:
            note_parts.append("review_after_days defaulted")

        entries.append(
            {
                "path": relative_path,
                "freshness": freshness,
                "status": status,
                "last_verified": last_verified,
                "review_after_days": review_after,
                "age_days": age_days,
                "notes": "; ".join(note_parts) or "ok",
            }
        )

    counts = {
        "fresh": sum(1 for item in entries if item["freshness"] == "fresh"),
        "stale": sum(1 for item in entries if item["freshness"] == "stale"),
        "missing": sum(1 for item in entries if item["freshness"] == "missing"),
    }

    table_lines = [
        "| File | Freshness | Status | Last Verified | Review After (days) | Age (days) | Notes |",
        "|---|---|---|---|---:|---:|---|",
    ]
    for item in entries:
        table_lines.append(
            "| {path} | {freshness} | {status} | {last_verified} | {review_after_days} | {age_days} | {notes} |".format(
                **item
            )
        )

    markdown = (
        "# Freshness Report\n\n"
        f"- generated_at: {utc_now_iso()}\n"
        f"- fresh: {counts['fresh']}\n"
        f"- stale: {counts['stale']}\n"
        f"- missing: {counts['missing']}\n\n"
        "## Tracked Files\n\n"
        + "\n".join(table_lines)
        + "\n"
    )

    if write:
        metadata, _body, _path = read_markdown(vault, FRESHNESS_PATH)
        next_metadata = dict(metadata)
        next_metadata.update(
            {
                "type": "state",
                "state_id": "freshness-report",
                "status": "active",
                "last_verified": utc_now_iso(),
                "review_after_days": int(next_metadata.get("review_after_days", 1) or 1),
                "updated_by": "nightly-maintenance" if write else "command-center",
            }
        )
        write_markdown(vault, FRESHNESS_PATH, next_metadata, markdown)

    return {"entries": entries, "counts": counts, "markdown": markdown}
