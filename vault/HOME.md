---
aliases:
  - Home
  - Dashboard
cssclasses:
  - cc-home
---

<div class="cc-hero">

# Command Center

**Eternal memory for any AI — local, private, portable.**

</div>

---

## Identity

> [!identity] Core Configuration
> Fill these three files once. Every AI session loads them automatically — full context, zero re-explaining.
>
> **[[Core/USER|USER]]** — Who you are: background, preferences, goals, tech stack
> **[[Core/SOUL|SOUL]]** — AI behavior rules: tone, directives, what to always and never do
> **[[Core/COMPANY-SOUL|COMPANY SOUL]]** — Organization mission, active projects, team context

---

## Operating State

> [!state] Eternal Context Engine
> These files are the enforced working set for startup and post-compact recovery.
>
> **[[Core/ACTIVE_CONTEXT|ACTIVE CONTEXT]]** — current mission, priorities, constraints, next actions
> **[[Core/SESSION_HANDOFF|SESSION HANDOFF]]** — latest durable checkpoint between sessions
> **[[Core/FRESHNESS|FRESHNESS]]** — stale-file detector for the core operating files

---

## Memory

> [!memory] Long-Term Memory
> Permanent facts, decisions, and directives — never auto-deleted.
>
> ```dataview
> TABLE WITHOUT ID file.link AS "File", dateformat(file.mtime, "yyyy-MM-dd HH:mm") AS "Last Updated", file.size AS "Bytes"
> FROM "Archive" AND !"Archive/short"
> WHERE file.name != ".gitkeep"
> SORT file.mtime DESC
> ```

> [!session]- Active Sessions (30-day TTL)
> Short-term memory — tasks in progress, recent backtests, current sprint state.
>
> ```dataview
> TABLE WITHOUT ID file.link AS "Session", dateformat(file.mtime, "yyyy-MM-dd") AS "Date", file.size AS "Bytes"
> FROM "Archive/short"
> WHERE file.name != ".gitkeep"
> SORT file.mtime DESC
> LIMIT 10
> ```

> [!cache]- Cache (clears nightly)
> Session noise — greetings, one-off questions, ephemeral context.
>
> ```dataview
> LIST FROM "Cache"
> WHERE file.name != ".gitkeep"
> SORT file.mtime DESC
> ```

---

## Knowledge Base

> [!knowledge] Your Notes
> Domain knowledge, research, strategies, references — always semantically searchable by any connected AI.
>
> ```dataview
> TABLE WITHOUT ID file.link AS "Note", dateformat(file.mtime, "yyyy-MM-dd") AS "Updated"
> FROM "Knowledge"
> WHERE file.name != ".gitkeep" AND !contains(file.path, "/attachments")
> SORT file.mtime DESC
> ```

---

## System

> [!engine] Engine Status
> | | |
> |---|---|
> | **API** | `http://localhost:8765` |
> | **Start** | `python engine/omniscience.py start` |
> | **Stop** | `python engine/omniscience.py stop` |
> | **Status** | `python engine/omniscience.py status` |
> | **Health** | `python engine/omniscience.py doctor` |
> | **Logs** | `python engine/omniscience.py logs` |
>
> MCP connection configured in `~/.claude/settings.json` (Claude Code) or `claude_desktop_config.json` (Claude Desktop).

---

## Skills

> [!skills] Available to Any Connected AI
> Every AI connected via MCP or REST can use these capabilities. Add a file to `Skills/` to register a new skill — it appears here automatically.
>
> ```dataview
> TABLE WITHOUT ID file.link AS "Skill", trigger AS "Trigger", description AS "What it does", category AS "Category"
> FROM "Skills"
> WHERE type = "skill"
> SORT category ASC, file.name ASC
> ```

---

> [!tip] How Memory Flows
> Your AI calls `store("content")` → **Memory Classifier** reads it → routes to the right tier automatically.
> No manual classification. No configuration. It just works.
>
> See [[ARCHITECTURE]] to visualize the full system.
