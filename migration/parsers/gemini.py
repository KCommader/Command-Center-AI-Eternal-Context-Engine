"""
Gemini Export Parser

Google Takeout format for Gemini (gemini.google.com -> Google Takeout):
  Takeout/
    Gemini Apps Activity/
      Gemini Apps Activity.json
        {
          "conversations": [
            {
              "title": "...",
              "startTime": "2025-01-01T00:00:00Z",
              "messages": [
                {
                  "role": "user" | "model",
                  "text": "...",
                  "timestamp": "..."
                }
              ]
            }
          ]
        }

Note: Google Takeout format has varied across versions.
This parser handles the most common structure found in 2024-2025 exports.
If your export has a different structure, open a GitHub issue with a
sanitized sample and we'll add support.
"""
from __future__ import annotations

import json
import datetime
from pathlib import Path

from migration.base import BaseParser, Conversation, ExportSummary


def _parse_time(t: str) -> float:
    try:
        return datetime.datetime.fromisoformat(
            t.replace("Z", "+00:00")
        ).timestamp()
    except Exception:
        return 0.0


def _time_to_date(t: str) -> str:
    try:
        return datetime.datetime.fromisoformat(
            t.replace("Z", "+00:00")
        ).strftime("%Y-%m-%d")
    except Exception:
        return "Unknown"


class GeminiParser(BaseParser):
    PROVIDER_NAME = "gemini"

    @staticmethod
    def detect(export_path: str) -> str | None:
        p = Path(export_path)
        # Direct JSON file
        if p.is_file() and "gemini" in p.name.lower():
            return "gemini"
        # Google Takeout folder
        if p.is_dir():
            takeout = p / "Gemini Apps Activity" / "Gemini Apps Activity.json"
            if takeout.exists():
                return "gemini"
        return None

    def _find_export_file(self) -> Path | None:
        p = Path(self.export_path)
        if p.is_file():
            return p
        # Standard Google Takeout path
        takeout = p / "Gemini Apps Activity" / "Gemini Apps Activity.json"
        if takeout.exists():
            return takeout
        # Fallback: any JSON with "gemini" in name
        for f in p.rglob("*.json"):
            if "gemini" in f.name.lower():
                return f
        return None

    def parse(self) -> ExportSummary:
        export_file = self._find_export_file()
        if not export_file:
            return ExportSummary(
                provider=self.PROVIDER_NAME,
                total=0,
                date_range=("Unknown", "Unknown"),
                conversations=[],
                artifacts=[],
                raw_stats={"error": "No Gemini export file found"},
            )

        with open(export_file, encoding="utf-8") as f:
            data = json.load(f)

        raw_convos = data.get("conversations", [])
        if not raw_convos and isinstance(data, list):
            raw_convos = data

        conversations = []
        for item in raw_convos:
            messages = item.get("messages", [])
            user_msg = next(
                (m.get("text", "")[:500] for m in messages
                 if m.get("role") in ("user", "human")),
                ""
            )
            asst_msg = next(
                (m.get("text", "")[:500] for m in messages
                 if m.get("role") in ("model", "assistant")),
                ""
            )
            start = item.get("startTime", item.get("timestamp", ""))
            ts = _parse_time(start)
            conversations.append(Conversation(
                id=item.get("id", item.get("conversationId", "")),
                title=item.get("title", "Untitled"),
                date=_time_to_date(start),
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
            raw_stats={"source_file": str(export_file)},
        )
