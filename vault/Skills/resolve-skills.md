---
type: skill
status: active
category: skills
trigger: resolve_skills
description: Recommend the most relevant skills for a task, agent, or target stack
source: Command Center MCP
targets: [frontend, flutter, react, threejs, trading, agentic]
---

# resolve_skills

Ranks the most relevant skills for a task. This is the portable replacement for vendor-specific auto-skill triggers.

## Usage
```text
resolve_skills(task="build a premium 3d landing page")
resolve_skills(task="fix the websocket reconnect bug", agent="Codex", target="backend")
resolve_skills(task="ship an ios app", target="flutter", limit=5)
```

## Notes
- The resolver scores skill name, description, targets, and body text
- Use before planning when the runtime does not have native skill auto-selection
- Follow with `read_skill()` on the returned ids
