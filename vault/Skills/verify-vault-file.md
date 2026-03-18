---
type: skill
status: active
category: state
trigger: verify_vault_file
description: Mark a vault file as freshly verified so Command Center can detect stale operating context
source: Command Center MCP
targets: [claude, codex, custom-ai, custom-ai, any-ai]
---

# verify_vault_file

Updates a vault file's freshness metadata in place.

Use it when you confirm a file is still current and want stale-state detection to stay accurate.

## Usage
```text
verify_vault_file(path="Core/COMPANY-SOUL.md", status="active", note="Reviewed after strategy reset")
verify_vault_file(path="Core/ACTIVE_CONTEXT.md", review_after_days=3)
```
