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
[AI Input / OpenClaw]
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
3. Any AI sends JSON to `http://127.0.0.1:8765/search`
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

## Nightly Self-Check + Cleanup

You can enable automatic nightly maintenance (local-only):

```bash
chmod +x engine/install_nightly_timer.sh
bash engine/install_nightly_timer.sh
```

What it does each night:
- Runs `doctor` checks
- Calls `POST /admin/cleanup` if engine is running
- Writes logs to `.omniscience/nightly.log`

Manual run:

```bash
python engine/nightly_maintenance.py
```

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

### Backend Structure (Why + How)

- **`vault/` (source of truth)**
  - Why: human-readable, portable, Obsidian-native knowledge base.
  - How: all durable context is Markdown-first; engine reads from here.
- **`engine/engine.py` (index + API core)**
  - Why: one local process should both index and serve retrieval APIs.
  - How: watches markdown, chunks text, embeds locally, writes LanceDB, exposes FastAPI.
- **`.lancedb/` (semantic index)**
  - Why: fast local vector search without running external DB infrastructure.
  - How: embedded LanceDB table stores vectors + metadata for filtered retrieval.
- **Role-based bearer auth**
  - Why: keep local-first defaults but allow safe LAN usage when needed.
  - How: optional read/write/admin token split via env vars.
- **Anti-bloat controls**
  - Why: prevent performance decay as context grows.
  - How:
    - file-hash manifest skips re-embedding unchanged files
    - bounded query cache (TTL + max items)
    - temp/log cleanup caps and nightly maintenance
- **Thin launcher (`engine/omniscience.py`)**
  - Why: app-like UX for non-fragile operations.
  - How: consistent `start/stop/status/doctor/logs` wrapper over engine runtime.
- **Nightly maintenance (`engine/nightly_maintenance.py`)**
  - Why: automated health and cleanup reduces drift and runtime bloat.
  - How: runs doctor checks + admin cleanup and logs results under `.omniscience/`.
- **Migration model**
  - Why: new machine recovery should be deterministic and fast.
  - How: copy repo folder, install requirements, reindex from markdown source.

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Engine status + vault stats |
| `/search` | POST (JSON) | Semantic search with optional filters |
| `/capture` | POST (JSON) | Store a memory entry with metadata |
| `/admin/reindex` | POST | Trigger background reindex (admin key) |
| `/admin/cleanup` | POST | Run temp/cache cleanup (admin key) |

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
- **Anti-bloat controls**:
  - file-hash manifest skips re-embedding unchanged markdown
  - bounded in-memory query cache with TTL
  - automatic temp/log cleanup with caps

### Runtime Tuning (optional env vars)

```bash
OMNI_QUERY_CACHE_TTL_SEC=3600
OMNI_QUERY_CACHE_MAX_ITEMS=256
OMNI_TMP_TTL_SEC=172800
OMNI_TMP_MAX_FILES=400
OMNI_LOG_MAX_BYTES=5242880
```

---

## License

MIT — use freely, modify freely, ship it.
