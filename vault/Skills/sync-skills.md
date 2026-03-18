---
type: skill
status: active
category: skills
trigger: sync_skills
description: Sync vault/Skills/ to all connected AI runtimes so every AI has the same skill set
source: Command Center MCP
targets: [claude, codex, openclaw, gemini, any-ai]
---

# sync_skills

Pushes the canonical skill set from `vault/Skills/` to every AI runtime in
that runtime's native format. After syncing, Claude Code, Gemini CLI, Codex,
and OpenClaw all have identical skills.

## How it works

```
vault/Skills/   ← the one source of truth
      │
      ├─ Claude Code  → ~/.claude/skills/*.md
      ├─ Gemini CLI   → ~/.gemini/skills/*.md
      ├─ Codex / GPT  → ~/.codex/skills/*.md
      └─ OpenClaw     → {workspace}/skills/{name}/SKILL.md
```

Each adapter reads the vault skill and reformats it for its runtime.
Files are only written when content changes (safe to run repeatedly).

## Usage via MCP

```text
sync_skills()                                    # sync all runtimes
sync_skills(runtimes=["claude", "gemini"])       # specific runtimes only
sync_skills(dry_run=true)                        # preview, no writes
sync_skills(reverse=true)                        # import FROM runtimes → vault
```

## Usage via CLI

```bash
python -m engine sync-skills                     # all runtimes
python -m engine sync-skills --runtime claude    # one runtime
python -m engine sync-skills --dry-run           # preview
python -m engine sync-skills --list              # list all vault skills
python -m engine sync-skills --reverse           # promote runtime skills to vault
```

## Rules

- Vault always wins on conflicts — reverse mode never overwrites existing vault skills
- Meta skills (MCP tool descriptors) are not synced to runtimes — they describe tools, not prompts
- Skills with a `targets` list only sync to listed runtimes
- Skills with no `targets` list sync to all runtimes

## When to call

- After adding or editing any skill in `vault/Skills/`
- During `bootstrap_agent` if the runtime might be stale
- Any time an AI says "I don't have that skill"
