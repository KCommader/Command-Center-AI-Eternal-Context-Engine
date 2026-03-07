"""
ChatGPT Export Parser

Handles OpenAI's export format:
  export_folder/
    conversations-000.json   (array of 100 conversations)
    conversations-001.json
    ...
    conversations-NNN.json
    <uuid>/                  (one folder per conversation with attachments)
    <uuid-hash>-filename.ext (code artifacts, images, etc.)
    export_manifest.json
    user.json
    user_settings.json

Each conversation has:
  - title, create_time, update_time
  - mapping: dict of message nodes
    - message.author.role: "user" | "assistant" | "system" | "tool"
    - message.content.parts: list of text strings
    - message.create_time: float timestamp
"""
from __future__ import annotations

import json
import os
import datetime
import re
from pathlib import Path

from migration.base import BaseParser, Conversation, ExportSummary


def _ts_to_date(ts) -> str:
    if not ts:
        return "Unknown"
    try:
        return datetime.datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d")
    except Exception:
        return "Unknown"


def _extract_messages(mapping: dict) -> list[dict]:
    """Return list of {role, text, ts} sorted by timestamp."""
    msgs = []
    for node in mapping.values():
        msg = node.get("message")
        if not msg or not msg.get("content"):
            continue
        role = msg.get("author", {}).get("role", "")
        if role not in ("user", "assistant"):
            continue
        parts = msg.get("content", {}).get("parts", [])
        text = " ".join(str(p) for p in parts if isinstance(p, str)).strip()
        if not text:
            continue
        ts = float(msg.get("create_time") or 0)
        msgs.append({"role": role, "text": text, "ts": ts})
    msgs.sort(key=lambda x: x["ts"])
    return msgs


def _first_of_role(msgs: list[dict], role: str, max_len: int = 500) -> str:
    for m in msgs:
        if m["role"] == role:
            return m["text"][:max_len]
    return ""


def _scan_artifacts(export_path: Path) -> list[dict]:
    """
    Find code/document artifacts in the export.
    OpenAI names them: <hash>-<original_filename>.<ext>
    Also checks UUID-named subdirectories.
    """
    artifacts = []
    code_exts = {".py", ".js", ".ts", ".cs", ".go", ".rs", ".java",
                 ".html", ".css", ".json", ".yaml", ".yml", ".md",
                 ".txt", ".sh", ".sql", ".r", ".cpp", ".c", ".h"}

    for item in export_path.iterdir():
        if item.is_file() and item.suffix.lower() in code_exts:
            # Skip the standard export files
            if item.name in {"export_manifest.json", "user.json",
                              "user_settings.json", "message_feedback.json"}:
                continue
            # Skip conversations-NNN.json files
            if re.match(r"conversations-\d+\.json", item.name):
                continue
            try:
                content = item.read_text(encoding="utf-8", errors="replace")
                artifacts.append({
                    "name": item.name,
                    "path": str(item),
                    "ext": item.suffix.lower(),
                    "size": len(content),
                    "content": content,
                })
            except Exception:
                pass

        elif item.is_dir() and _looks_like_uuid(item.name):
            for sub in item.iterdir():
                if sub.is_file() and sub.suffix.lower() in code_exts:
                    try:
                        content = sub.read_text(encoding="utf-8", errors="replace")
                        artifacts.append({
                            "name": sub.name,
                            "path": str(sub),
                            "ext": sub.suffix.lower(),
                            "size": len(content),
                            "content": content,
                        })
                    except Exception:
                        pass

    return artifacts


def _looks_like_uuid(name: str) -> bool:
    return bool(re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        name, re.IGNORECASE
    ))


class ChatGPTParser(BaseParser):
    PROVIDER_NAME = "chatgpt"

    @staticmethod
    def detect(export_path: str) -> str | None:
        p = Path(export_path)
        if not p.is_dir():
            return None
        files = list(p.iterdir())
        has_convos = any(
            re.match(r"conversations-\d+\.json", f.name)
            for f in files if f.is_file()
        )
        has_manifest = (p / "export_manifest.json").exists()
        if has_convos or has_manifest:
            return "chatgpt"
        return None

    def parse(self) -> ExportSummary:
        export_path = Path(self.export_path)

        # Load all conversations-NNN.json files
        raw_convos = []
        convo_files = sorted(
            f for f in export_path.iterdir()
            if f.is_file() and re.match(r"conversations-\d+\.json", f.name)
        )
        for fpath in convo_files:
            with open(fpath, encoding="utf-8") as f:
                raw_convos.extend(json.load(f))

        # Normalize
        conversations = []
        for raw in raw_convos:
            mapping = raw.get("mapping", {})
            msgs = _extract_messages(mapping)
            ts = float(raw.get("create_time") or 0)
            conv = Conversation(
                id=raw.get("id", raw.get("conversation_id", "")),
                title=raw.get("title", "Untitled"),
                date=_ts_to_date(ts),
                timestamp=ts,
                user_msg=_first_of_role(msgs, "user"),
                asst_msg=_first_of_role(msgs, "assistant"),
                model=raw.get("default_model_slug", ""),
                extra={
                    "update_time": raw.get("update_time"),
                    "is_archived": raw.get("is_archived", False),
                    "gizmo_id": raw.get("gizmo_id"),
                },
            )
            conversations.append(conv)

        conversations.sort(key=lambda c: c.timestamp)

        # Code artifacts
        artifacts = _scan_artifacts(export_path)

        # Date range
        dates = [c.date for c in conversations if c.date != "Unknown"]
        date_range = (dates[0], dates[-1]) if dates else ("Unknown", "Unknown")

        return ExportSummary(
            provider=self.PROVIDER_NAME,
            total=len(conversations),
            date_range=date_range,
            conversations=conversations,
            artifacts=artifacts,
            raw_stats={
                "files_loaded": len(convo_files),
                "artifacts_found": len(artifacts),
            },
        )
