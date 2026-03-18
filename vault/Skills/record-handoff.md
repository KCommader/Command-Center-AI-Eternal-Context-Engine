---
type: skill
status: active
category: state
trigger: record_handoff
description: Write the latest durable handoff summary so a new session can resume cleanly
source: Command Center MCP
targets: [claude, codex, custom-ai, custom-ai, any-ai]
---

# record_handoff

Writes the latest session handoff to `Core/SESSION_HANDOFF.md`.

Use it before ending a session or after finishing a meaningful chunk of work.

## Usage
```text
record_handoff(
  summary="prediction market bot is live on oracle-lag only and idle by design until a valid edge appears.",
  next_actions=["Check fills after the next valid signal"],
  changed_files=["Trading Bots/trading_project/trading_bot.py"],
  risks=["No external sports odds provider configured yet"]
)
```
