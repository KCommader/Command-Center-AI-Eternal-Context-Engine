---
type: skill
status: active
category: state
trigger: update_working_set
description: Update the canonical active working set so every agent reloads the same mission, priorities, and next actions
source: Command Center MCP
targets: [claude, codex, custom-ai, custom-ai, any-ai]
---

# update_working_set

Writes the active working set to `Core/ACTIVE_CONTEXT.md`.

Use it after:
- major strategy changes
- production incidents
- priority shifts
- any point where a future session must resume from the same state

## Usage
```text
update_working_set(
  project="AlphaEngine",
  mission="Make the prediction market bot trade only high-edge setups",
  summary="Oracle-lag only, BTC/ETH only, awaiting more live samples",
  priorities=["Validate fills", "Monitor overnight opportunities"],
  next_actions=["Review fresh trades in the morning"]
)
```
