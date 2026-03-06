---
type: skill
status: active
category: vault
trigger: list_vault
description: Browse all available notes and files in the vault
source: Command Center MCP
---

# list_vault

Returns a list of all Markdown files in the vault, organized by folder. Use this to discover what knowledge and memory is available before searching or reading.

## Usage
```
list_vault()
list_vault("Knowledge/")
list_vault("Archive/")
```

## Notes
- Returns file paths relative to vault root
- Filter by folder prefix to narrow scope
- Combine with `read_vault_file` to load specific content
- Combine with `search_memory` for targeted semantic retrieval
