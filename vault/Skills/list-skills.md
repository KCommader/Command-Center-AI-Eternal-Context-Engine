---
type: skill
status: active
category: skills
trigger: list_skills
description: Browse the cross-AI Commander skill catalog across vault and external skill libraries
source: Command Center MCP
targets: [claude, codex, custom-ai, custom-ai]
---

# list_skills

Lists the portable Commander skill catalog. This includes vault-native skills and external prompt-skill libraries such as `~/.claude/skills`.

## Usage
```text
list_skills()
list_skills(query="flutter")
list_skills(source="claude", target="frontend", limit=10)
```

## Notes
- Use this when an agent needs to know what specialized playbooks exist
- Returns canonical `skill_id` values for follow-up `read_skill()` calls
- Filters are lightweight and deterministic so every client gets the same catalog view
