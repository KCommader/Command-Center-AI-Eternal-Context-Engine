# 🧠 Omniscience Engine
### Eternal Context for AI — Local, Private, Visual

A lightweight backend that gives any local AI assistant **eternal memory** by combining:
- 📁 **Obsidian Vault** — human-readable Markdown files you can visually browse
- ⚡ **LanceDB** — on-disk vector database for millisecond semantic search
- 🌐 **FastAPI** — a local REST API any AI/script on your network can query

> No cloud. No subscriptions. No lock-in. Your context lives on your machine.

---

## How It Works

```
[AI Input / Custom AI]
        ↓  captures context
[vault/ Markdown Files]  ←→  Browse in Obsidian (Graph View, DB plugin)
        ↓  watched by engine
[engine/engine.py]
        ↓  embeds + indexes
[.lancedb/ Vector DB]
        ↓  responds to queries
[Any AI on your machine/network]
```

1. Your AI writes context to `vault/Archive/` (auto-capture or manual)
2. The Engine watches for changes and immediately indexes them into LanceDB
3. Any AI queries `http://localhost:8765/search?q=your+question`
4. The Engine returns semantically relevant context from your vault
5. You can see your knowledge "brain" growing live in Obsidian's Graph View

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r engine/requirements.txt

# 2. Start the engine (indexes vault + serves API + watches for changes)
python engine/engine.py --vault ./vault --watch

# 3. Search your context from any terminal
python engine/engine.py --vault ./vault --search "what is my content strategy"

# 4. Query via API (from any local AI or script)
curl -X POST "http://127.0.0.1:8765/search" \
  -H "Content-Type: application/json" \
  -d '{"query":"risk management","k":5}'
```

---


## App Mode (Thin Launcher)

If you want this to feel like an app instead of manually managing processes:

```bash
# Health check your local setup
python engine/omniscience.py doctor

# Start in background (app mode)
python engine/omniscience.py start --vault ./vault

# Check status
python engine/omniscience.py status

# Show recent logs
python engine/omniscience.py logs --lines 80

# Stop
python engine/omniscience.py stop
```

This wrapper does **not** replace your engine logic.
It simply manages process lifecycle (start/stop/status/logs).

---


## API Auth (Optional, Recommended)

Default mode is local-open if no API keys are set.

Single-key mode (simplest):

```bash
export OMNI_API_KEY="replace-with-long-random-token"
```

Optional advanced split roles:

```bash
export OMNI_API_KEYS_READ="read_token"
export OMNI_API_KEYS_WRITE="write_token"
export OMNI_API_KEYS_ADMIN="admin_token"
```

Use bearer token in requests:

```bash
curl -X POST "http://127.0.0.1:8765/search" \
  -H "Authorization: Bearer $OMNI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query":"latest project decisions","k":5,"namespaces":["company_memory"]}'
```

---

## Why These Choices

- **JSON body for `/search` and `/capture`**: better input validation, cleaner contracts for AIs/scripts, and avoids putting sensitive content in URL query strings.
- **Why URL query strings are risky**: query params can leak into browser history, access logs, reverse-proxy logs, and monitoring tools.
- **Bearer token auth**: simple, standard, and enough for local/LAN setups. Start with one key (`OMNI_API_KEY`), then split read/write/admin keys only if needed.
- **Namespace filters**: keep big knowledge sets (e.g., cooking books) from polluting runtime project-memory retrieval.

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Engine status + vault stats |
| `/search` | POST (JSON) | Semantic search with optional filters |
| `/capture` | POST (JSON) | Store a memory entry with metadata |
| `/admin/reindex` | POST | Trigger background reindex (admin key) |

---

## Vault Structure

```
vault/
├── DASHBOARD.md          ← Live status (auto-updated by engine)
├── Core/
│   ├── SOUL.md           ← AI identity & behavior rules
│   ├── COMPANY-SOUL.md   ← Organization/project mission
│   └── USER.md           ← User context (name, timezone, stack)
├── Knowledge/            ← Your domain knowledge (strategies, docs)
└── Archive/
    └── MEMORY.md         ← Auto-captured facts and preferences
```

---

## Obsidian Setup

1. Install [Obsidian](https://obsidian.md) (free)
2. Open `vault/` as a vault
3. Enable **Graph View** (Core Plugins) to see nodes connect as context grows
4. Optional: Install **DB Folder** plugin for database-style view of your context

---

## Migrating to a New Machine

```bash
# Copy the entire Command-Center-AI folder
# On new machine:
pip install -r engine/requirements.txt
python engine/engine.py --vault ./vault --reindex
```
That's it. LanceDB rebuilds from your Markdown files in seconds.

---

## Architecture Notes

- **Embedding model**: `BAAI/bge-small-en-v1.5` — runs 100% locally, ~130MB, ~50ms/doc
- **Vector DB**: LanceDB — embedded, disk-based, no server required (like SQLite for vectors)
- **API**: FastAPI on `localhost:8765` by default — only accessible on your machine
- **Auto-capture**: POST to `/capture` from any AI to store new facts permanently

---

## License

MIT — use freely, modify freely, ship it.
