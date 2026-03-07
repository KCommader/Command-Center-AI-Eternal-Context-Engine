"""
Claude Export Parser

Claude's export format (claude.ai -> Settings -> Export):
  export_folder/
    conversations.json   single JSON file, array of conversations
    Each conversation:
      {
        "uuid": "...",
        "name": "conversation title",
        "created_at": "2025-01-01T12:00:00.000Z",
        "updated_at": "...",
        "chat_messages": [
          {
            "uuid": "...",
            "text": "...",
            "sender": "human" | "assistant",
            "created_at": "...",
            "files": [...],
            "attachments": [...]
          }
        ]
      }
"""
from __future__ import annotations

import json
import datetime
from pathlib import Path

from migration.base import BaseParser, Conversation, ExportSummary


def _parse_iso(dt_str: str) -> float:
    try:
        return datetime.datetime.fromisoformat(
            dt_str.replace("Z", "+00:00")
        ).timestamp()
    except Exception:
        return 0.0


def _iso_to_date(dt_str: str) -> str:
    try:
        return datetime.datetime.fromisoformat(
            dt_str.replace("Z", "+00:00")
        ).strftime("%Y-%m-%d")
    except Exception:
        return "Unknown"


class ClaudeParser(BaseParser):
    PROVIDER_NAME = "claude"

    @staticmethod
    def detect(export_path: str) -> str | None:
        p = Path(export_path)
        if p.is_file() and p.name == "conversations.json":
            # Could be Claude or another provider — peek inside
            try:
                with open(p) as f:
                    data = json.load(f)
                if isinstance(data, list) and data and "chat_messages" in data[0]:
                    return "claude"
            except Exception:
                pass
        if p.is_dir():
            convos_file = p / "conversations.json"
            if convos_file.exists():
                try:
                    with open(convos_file) as f:
                        data = json.load(f)
                    if isinstance(data, list) and data and "chat_messages" in data[0]:
                        return "claude"
                except Exception:
                    pass
        return None

    def parse(self) -> ExportSummary:
        p = Path(self.export_path)
        convos_file = p / "conversations.json" if p.is_dir() else p

        with open(convos_file, encoding="utf-8") as f:
            raw = json.load(f)

        conversations = []
        for item in raw:
            messages = item.get("chat_messages", [])
            user_msg = next(
                (m.get("text", "")[:500] for m in messages if m.get("sender") == "human"),
                ""
            )
            asst_msg = next(
                (m.get("text", "")[:500] for m in messages if m.get("sender") == "assistant"),
                ""
            )
            created = item.get("created_at", "")
            ts = _parse_iso(created)
            conversations.append(Conversation(
                id=item.get("uuid", ""),
                title=item.get("name", "Untitled"),
                date=_iso_to_date(created),
                timestamp=ts,
                user_msg=user_msg,
                asst_msg=asst_msg,
            ))

        conversations.sort(key=lambda c: c.timestamp)
        dates = [c.date for c in conversations if c.date != "Unknown"]
        date_range = (dates[0], dates[-1]) if dates else ("Unknown", "Unknown")

        return ExportSummary(
            provider=self.PROVIDER_NAME,
            total=len(conversations),
            date_range=date_range,
            conversations=conversations,
            artifacts=[],
            raw_stats={"source_file": str(convos_file)},
        )
