"""
Base parser interface.
Every provider parser (ChatGPT, Claude, Gemini...) inherits from this.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Conversation:
    """Normalized conversation from any provider."""
    id: str
    title: str
    date: str                   # YYYY-MM-DD
    timestamp: float            # unix epoch, for sorting
    user_msg: str               # first user message (up to 500 chars)
    asst_msg: str               # first assistant response (up to 500 chars)
    model: str = ""             # model used, if known
    category: str = ""          # filled by classifier
    extra: dict = field(default_factory=dict)  # provider-specific metadata


@dataclass
class ExportSummary:
    """What the parser found in the export."""
    provider: str
    total: int
    date_range: tuple[str, str]  # (earliest, latest)
    conversations: list[Conversation]
    artifacts: list[dict]        # code files, attachments, etc.
    raw_stats: dict = field(default_factory=dict)


class BaseParser(ABC):
    """
    Implement this for each AI provider export format.

    Usage:
        parser = ChatGPTParser("/path/to/export/folder")
        summary = parser.parse()
    """

    PROVIDER_NAME: str = "unknown"

    def __init__(self, export_path: str):
        self.export_path = export_path

    @abstractmethod
    def parse(self) -> ExportSummary:
        """
        Parse the export and return a normalized ExportSummary.
        Must handle all files in self.export_path.
        """
        ...

    @staticmethod
    def detect(export_path: str) -> Optional[str]:
        """
        Return provider name if this parser recognizes the export format,
        None otherwise. Used for auto-detection.
        """
        return None
