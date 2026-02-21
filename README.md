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
python engine/engine.py --vault ./vault --search "what is my trading strategy"

# 4. Query via API (from any local AI or script)
curl "http://localhost:8765/search?q=risk+management&k=5"
```

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Engine status + vault stats |
| `/search?q=<query>&k=<n>` | GET | Semantic search, returns top-k chunks |
| `/capture?text=<text>&tag=<tag>` | POST | Store a memory directly |

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
