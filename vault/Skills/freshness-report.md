---
type: skill
status: active
category: state
trigger: freshness_report
description: Generate the freshness report for the key operating files and catch stale context before it drifts
source: Command Center MCP
targets: [claude, codex, custom-ai, custom-ai, any-ai]
---

# freshness_report

Regenerates `Core/FRESHNESS.md` and reports which tracked files are fresh, stale, or missing.

## Usage
```text
freshness_report()
freshness_report(stale_days=3, write=true)
```
