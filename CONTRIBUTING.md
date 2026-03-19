# Contributing to Command Center AI

Command Center solves a problem that affects every serious AI user — context loss from provider compaction. Contributions that make it better, more universal, or easier to use are genuinely welcome.

## What's Needed

### High impact
- **Native frontend** — Obsidian is the current interface but it's a third-party tool. A native web UI (or desktop app) that shows the knowledge graph, manages vault files, displays memory tiers, and gives full visibility into session state would be a massive step forward. Graph-like, local-first, no cloud.
- **Migration parsers** — `migration/parsers/` has OpenAI and Claude. Gemini, Grok/xAI, and a generic JSON format are missing. Each parser is ~100 lines.
- **AI runtime adapters** — `engine/skill_adapter.py` has Claude, Gemini, Codex, Custom AI. If your AI tool has a skill/context format, add a subclass.
- **MCP setup UX** — the initial connection is the hardest step. A setup wizard, a `doctor --fix` command, or better error messages would help a lot of people.

### Medium impact
- **Obsidian theme** — `vault/.obsidian/snippets/command-center.css`. Improvements to callout types, colors, or Dataview table layouts.
- **Templates** — `vault/Templates/` has two note templates. More domain-specific templates (research notes, decision logs, project specs) would be useful.
- **Bootstrap improvements** — `engine/mcp_server.py` handles `bootstrap_agent`. Better skill resolution, smarter recovery packets.

### Documentation
If something confused you during setup, a PR fixing it helps everyone who comes after you. The MCP troubleshooting section especially benefits from real-world cases.

### Anything else
The list above is a starting point, not a boundary. If you've built something that makes AI memory more permanent, more portable, or more reliable — or if you've solved a problem we haven't thought of yet — open an issue and show it.

## How to Submit

1. Fork the repo
2. Make your change on a branch
3. Test locally (`python engine/omniscience.py doctor` should pass)
4. Open a PR with a clear description of what it does and why

No formal review process yet — if it works, doesn't break existing behavior, and solves a real problem, it goes in.

## Principles

- **Keep it lean** — Command Center is intentionally simple. Resist adding complexity that only helps edge cases.
- **Markdown is the source of truth** — don't add features that require a database or cloud service to function.
- **Portable first** — everything should run from a folder that can be copied to a USB drive.
- **No lock-in** — the vault is plain files. Any feature that ties users to a specific platform is wrong direction.

## Questions

Open an issue. No Discord, no Slack — issues are the right place to discuss things publicly so the answers help everyone.
