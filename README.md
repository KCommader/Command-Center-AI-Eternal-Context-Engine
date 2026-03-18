<div align="center">

<img src="assets/logo.png" alt="Command Center AI" width="720" />

### Your AI Should Never Forget — Local, Private, Portable

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)](https://python.org)
[![MCP](https://img.shields.io/badge/MCP-stdio%20%2B%20HTTP-purple?style=flat-square)](https://modelcontextprotocol.io)
[![LanceDB](https://img.shields.io/badge/Vector%20DB-LanceDB-orange?style=flat-square)](https://lancedb.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Obsidian](https://img.shields.io/badge/Vault-Obsidian%20Native-7C3AED?style=flat-square&logo=obsidian)](https://obsidian.md)
[![Contributions Welcome](https://img.shields.io/badge/contributions-welcome-brightgreen?style=flat-square)](CONTRIBUTING.md)

</div>

---

## The Problem Everyone Hits

You're deep in a project with Claude, GPT, or Gemini. Two hours in, the conversation gets long. The provider **compacts**. Suddenly your AI "forgets" the architecture decision from an hour ago. It hallucinates a file path. It suggests something you explicitly ruled out. You spend the next 20 minutes re-explaining yourself.

This isn't a bug. It's how every LLM works. **Conversations have limits. Providers compact or truncate when they hit them. When they do, the AI loses its mind — and your project context goes with it.**

There are hundreds of threads on X about this exact experience. People watching months of project context get wiped mid-session. It's the #1 friction point for anyone doing serious work with AI.

**Command Center is the fix.**

---

## How It Solves It

Memory lives in **files on your machine**, not inside the conversation.

At the start of every session, the AI reads your vault — who you are, your active project, what was decided last session, what your preferences are. When the conversation compacts or you switch tools entirely, it doesn't matter. The memory was never in the conversation. It lives in Markdown files that nothing can delete.

```
Without Command Center:                With Command Center:
────────────────────────               ─────────────────────────────
Session 1 → context                    Session 1 → AI reads vault
    ↓ compaction                           ↓ work happens
    context gone                           ↓ AI writes decisions to vault
Session 2 → starts over                Session 2 → AI reads vault again
Session 3 → starts over                Session 3 → same, full context
```

**Works with**: Claude Desktop, Claude Code, Cursor, Zed, Gemini CLI, Codex, or any MCP-compatible AI.

> No cloud. No subscriptions. No lock-in. Your context lives on your machine — or on a USB drive.

---

## What It Looks Like

<div align="center">

<img src="assets/screenshots/home-dashboard.png" alt="Command Center Home Dashboard" width="100%" />

*The Obsidian dashboard — your vault's home page. Browse your identity files, memory tiers, knowledge base, and skills all from one place.*

</div>

<div align="center">

<img src="assets/screenshots/graph-view.png" alt="Knowledge Graph View" width="100%" />

*Graph view — every note, skill, and memory as a living constellation. Core files (cyan) anchor the identity layer. Archive (violet) holds long-term memory. Knowledge (green) holds your domain notes.*

</div>

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/KCommader/Command-Center-AI-Eternal-Context-Engine
cd Command-Center-AI

# 2. Setup (creates venv, installs deps, scaffolds vault)
bash setup.sh

# 3. Fill in your identity (this is what your AI will read every session)
#    Edit: vault/Core/USER.md       ← who you are
#    Edit: vault/Core/SOUL.md       ← how you want the AI to behave
#    Edit: vault/Core/COMPANY-SOUL.md ← your project/organization context

# 4. Start the engine
python engine/omniscience.py start

# 5. Connect your AI (see below)
```

Open `vault/` in [Obsidian](https://obsidian.md) to browse your memory visually.

---

## Connecting Your AI

### Option A — MCP stdio (Claude Code, Claude Desktop, Cursor, Zed)

MCP (Model Context Protocol) is an open standard for giving AI tools access to external systems. Command Center speaks MCP natively — your vault becomes a set of tools the AI can call automatically.

**Step 1: Make sure the engine is running first**
```bash
python engine/omniscience.py start
python engine/omniscience.py doctor  # verify everything is healthy
```

**Step 2: Add to your AI's config**

Claude Code (`~/.claude/settings.json`):
```json
{
  "mcpServers": {
    "command-center": {
      "command": "/absolute/path/to/Command-Center-AI/.venv/bin/python",
      "args": ["/absolute/path/to/Command-Center-AI/engine/mcp_server.py"],
      "env": {
        "OMNI_VAULT_PATH": "/absolute/path/to/Command-Center-AI/vault",
        "OMNI_ENGINE_URL": "http://127.0.0.1:8765"
      }
    }
  }
}
```

Claude Desktop (`~/.config/claude/claude_desktop_config.json` or `~/Library/Application Support/Claude/claude_desktop_config.json` on Mac):
```json
{
  "mcpServers": {
    "command-center": {
      "command": "/absolute/path/to/Command-Center-AI/.venv/bin/python",
      "args": ["/absolute/path/to/Command-Center-AI/engine/mcp_server.py"],
      "env": {
        "OMNI_VAULT_PATH": "/absolute/path/to/Command-Center-AI/vault",
        "OMNI_ENGINE_URL": "http://127.0.0.1:8765"
      }
    }
  }
}
```

> **Important**: Use the `.venv/bin/python` inside the repo, not system Python. Use absolute paths everywhere. Relative paths break silently.

**Step 3: Test the connection**

Open a new chat and ask your AI to call `bootstrap_agent`. It should respond with a startup packet from your vault. If it errors, check [MCP Troubleshooting](#mcp-troubleshooting) below.

**Tools the AI gets automatically:**

| Tool | What it does |
|------|-------------|
| `search_memory` | Semantic search across your entire vault |
| `store` | Save facts/decisions — engine auto-routes to the right memory tier |
| `read_vault_file` | Read any Markdown file from the vault |
| `list_vault` | Browse all available notes |
| `bootstrap_agent` | **Compaction recovery** — load full context after a reset (see below) |
| `list_skills` | Browse available AI skills |
| `read_skill` | Load a skill's instructions |
| `resolve_skills` | Get skill recommendations for a task |
| `update_working_set` | Update the active mission and priorities |
| `record_handoff` | Write a session checkpoint |
| `sync_skills` | Push vault skills to all connected AI runtimes |

### Option B — Network MCP (NAS / Multi-Machine)

Run one Command Center on a NAS or home server and connect every machine on your network to the same vault. One memory. Shared everywhere.

**On your server:**
```bash
OMNI_MCP_KEY=your_secret_token \
OMNI_VAULT_PATH=/path/to/vault \
python engine/mcp_server.py --transport http --port 8766
```

**On each client** (`~/.claude/settings.json`):
```json
{
  "mcpServers": {
    "command-center": {
      "url": "http://YOUR_SERVER_IP:8766/mcp",
      "headers": { "Authorization": "Bearer your_secret_token" }
    }
  }
}
```

### Option C — REST API (Scripts, bots, custom integrations)

```bash
# Semantic search
curl -X POST "http://127.0.0.1:8765/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "my architecture decisions", "k": 5}'

# Store a memory
curl -X POST "http://127.0.0.1:8765/capture" \
  -H "Content-Type: application/json" \
  -d '{"content": "Decided to use FastAPI over Flask for the main API"}'
```

---

## MCP Troubleshooting

MCP connection issues are almost always one of these:

**1. Wrong Python path**
The `command` must point to the Python inside the repo's virtual environment, not system Python.
```bash
# Find the right path
which python  # wrong — this is system python
ls /path/to/Command-Center-AI/.venv/bin/python  # this is correct
```

**2. Relative paths**
Every path in the MCP config must be absolute. `./vault` or `~/Command-Center-AI` will silently fail on some clients.

**3. Engine not running**
The MCP server talks to the engine on port 8765. If the engine isn't running, tools will fail.
```bash
python engine/omniscience.py status   # check
python engine/omniscience.py start    # start if needed
python engine/omniscience.py doctor   # full health check
```

**4. Config file location varies by AI**
- Claude Code: `~/.claude/settings.json`
- Claude Desktop (Linux): `~/.config/claude/claude_desktop_config.json`
- Claude Desktop (Mac): `~/Library/Application Support/Claude/claude_desktop_config.json`
- Cursor / Zed: check their respective MCP docs

**5. Restart the AI after config changes**
MCP servers are spawned at startup. Editing the config file requires a full restart of the AI tool, not just a new chat.

---

## Bootstrap — The Anti-Compaction Mechanism

This is the core feature. Here's exactly what it does and why it exists.

**The problem**: When a provider compacts a conversation, the AI loses all the context it accumulated during the session — your preferences, your active project, what was decided, what was built. It falls back to generic behavior.

**How bootstrap solves it**: `bootstrap_agent` is an MCP tool that generates a structured startup packet from your vault in one call. It returns:
- Your identity files (USER, SOUL, COMPANY-SOUL)
- Your active mission and current priorities (ACTIVE_CONTEXT)
- The latest session checkpoint (SESSION_HANDOFF)
- A freshness check on your core files
- Recommended skills for your current task

Any AI can call this at any time — session start, after compaction, when switching tools. The vault always has the current state. The AI is back to full context in seconds.

**How to use it:**

At session start — tell your AI:
```
Call bootstrap_agent to load my context before we start.
```

After compaction — the AI detects it lost context, calls:
```
bootstrap_agent(agent="Claude", reason="compact_recovery")
```

When switching AI tools — same call, different agent name. Same vault. Same context.

**For developers**: Add bootstrap to your AI's system prompt or CLAUDE.md as a startup instruction:
```
At the start of every session, call bootstrap_agent to load context from Command Center.
If the conversation compacts, call bootstrap_agent again to recover.
```

---

## Vault Structure

```
vault/
├── Core/                    ← Identity layer — fill these in once
│   ├── USER.md              ← Who you are: background, preferences, tech stack
│   ├── SOUL.md              ← AI behavior: tone, directives, what to always/never do
│   └── COMPANY-SOUL.md      ← Project/org context: mission, active work, stack
│
├── Archive/                 ← Memory tiers
│   ├── MEMORY.md            ← Long-term: preferences, decisions, permanent directives
│   └── short/               ← Short-term: active tasks, project state (30-day TTL)
│
├── Cache/                   ← Session noise — cleared nightly automatically
│
├── Knowledge/               ← Your notes, research, strategies (always searchable)
│
├── Skills/                  ← AI skill registry (available to all connected AIs)
│
└── Templates/               ← Note templates for consistent formatting
```

**Start here**: Fill in `Core/USER.md`, `Core/SOUL.md`, and `Core/COMPANY-SOUL.md`. Everything else populates automatically as you and your AI work.

---

## How Memory Works

The AI calls `store("content")`. Command Center does the rest — no manual classification.

| Tier | Location | Lifetime | What ends up here |
|------|----------|----------|-------------------|
| **long_term** | `Archive/MEMORY.md` | Forever | Preferences, decisions, directives ("always use Python", "decided on FastAPI") |
| **short_term** | `Archive/short/` | 30 days | Active tasks, project state, in-progress work |
| **cache** | `Cache/` | Nightly purge | Session greetings, one-off questions, ephemeral notes |

The classifier (`engine/memory_classifier.py`) uses content patterns to route automatically:
- `"remember this"`, `"never forget"`, `"from now on"` → long_term
- `"working on"`, `"current task"`, `"this sprint"` → short_term
- Greetings, quick questions, `"show me"` → cache
- When in doubt → short_term (better to keep than lose)

---

## Skills — Universal Across All AIs

Add a Markdown file to `vault/Skills/` and every connected AI can access it via `list_skills` and `read_skill`. Skills are prompt libraries — playbooks, best practices, domain knowledge — that any AI can load on demand.

Each AI runtime has its own native format for skills. Command Center syncs them automatically:

```bash
python engine/omniscience.py sync-skills         # push to all runtimes
python engine/omniscience.py sync-skills --runtime claude   # one runtime
python engine/omniscience.py sync-skills --dry-run          # preview
python engine/omniscience.py sync-skills --list             # see all skills
```

Runtimes: `claude` (`~/.claude/skills/`), `gemini` (`~/.gemini/skills/`), `codex` (`~/.codex/skills/`), `openclaw` (workspace).

---

## Migrating to a New Machine

```bash
# 1. Copy the entire Command-Center-AI folder to the new machine
# 2. On the new machine:
bash setup.sh
python engine/omniscience.py start
# Done. LanceDB rebuilds the vector index from Markdown in seconds.
```

Or put it on a USB drive. Runs anywhere Python runs.

---

## Migrating from Other AI Tools

Bring your ChatGPT or Claude history into the vault:

```bash
# ChatGPT export (Settings → Export data → conversations.json)
python scripts/migrate_openai.py --input ~/Downloads/conversations.json

# Claude export
python -m migration claude --input ~/Downloads/claude-export/
```

This extracts your decisions, projects, and preferences from conversation history and writes structured Markdown into `vault/Migration/` — ready for semantic search.

---

## Architecture

| Component | Role |
|-----------|------|
| `vault/` | Source of truth — plain Markdown, readable by humans and AIs alike |
| `engine/engine.py` | Watches vault, builds LanceDB index, serves search API on port 8765 |
| `engine/memory_classifier.py` | Auto-routes stored memories to the right tier — no LLM needed, ~1ms |
| `engine/mcp_server.py` | Exposes vault as MCP tools (stdio + HTTP transports) |
| `engine/skill_adapter.py` | Syncs vault skills to each AI runtime's native format |
| `engine/context_state.py` | Reads/writes ACTIVE_CONTEXT, SESSION_HANDOFF, FRESHNESS |
| `engine/omniscience.py` | CLI launcher: start/stop/status/doctor/logs/sync-skills |
| `engine/nightly_maintenance.py` | Nightly cache purge + short-term TTL + state bootstrap |
| `.lancedb/` | Auto-generated vector index — never edit manually, always rebuilt from vault |

**Key decisions:**
- Markdown is the source of truth. LanceDB is the search index — disposable, always rebuildable.
- The AI never picks the memory tier. The classifier does it based on content.
- Engine only listens on `127.0.0.1`. Nothing reaches your vault from the internet directly.
- Two MCP transports: stdio for local (zero config), HTTP for network (NAS/LAN).

---

## Engine Commands

```bash
python engine/omniscience.py start     # Start engine in background
python engine/omniscience.py stop      # Stop engine
python engine/omniscience.py status    # Check if running
python engine/omniscience.py doctor    # Full health check
python engine/omniscience.py logs      # View recent logs
python engine/omniscience.py sync-skills  # Sync skills to all AI runtimes
```

---

## Nightly Maintenance

Auto-runs every night to keep memory clean:

```bash
bash engine/install_nightly_timer.sh  # install systemd timer (Linux)
```

What it does: cache purge → short-term TTL expiry → state bootstrap → freshness snapshot → health check. Logs to `.omniscience/nightly.log`.

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Engine status and vault stats |
| `/search` | POST | Semantic search with optional namespace filter |
| `/capture` | POST | Store a memory entry |
| `/admin/reindex` | POST | Force full reindex |
| `/admin/cleanup` | POST | Run cleanup |

Optional auth: `export OMNI_API_KEY="your-token"` then `Authorization: Bearer $OMNI_API_KEY`.

---

## Contributing

**This project solves a real problem that affects every serious AI user.** Contributions that make it better, easier to set up, or more universal are very welcome.

Good places to start:
- **More migration parsers** — Gemini export, Grok export, generic JSON format
- **More AI runtime adapters** — if your AI tool has a skill/context format, add an adapter
- **Better MCP setup UX** — anything that makes the initial connection less painful
- **Obsidian theme improvements** — the vault has a custom CSS theme, improvements welcome
- **Documentation** — if something confused you during setup, a PR fixing it helps everyone

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## License

MIT — use freely, modify freely, ship it.
