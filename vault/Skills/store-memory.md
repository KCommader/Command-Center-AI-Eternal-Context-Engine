---
type: skill
status: active
category: memory
trigger: store
description: Save facts, decisions, and context — auto-classified to the right memory tier
source: Command Center MCP
---

# store

Saves a piece of information to the vault. The Memory Classifier automatically determines which tier it belongs to — no manual routing needed.

## Usage
```
store("I prefer Python over Node for data pipelines")
store("remember this: vault password is stored in Bitwarden")
store("working on the exchange bot, currently debugging the order fill logic")
```

## Memory Tiers (auto-classified)
| Tier | TTL | Triggered by |
|------|-----|--------------|
| `long_term` | Never | "always", "never", "decided", "remember this", "permanent" |
| `short_term` | 30 days | "working on", "current task", "blocked", "this sprint" |
| `cache` | Nightly | Greetings, one-off questions, ephemeral context |

## Force keywords
Prepend any of these to guarantee long_term storage:
`"remember this"` · `"never forget"` · `"permanent"` · `"always"`
