---
type: skill
status: active
category: skills
trigger: read_skill
description: Load the full text of a registered skill by canonical id or name
source: Command Center MCP
targets: [claude, codex, custom-ai, custom-ai]
---

# read_skill

Reads one skill from the registry. Use this after `list_skills` or `resolve_skills` to load the exact skill instructions into the current session.

## Usage
```text
read_skill(skill_id="claude:elite-landing-page")
read_skill(name="elite-landing-page", source="claude")
```

## Notes
- `skill_id` is the most reliable lookup method
- The response includes source, path, category, and the full skill body
- This is the bridge that lets non-Claude runtimes consume Claude-style skill files
