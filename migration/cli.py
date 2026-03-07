#!/usr/bin/env python3
"""
Command Center AI — Migration CLI

Usage:
    python -m migration <provider> <export_path> [--vault <vault_path>] [--out <filename>]

Provider options:
    chatgpt   OpenAI export folder (conversations-000.json, ...)
    claude    Claude.ai export (conversations.json)
    gemini    Google Takeout / Gemini Apps Activity
    auto      Auto-detect provider from export contents

Examples:
    python -m migration chatgpt ~/Downloads/openai-export --vault ./vault
    python -m migration claude ~/Downloads/claude-export.json --vault ./vault
    python -m migration auto ~/Downloads/my-ai-export --vault ./vault

Output:
    vault/Migration/<PROVIDER>_<DATE>_ANALYSIS.md
    (gitignored — your data stays local)
"""
import argparse
import sys
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Migrate AI provider export into Command Center vault",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "provider",
        choices=["chatgpt", "claude", "gemini", "auto"],
        help="AI provider export format",
    )
    parser.add_argument(
        "export_path",
        help="Path to the export folder or file",
    )
    parser.add_argument(
        "--vault",
        default=None,
        help="Path to vault folder (default: ./vault or OMNI_VAULT_PATH env var)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output filename (default: <PROVIDER>_<DATE>_ANALYSIS.md)",
    )
    parser.add_argument(
        "--categories",
        default=None,
        help="Path to custom categories JSON file (optional)",
    )

    args = parser.parse_args()

    # Resolve vault path
    vault_path = (
        args.vault
        or os.environ.get("OMNI_VAULT_PATH")
        or "./vault"
    )
    vault_path = Path(vault_path).expanduser().resolve()

    if not vault_path.exists():
        print(f"ERROR: Vault not found: {vault_path}", file=sys.stderr)
        print("Pass --vault /path/to/vault or set OMNI_VAULT_PATH", file=sys.stderr)
        sys.exit(1)

    export_path = Path(args.export_path).expanduser().resolve()
    if not export_path.exists():
        print(f"ERROR: Export path not found: {export_path}", file=sys.stderr)
        sys.exit(1)

    # Import here so module is usable even if optional deps missing
    from migration.classifier import Classifier, DEFAULT_CATEGORIES
    from migration.writer import write_analysis

    # Load custom categories if provided
    categories = None
    if args.categories:
        import json
        with open(args.categories) as f:
            categories = json.load(f)
        print(f"Using custom categories: {args.categories}")

    classifier = Classifier(categories)

    # Load parser
    if args.provider == "auto":
        from migration.parsers import auto_detect
        p = auto_detect(str(export_path))
        if not p:
            print("ERROR: Could not auto-detect provider. Specify explicitly.", file=sys.stderr)
            print("Supported: chatgpt, claude, gemini", file=sys.stderr)
            sys.exit(1)
        print(f"Auto-detected provider: {p.PROVIDER_NAME}")
    else:
        from migration.parsers import PARSERS
        parser_cls = PARSERS[args.provider]
        p = parser_cls(str(export_path))

    # Parse
    print(f"Parsing {p.PROVIDER_NAME} export from: {export_path}")
    summary = p.parse()
    print(f"  Loaded {summary.total} conversations ({summary.date_range[0]} → {summary.date_range[1]})")
    if summary.artifacts:
        print(f"  Found {len(summary.artifacts)} code artifacts")

    # Classify
    print("Classifying conversations...")
    classifier.classify_batch(summary.conversations)

    from collections import Counter
    cat_counts = Counter(c.category for c in summary.conversations)
    for cat, count in cat_counts.most_common():
        print(f"  {count:4d}  {cat}")

    # Write
    print(f"\nWriting analysis to vault/Migration/...")
    output = write_analysis(summary, vault_path, args.out)
    size_kb = output.stat().st_size // 1024
    print(f"Done: {output}")
    print(f"Size: {size_kb} KB | {len(summary.conversations)} conversations")


if __name__ == "__main__":
    main()
