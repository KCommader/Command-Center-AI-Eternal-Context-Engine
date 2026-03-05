# 🧠 Command Center AI
### Eternal Memory for Any AI — Local, Private, Portable

Your AI shouldn't start from scratch every session. Command Center gives any AI tool permanent, searchable memory stored as Markdown files you can read, edit, and browse in Obsidian.

**Works with**: Claude Desktop, Claude Code, Cursor, Zed, Gemini CLI, Custom AI, or any MCP-compatible AI.

> No cloud. No subscriptions. No lock-in. Your context lives on your machine — or on a USB drive.

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
- **Migrate in 60 seconds** — copy folder, reinstall deps, reindex

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/KCommader/Command-Center-AI-Eternal-Context-Engine
cd Command-Center-AI

# 2. Install
pip install -r engine/requirements.txt

# 3. Fill in your identity (copy templates, then edit them)
cp vault/Core/USER.md.example vault/Core/USER.md
cp vault/Core/SOUL.md.example vault/Core/SOUL.md
cp vault/Core/COMPANY-SOUL.md.example vault/Core/COMPANY-SOUL.md

# 4. Start the engine
python engine/engine.py --vault ./vault --watch

# 5. Connect your AI (see below)
```

---

## Connecting Your AI

### Option A — MCP (Recommended for Claude, Cursor, Zed)

MCP is Anthropic's open protocol. Any MCP-compatible AI gets your vault as tools + resources automatically.

**Claude Desktop** (`~/.config/claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "command-center": {
      "command": "python",
      "args": ["/absolute/path/to/Command-Center-AI/engine/mcp_server.py"],
      "env": {
        "OMNI_VAULT_PATH": "/absolute/path/to/Command-Center-AI/vault",
        "OMNI_ENGINE_URL": "http://127.0.0.1:8765"
      }
    }
  }
}
```

**Claude Code** (`.claude/mcp_config.json` in your project):
```json
{
  "mcpServers": {
    "command-center": {
      "command": "python",
      "args": ["/absolute/path/to/Command-Center-AI/engine/mcp_server.py"]
    }
  }
}
```

Once connected, the AI gets these tools automatically:
- `search_memory` — semantic search across your vault
- `store` — save facts/decisions (engine auto-classifies into the right memory tier)
- `read_vault_file` — read any vault document
- `list_vault` — browse available notes

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
python engine/engine.py --vault ./vault --watch

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

## Vault Structure

```
vault/
├── Core/
│   ├── USER.md          ← Who you are (fill this in)
│   ├── SOUL.md          ← AI identity & behavior rules (fill this in)
│   └── COMPANY-SOUL.md  ← Organization/project mission (fill this in)
├── Knowledge/           ← Your domain notes (strategies, docs, research)
├── Archive/
│   └── MEMORY.md        ← Auto-captured facts and decisions
└── DASHBOARD.md         ← Live status (auto-updated by engine)
```

The three Core files are your foundation. Fill them in once and every AI session starts with full context.

---

## Connecting Other Folders

Command Center is designed to connect to adjacent knowledge bases without bloating the core engine.

```
~/Documents/
├── Command-Center-AI/     ← Core engine (this repo)
├── MyBooks/               ← 10k book library
├── WorkProject/           ← Project notes
└── Research/              ← Domain research
```

Point the engine at any folder:
```bash
# Index an additional folder as a namespace
python engine/engine.py --vault ./vault --extra-vault ../MyBooks --namespace books
python engine/engine.py --vault ./vault --extra-vault ../Research --namespace research
```

Then query by namespace:
```bash
curl -X POST "http://127.0.0.1:8765/search" \
  -d '{"query": "romance novels", "namespaces": ["books"]}'
```

---

## App Mode (Background Process)

```bash
python engine/omniscience.py start --vault ./vault   # Start in background
python engine/omniscience.py status                   # Check status
python engine/omniscience.py logs --lines 50          # View logs
python engine/omniscience.py stop                     # Stop
python engine/omniscience.py doctor                   # Health check
```

---

## Obsidian Setup

1. Install [Obsidian](https://obsidian.md) (free)
2. Open `vault/` as a vault
3. Enable **Graph View** (Core Plugins) — watch your knowledge map grow as context accumulates
4. Optional: Install **DB Folder** plugin for database-style browsing

---

## Migrating to a New Machine

```bash
# 1. Copy the entire Command-Center-AI folder (vault/ included)
# 2. On new machine:
pip install -r engine/requirements.txt
python engine/engine.py --vault ./vault --reindex
# Done. LanceDB rebuilds from Markdown in seconds.
```

Or put it on a USB drive. Runs anywhere Python runs.

---

## Nightly Maintenance

Auto-cleanup and health checks every night (prevents memory bloat):

```bash
chmod +x engine/install_nightly_timer.sh
bash engine/install_nightly_timer.sh
```

What it does:
- Runs health checks
- Cleans expired cache entries
- Trims old logs
- Keeps the engine lean

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
| `.lancedb/` | Fast local vector search | Like SQLite but for vectors |
| `engine/mcp_server.py` | Universal AI connector | MCP protocol — works with any compatible AI |
| `engine/omniscience.py` | App-like UX | start/stop/status/doctor/logs |
| `engine/nightly_maintenance.py` | Anti-bloat | Automated cleanup and health |

- **Embedding model**: `BAAI/bge-small-en-v1.5` — 100% local, ~130MB, ~50ms/doc
- **Vector DB**: LanceDB — embedded, disk-based, no server needed
- **API**: FastAPI on `localhost:8765`
- **MCP transports**: stdio (local, zero-config) + Streamable HTTP (NAS/network, Bearer auth)

---

## Smart Connections Comparison

If you know Obsidian's Smart Connections plugin, this is the self-hosted version — on steroids:

| Feature | Smart Connections | Command Center |
|---|---|---|
| Semantic search | ✅ | ✅ |
| Graph view | ✅ (Obsidian) | ✅ (Obsidian) |
| Works across AI tools | ❌ (Obsidian only) | ✅ (MCP + REST) |
| Network accessible | ❌ | ✅ |
| Multiple vaults/namespaces | ❌ | ✅ |
| API for scripts/bots | ❌ | ✅ |
| Portable (USB) | Partial | ✅ |
| No cloud | ✅ | ✅ |

---

## License

MIT — use freely, modify freely, ship it.

---

## Contributing

Issues and PRs welcome. The goal is a simple, portable, powerful memory layer — keep it lean.
