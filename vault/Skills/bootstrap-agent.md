---
type: skill
status: active
category: skills
trigger: bootstrap_agent
description: Generate a standard startup packet so any AI runtime can load the same context and skills
source: Command Center MCP
targets: [claude, codex, custom-ai, custom-ai, any-ai]
---

# bootstrap_agent

Returns the standard startup or recovery flow for an agent: which resources to read, what memory search to run first, which operating-state files to trust, and which skills to load for the active task.

## Usage
```text
bootstrap_agent(agent="Codex")
bootstrap_agent(agent="Codex", reason="compact_recovery")
bootstrap_agent(agent="Custom AI", task="handle incoming messages", target="assistant")
bootstrap_agent(agent="Claude", task="design an ios app", target="flutter")
```

## Notes
- This is the closest thing to true cross-AI inheritance
- It normalizes session startup across different vendors and runtimes
- It now includes `ACTIVE_CONTEXT`, `SESSION_HANDOFF`, and `FRESHNESS` in the boot order
- Pair it with `store()` so the system gets stronger after every session
