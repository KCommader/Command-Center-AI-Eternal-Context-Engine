---
type: manifest
status: active
updated_by: KAI
updated: 2026-04-06
namespace: company_core
---

# Projects Manifest

Every active project in the Kaiju empire. This is the bootstrap map — any AI resuming a session reads this first to know where everything lives, what's in progress, and how to access the code.

## How Project Access Works

Projects live in their own folders on disk. Command Center indexes their documentation via symlinks in `vault/Projects/`. Any AI can:
1. Read this manifest for full context
2. Navigate to the real path on disk to read/edit code
3. Use `search_memory(namespace="projects")` or `search_memory(namespace="bots_runtime")` for semantic search across all project docs

---

## 🔴 Kaiju Capital — Trading System
**Disk:** `/home/cypher/Documents/Antigravity/` (workspace folder name — the empire is always Kaiju)
**Vault index:** `vault/Projects/bots/kaiju-trading/`, `vault/Projects/kaiju-fund/`, `vault/Projects/kaiju-research/`
**Status:** ACTIVE — live bots running

### kaiju_poly (Polymarket Oracle Lag Bot)
- **Path:** `/home/cypher/Documents/Antigravity/Trading Bots/kaiju_pro/kaiju_poly.py`
- **Strategy:** SOL oracle lag — Chainlink vs Binance price divergence on 5-min windows
- **Status:** Live champion running, accumulating resolved trades
- **Config:** `MIN_PRICE_LAG=0.52`, `MAX_PRICE=0.60`, oracle gap tightened post-regression fix
- **Logs:** `/home/cypher/Documents/Antigravity/Trading Bots/kaiju_pro/results/kaiju_poly.log`
- **Watchdog:** `/home/cypher/Documents/Antigravity/Trading Bots/kaiju_pro/results/watchdog.log`

### kaiju_scanner_live (Hyperliquid Perps)
- **Path:** `/home/cypher/Documents/Antigravity/Trading Bots/kaiju_pro/kaiju_scanner_live.py`
- **Strategy:** LTR + FVG + CVD + Pulse orderflow — 229 assets
- **Status:** Research / paper mode
- **HL Account:** UNIFIED, wallet `0xbd55C3ADeE8B7bC709ADe1c570139CE64082dFc0`

### Kaiju RH Spread Bot (TO BUILD)
- **Plan:** Unusual Whales sweep detector → yfinance options chain scorer → Telegram alert
- **Blocker:** Need `UNUSUAL_WHALES_API_KEY` added to ENV.txt
- **ENV file:** `/home/cypher/Documents/Command-Center-AI/ENV.txt`
- **Target path:** `/home/cypher/Documents/Antigravity/Trading Bots/kaiju_pro/`

### kaiju_weather (Polymarket Weather Oracle)
- **Path:** `/home/cypher/Documents/Antigravity/Trading Bots/kaiju_pro/kaiju_weather.py`
- **Strategy:** NOAA free data vs Polymarket weather market prices
- **Status:** Built, testing

### Key Trading Docs (searchable via bots_runtime namespace)
- `vault/Projects/bots/kaiju-trading/DECISIONS.md`
- `vault/Projects/bots/kaiju-trading/DEPLOY_GATES.md`
- `vault/Projects/bots/kaiju-trading/CURRENT_STATUS.md`
- `vault/Projects/bots/kaiju-trading/NEXT_ACTIONS.md`
- `vault/Projects/bots/kaiju-trading/RUNBOOK.md`
- `vault/Projects/kaiju-fund/risk-management.md`
- `vault/Projects/kaiju-research/derived/high_edge_playbook.md`

---

## 🟡 SmartKitchenZone — E-commerce Brand
**Disk:** `/home/cypher/Documents/SmartKitchenZone/`
**Status:** ACTIVE — domain expires ~3 weeks, needs attention
**Priority:** HIGH — get site live before domain expires

---

## 🟡 MTH — Flutter App
**Disk:** `/home/cypher/Documents/Antigravity/MTH/`
**Status:** IN PROGRESS — frontend build pending
**Stack:** Flutter + Riverpod
**Notes:** Start frontend when Commander gives go-ahead

---

## 🔵 KAI — AI Infrastructure
**Disk:** `/home/cypher/Documents/KAI/`
**Sub-projects:**
- `KAI/Mission-Control-UI/` — dashboard UI
- `KAI/api/` — API layer
- `KAI/agents/` — agent configs
- `KAI/skills/` — skill library
- `KAI/Brave-Agent-Extension/` — browser agent extension

---

## 🔵 Command Center AI — Memory Engine
**Disk:** `/home/cypher/Documents/Command-Center-AI/`
**Repo:** github.com/KCommader/Command-Center-AI-Eternal-Context-Engine
**Status:** ACTIVE — production, engine on port 8765
**Stack:** FastAPI + LanceDB + MCP + Obsidian
**Open items:**
- Embedding model upgrade to POWER tier (~2min reindex downtime)
- ECE 3D frontend build (blocked on Commander readiness)

---

## 🔵 Nunchi Agent CLI
**Disk:** `/home/cypher/Documents/Antigravity/Trading Bots/nunchi-agent-cli/`
**Vault index:** `vault/Projects/bots/kaiju-trading/nunchi-agent-cli/`
**Status:** Built — OpenClaw deployment on Railway

---

## ⚪ Other Projects
- **Book Biblioteca:** `/home/cypher/Documents/Book Biblioteca/`
- **Soda Drink App:** `/home/cypher/Documents/Antigravity/Soda drinkapp/`
- **Fitness App:** `/home/cypher/Documents/Antigravity/Fitness App/`
- **Sol Automated Generator:** `/home/cypher/Documents/Antigravity/Sol Automated Generator/`
- **Brave Agent Extension:** `/home/cypher/Documents/Brave-Agent-Extension/`

---

## How Indexing Works

One symlink covers the whole machine:
```
vault/Projects/workspace  →  /home/cypher/Documents/
```

The engine scans this recursively and indexes every `.md` file it finds. New project lands on disk → CC knows about it automatically on next reindex. No manual symlink work ever needed.

**Excluded from indexing** (engine IGNORED_DIRS):
- `Command-Center-AI` — vault itself, already indexed natively
- `Back First Command iteration antigravity windows` — stale Windows backup, noise
- `.git`, `venv`, `.venv`, `.venv-linux`, `node_modules`, `dist-info`, `site-packages` — deps, never signal

## Adding a New Project
Just drop it in `/home/cypher/Documents/` with markdown docs. It gets indexed automatically.
To force immediate pickup: `curl -X POST http://localhost:8765/admin/reindex`
