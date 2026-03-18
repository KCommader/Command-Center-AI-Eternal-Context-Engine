<div align="center">

<img src="assets/logo.png" alt="Command Center AI" width="720" />

### Eternal Memory for Any AI — Local, Private, Portable

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)](https://python.org)
[![MCP](https://img.shields.io/badge/MCP-stdio%20%2B%20HTTP-purple?style=flat-square)](https://modelcontextprotocol.io)
[![LanceDB](https://img.shields.io/badge/Vector%20DB-LanceDB-orange?style=flat-square)](https://lancedb.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Obsidian](https://img.shields.io/badge/Vault-Obsidian%20Native-7C3AED?style=flat-square&logo=obsidian)](https://obsidian.md)
[![Contributions Welcome](https://img.shields.io/badge/contributions-welcome-brightgreen?style=flat-square)](CONTRIBUTING.md)

</div>

Your AI shouldn't start from scratch every session. Command Center gives any AI tool permanent, searchable memory stored as Markdown files you can read, edit, and browse in Obsidian.

**Works with**: Claude Desktop, Claude Code, Cursor, Zed, Gemini CLI, OpenClaw, or any MCP-compatible AI.

> No cloud. No subscriptions. No lock-in. Your context lives on your machine — or on a USB drive.

---

## The Problem This Solves

You're deep in a project with Claude, GPT, or Gemini. The conversation gets long. The provider **compacts**. Suddenly the AI forgets the architecture decision you made an hour ago. It hallucinates a file path. It suggests something you already ruled out. You spend 20 minutes re-explaining yourself.

This happens to everyone. It's not a bug — it's how LLMs work. **Conversations have limits. When providers hit them, they compact or truncate. Context is gone.**

Command Center stores your memory in files on your machine — outside the conversation. The AI reads your vault at the start of every session. Compaction can't touch it.

---

## What It Looks Like

<div align="center">

<img src="assets/screenshots/home-dashboard.png" alt="Command Center Home Dashboard" width="100%" />

*The Obsidian dashboard — your vault's home page. Browse your identity files, memory tiers, knowledge base, and skills.*

</div>

<div align="center">

<img src="assets/screenshots/graph-view.png" alt="Knowledge Graph View" width="100%" />

*Graph view — every note, skill, and memory as a living constellation. Core=cyan, Archive=violet, Knowledge=green.*

</div>

---

## What It Does

```
Your Notes (Markdown)  →  Vault (Obsidian Graph View)
         ↓
    Engine indexes with LanceDB (local vector DB)
         ↓
  MCP Server / REST API  →  Any AI on your machine or network
         ↓
  AI remembers you. Every session. Across machines.
```

- **Write notes in Markdown** → Engine indexes them automatically
- **AI searches your vault** via MCP or REST API — gets relevant context instantly
- **Visualize your knowledge** in Obsidian's Graph View as it grows
- **Migrate in 60 seconds** — copy folder to any machine or USB drive, reinstall deps, reindex

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/KCommader/Command-Center-AI-Eternal-Context-Engine
cd Command-Center-AI

# 2. Setup (creates venv, installs deps, scaffolds vault)
bash setup.sh

# 3. Fill in your identity
# Edit: vault/Core/USER.md       ← who you are
# Edit: vault/Core/SOUL.md       ← how you want the AI to behave
# Edit: vault/Core/COMPANY-SOUL.md ← your project/org context

# 4. Start the engine
python engine/omniscience.py start

# 5. Connect your AI (see below)
```

---

## Connecting Your AI

### Option A — MCP (Recommended for Claude, Cursor, Zed)

MCP is an open protocol. Any MCP-compatible AI gets your vault as tools + resources automatically.

> **Before connecting**: Use the absolute path to `.venv/bin/python` inside the repo — not system Python. Relative paths and system Python both break silently.

**Claude Code** (`~/.claude/settings.json`):
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

**Claude Desktop** (`~/.config/claude/claude_desktop_config.json` on Linux, `~/Library/Application Support/Claude/claude_desktop_config.json` on Mac):
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

Once connected, the AI gets these tools automatically:
- `search_memory` — semantic search across your vault
- `store` — save facts/decisions (engine auto-classifies into the right memory tier)
- `read_vault_file` — read any vault document
- `list_vault` — browse available notes
- `list_skills` — browse the cross-AI skill catalog
- `read_skill` — load one skill from the registry
- `resolve_skills` — recommend the right skills for a task or runtime
- `bootstrap_agent` — load full context or recover after compaction (see below)
- `update_working_set` — set the canonical active mission, priorities, and next actions
- `record_handoff` — write a durable session checkpoint
- `verify_vault_file` — mark a vault file as freshly verified
- `freshness_report` — detect stale or missing operating files
- `sync_skills` — push vault skills to all connected AI runtimes

**MCP not connecting?** See [Troubleshooting](#mcp-troubleshooting) below.

### Option B — Network MCP via Streamable HTTP (NAS / Multi-Machine)

**Why this exists**: stdio requires the MCP server to run on the same machine as the AI.
If you have a NAS or home server, run one Command Center instance and connect every machine on your network to the same vault. One memory. Shared everywhere.

**On your NAS/server:**
```bash
OMNI_MCP_KEY=your_secret_token \
OMNI_VAULT_PATH=/path/to/vault \
OMNI_ENGINE_URL=http://127.0.0.1:8765 \
python engine/mcp_server.py --transport http --port 8766
```

**On every client machine** (`~/.claude/settings.json`):
```json
{
  "mcpServers": {
    "command-center": {
      "url": "http://YOUR_NAS_IP:8766/mcp",
      "headers": { "Authorization": "Bearer your_secret_token" }
    }
  }
}
```

> **Security**: The engine already has role-based Bearer tokens (read/write/admin). Add `OMNI_MCP_KEY` for the MCP HTTP layer too. Keep the engine on `localhost` — only the MCP server needs to be LAN-accessible.

### Option C — REST API (For scripts and bots)

```bash
# Start engine
python engine/omniscience.py start

# Search your vault
curl -X POST "http://127.0.0.1:8765/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "my trading strategy", "k": 5}'

# Store a memory
curl -X POST "http://127.0.0.1:8765/capture" \
  -H "Content-Type: application/json" \
  -d '{"content": "User prefers Python over Node for data pipelines"}'
```

---

## MCP Troubleshooting

The five most common failure modes:

**1. Wrong Python** — `command` must point to `.venv/bin/python` inside the repo, not system Python.
```bash
ls /path/to/Command-Center-AI/.venv/bin/python  # this is what you need
```

**2. Relative paths** — every path in the MCP config must be absolute. `~/` and `./` break silently on some clients.

**3. Engine not running** — the MCP server talks to the engine on port 8765. Check first:
```bash
python engine/omniscience.py status
python engine/omniscience.py doctor
```

**4. Config file location varies by AI** — Claude Code uses `~/.claude/settings.json`, Claude Desktop uses a different path per OS, Cursor and Zed have their own locations. Check the specific tool's MCP docs.

**5. Restart required** — MCP servers are spawned at startup. Editing the config requires a full restart of the AI tool, not just a new chat.

---

## Bootstrap — Surviving Compaction

When a provider compacts a conversation, the AI loses all context it accumulated during the session. `bootstrap_agent` is the recovery mechanism.

**What it does**: generates a structured startup packet from your vault in one call — your identity, active project, what was decided last session, what skills are relevant. Any AI can call it at session start or immediately after compaction to restore full context.

**At session start** — tell your AI:
```
Call bootstrap_agent to load my context before we start.
```

**After compaction** — the AI calls:
```
bootstrap_agent(agent="Claude", reason="compact_recovery")
```

**Add it to your CLAUDE.md** for automatic behavior:
```
At the start of every session, call bootstrap_agent to load context.
If the conversation compacts, call bootstrap_agent again to recover.
```

The vault always has the current state. The memory was never in the conversation — compaction can't touch it.

---

## Vault Structure

```
vault/
├── Core/
│   ├── USER.md             ← Who you are (fill this in)
│   ├── SOUL.md             ← AI identity & behavior rules (fill this in)
│   └── COMPANY-SOUL.md     ← Organization/project mission (fill this in)
├── Knowledge/              ← Your domain notes (strategies, docs, research)
├── Skills/                 ← AI skill registry (available to all connected AIs)
└── Archive/
    └── MEMORY.md           ← Auto-captured facts and decisions
```

The three Core files are your foundation. Fill them in once and every AI session starts with full context.

---

## App Mode (Background Process)

```bash
python engine/omniscience.py start --vault ./vault   # Start in background
python engine/omniscience.py status                   # Check status
python engine/omniscience.py logs --lines 50          # View logs
python engine/omniscience.py stop                     # Stop
python engine/omniscience.py doctor                   # Health check
python engine/omniscience.py sync-skills              # Push skills to all AI runtimes
```

---

## Obsidian — The Intended Interface

**[Install Obsidian](https://obsidian.md) (free), open the `vault/` folder as a vault.** Not the repo root — the `vault/` subfolder.

The repo ships a complete `.obsidian/` config inside `vault/` with everything pre-wired:

| What's included | What it does |
|---|---|
| `HOME.md` | Dashboard landing page — live memory stats via Dataview, quick links to all core files |
| `ARCHITECTURE.canvas` | Visual diagram of the full system: vault → engine → MCP → AI tools |
| `snippets/command-center.css` | Electric blue accent (#00d4ff), custom callout types per memory tier, Dataview table polish |
| `graph.json` | Color groups tuned for the vault: Core=cyan, Archive=violet, Knowledge=green |
| `bookmarks.json` | HOME.md and ARCHITECTURE.canvas pinned in the sidebar |
| `Templates/` | Note templates for Knowledge entries and Decision Logs |

Dataview (MIT) is bundled — no plugin installation needed. Open the vault and it works.

> The vault is plain Markdown. Everything works without Obsidian. But the graph view watching your memory grow in real time is the whole experience.

---

## Skills — Universal Across All AIs

Add a Markdown file to `vault/Skills/` and every connected AI can access it. Sync skills to each AI's native format automatically:

```bash
python engine/omniscience.py sync-skills                     # all runtimes
python engine/omniscience.py sync-skills --runtime claude    # one runtime
python engine/omniscience.py sync-skills --dry-run           # preview
python engine/omniscience.py sync-skills --list              # list all skills
```

Supported runtimes: `claude` (`~/.claude/skills/`), `gemini` (`~/.gemini/skills/`), `codex` (`~/.codex/skills/`), `openclaw`.

---

## Migrating to a New Machine

```bash
# 1. Copy the entire Command-Center-AI folder (vault/ included)
# 2. On new machine:
bash setup.sh
python engine/omniscience.py start
# Done. LanceDB rebuilds from Markdown in seconds.
```

Or put it on a USB drive. Runs anywhere Python runs.

---

## Migrating from Other AI Tools

Bring your existing AI conversation history into the vault:

```bash
# ChatGPT export (Settings → Export data → conversations.json)
python scripts/migrate_openai.py --input ~/Downloads/conversations.json

# Claude export
python -m migration claude --input ~/Downloads/claude-export/
```

Extracts decisions, preferences, and project context from your conversation history and writes structured Markdown into `vault/Migration/` — ready for semantic search.

---

## Memory Tiers — How Storage Works

Command Center stores memory in three tiers automatically. You never classify manually — the engine's classifier reads the content and decides.

| Tier | Location | TTL | What goes here |
|------|----------|-----|----------------|
| **cache** | `vault/Cache/session-YYYY-MM-DD.md` | Cleared nightly | Greetings, one-off questions, session noise |
| **short_term** | `vault/Archive/short/YYYY-MM-DD.md` | 30 days | Active tasks, project state, in-progress work |
| **long_term** | `vault/Archive/MEMORY.md` | Never expires | Preferences, decisions, identity rules, directives |

**How classification works** (`engine/memory_classifier.py`):
- Force keywords override everything: `"remember this"`, `"never forget"`, `"permanent"` → always long_term
- Long-term signals: `always`, `never`, `decided`, `from now on`, `my wallet`, `tech stack`
- Short-term signals: `working on`, `current task`, `blocked`, `this sprint`, `backtest result`
- Cache signals: greetings, `just checking`, `show me`, `today`
- No signal → short_term (better to keep than lose)

**The AI calls `store("content")` — classifier routes it. That's the whole interface.**

---

## Nightly Maintenance

Auto-cleanup and health checks every night (prevents memory bloat):

```bash
chmod +x engine/install_nightly_timer.sh
bash engine/install_nightly_timer.sh
```

What it does:
- **Engine health check** — runs `doctor` to verify vault + index are healthy
- **Cache purge** — deletes all files in `vault/Cache/` (session noise, not worth keeping)
- **Short-term expiry** — removes files in `vault/Archive/short/` older than 30 days
- **State bootstrap** — ensures operating-state files exist
- **Freshness snapshot** — regenerates `vault/Core/FRESHNESS.md`
- Logs everything to `.omniscience/nightly.log`

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Engine status and vault stats |
| `/search` | POST | Semantic search with optional namespace filter |
| `/capture` | POST | Store a memory entry |
| `/admin/reindex` | POST | Force full reindex (admin key required) |
| `/admin/cleanup` | POST | Run cleanup (admin key required) |

### Auth (Optional)

```bash
export OMNI_API_KEY="your-secret-token"
curl -H "Authorization: Bearer $OMNI_API_KEY" ...
```

For LAN/network use, split read/write/admin tokens:
```bash
export OMNI_API_KEYS_READ="read_token"
export OMNI_API_KEYS_WRITE="write_token"
export OMNI_API_KEYS_ADMIN="admin_token"
```

---

## Architecture

| Component | Why | What |
|---|---|---|
| `vault/` | Human-readable, Obsidian-native | Markdown source of truth |
| `engine/engine.py` | One process for index + API | Watches vault, embeds, serves search |
| `engine/memory_classifier.py` | Auto memory routing | Rule-based tier classifier — no LLM needed, ~1ms |
| `engine/context_state.py` | Compaction resilience | Reads/writes ACTIVE_CONTEXT, SESSION_HANDOFF, FRESHNESS |
| `engine/skill_adapter.py` | Universal skills | Syncs vault skills to each AI runtime's native format |
| `.lancedb/` | Fast local vector search | Like SQLite but for vectors — auto-built, never touch manually |
| `engine/mcp_server.py` | Universal AI connector | MCP protocol, two transports: stdio (local) + HTTP (network) |
| `engine/omniscience.py` | App-like UX | start/stop/status/doctor/logs/sync-skills |
| `engine/nightly_maintenance.py` | Anti-bloat | Cache purge + short-term TTL expiry + health check |

**Key design decisions:**
- **Markdown is the source of truth** — all memory lives in `.md` files you can read, edit, and open in Obsidian. LanceDB is the auto-generated search index, never the source.
- **The AI never picks the memory tier** — `memory_classifier.py` does it based on content patterns.
- **Vault is air-gapped** — engine only listens on `127.0.0.1`. Nothing from the internet reaches your memory directly.
- **Role-based auth** — separate Bearer tokens for read/write/admin.
- **Two MCP transports** — stdio spawns the server locally (zero config, works instantly). Streamable HTTP runs on a NAS and serves any machine on your LAN.

- **Embedding model**: `BAAI/bge-small-en-v1.5` — 100% local, ~130MB, ~50ms/doc
- **Vector DB**: LanceDB — embedded, disk-based, no server needed
- **API**: FastAPI on `localhost:8765`

---

## Scripts

`scripts/` contains standalone tools that work alongside the engine.

- **`scripts/migrate_openai.py`** — Import ChatGPT history into the vault
- **`scripts/browser_test.py`** — Example of giving your AI a real browser via `browser-use`

```bash
ANTHROPIC_API_KEY=your_key .venv/bin/python scripts/browser_test.py
```

> Add your own scripts here. Keep personal/sensitive scripts in subdirectories listed in `.gitignore`.

---

## Contributing

**Contributions welcome.** This project solves a real problem for every serious AI user — the more runtimes, migration parsers, and adapters it supports, the more useful it becomes for everyone.

Good places to start:
- Migration parsers for Gemini, Grok, and generic JSON export formats
- AI runtime adapters for new tools
- MCP setup improvements and better error messages
- Obsidian theme and template contributions

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

---

## License

MIT — use freely, modify freely, ship it.
