# Command Center AI — Session Context

## Bootstrap (Do This First)

If the Command Center MCP is connected, call this at the start of every session:

```
bootstrap_agent(reason="session_start")
```

This loads your identity files, active working set, session handoff, and recommended skills in one call. It's the fix for context compaction — your AI resumes exactly where you left off regardless of what the provider cleared.

If the engine isn't running yet:
```bash
python engine/omniscience.py start
```

---

## What This Is

Local-first AI memory system. Markdown source of truth + LanceDB semantic search + MCP interface + Obsidian visual layer.

- `vault/` — Obsidian vault (Core/, Archive/, Knowledge/, Skills/, Templates/)
- `engine/` — FastAPI + LanceDB engine on port 8765
- `engine/mcp_server.py` — MCP server (stdio + Streamable HTTP)
- No web dashboard — Obsidian is the frontend (intentional)

## Key Facts

- Open the `vault/` subfolder in Obsidian — not the repo root
- `vault/Core/*.md` and `vault/Archive/MEMORY.md` are gitignored — your personal data stays local
- `vault/Migration/` is gitignored — your AI history stays local
- LanceDB index (`.lancedb/`) is auto-generated from Markdown — never edit it directly

## API Endpoints (port 8765)

- `GET  /health` — engine status and vault stats
- `POST /search` — semantic search
- `POST /capture` — store a memory
- `POST /admin/reindex` — force full reindex (admin key required)
- `POST /admin/cleanup` — run cleanup (admin key required)

## MCP Tools Available

Once connected: `search_memory`, `store`, `read_vault_file`, `list_vault`, `list_skills`, `read_skill`, `resolve_skills`, `bootstrap_agent`, `update_working_set`, `record_handoff`, `verify_vault_file`, `freshness_report`, `sync_skills`

## Repo

github.com/KCommader/Command-Center-AI-Eternal-Context-Engine
