---
type: skill
status: active
category: vault
trigger: read_vault_file
description: Read any Markdown file from the vault
source: Command Center MCP
---

# read_vault_file

Reads the full content of any file in the vault. Useful for loading your identity context, checking specific notes, or reviewing memory entries directly.

## Usage
```
read_vault_file("Core/USER.md")
read_vault_file("Core/SOUL.md")
read_vault_file("Archive/MEMORY.md")
read_vault_file("Knowledge/my-trading-strategy.md")
```

## Notes
- Path is relative to the vault root
- Returns raw Markdown content
- Use `list_vault` first to discover available files
