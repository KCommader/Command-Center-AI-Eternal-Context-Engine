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
  summary="Auth service refactored to use short-lived tokens. All tests passing.",
  next_actions=["Deploy to staging", "Monitor token refresh rate"],
  changed_files=["src/auth/token_service.py", "tests/test_auth.py"],
  risks=["Redis session store not yet load-tested under high concurrency"]
)
```
