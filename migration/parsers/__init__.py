from .chatgpt import ChatGPTParser
from .claude_export import ClaudeParser
from .gemini import GeminiParser

PARSERS = {
    "chatgpt": ChatGPTParser,
    "claude": ClaudeParser,
    "gemini": GeminiParser,
}


def auto_detect(export_path: str):
    """Try each parser's detect() — return the right parser or None."""
    for name, cls in PARSERS.items():
        if cls.detect(export_path):
            return cls(export_path)
    return None
