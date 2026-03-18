---
aliases:
  - Home
  - Dashboard
cssclasses:
  - cc-home
---

<div class="cc-hero">

# Command Center

**Your AI's memory — local, private, eternal.**

</div>

> [!tip] First time here?
> Fill in the three files under **Identity** below. Every AI session loads them automatically. That's the whole setup.

---

## Identity

> [!identity] Core Configuration
> These three files are what your AI reads at the start of every session. Fill them in once — full context, zero re-explaining, forever.
>
> **[[Core/USER|USER]]** — Who you are: background, preferences, tech stack, how you like to work
> **[[Core/SOUL|SOUL]]** — AI behavior rules: tone, what to always do, what to never do
> **[[Core/COMPANY-SOUL|COMPANY SOUL]]** — Your project or organization: mission, active work, context

---

## Memory

> [!memory] Long-Term Memory
> Permanent facts, decisions, and directives — never auto-deleted. Your AI writes here when you say "remember this" or "from now on".
>
> ```dataview
> TABLE WITHOUT ID file.link AS "File", dateformat(file.mtime, "yyyy-MM-dd HH:mm") AS "Last Updated"
> FROM "Archive" AND !"Archive/short"
> WHERE file.name != ".gitkeep"
> SORT file.mtime DESC
> ```

> [!session]- Active Sessions (30-day TTL)
> Short-term memory — tasks in progress, project state, current sprint context. Auto-expires after 30 days.
>
> ```dataview
> TABLE WITHOUT ID file.link AS "Session", dateformat(file.mtime, "yyyy-MM-dd") AS "Date"
> FROM "Archive/short"
> WHERE file.name != ".gitkeep"
> SORT file.mtime DESC
> LIMIT 10
> ```

> [!cache]- Cache (clears nightly)
> Session noise — greetings, one-off questions, ephemeral context. Purged automatically every night.
>
> ```dataview
> LIST FROM "Cache"
> WHERE file.name != ".gitkeep"
> SORT file.mtime DESC
> ```

---

## Knowledge Base

> [!knowledge] Your Notes
> Domain knowledge, research, strategies, references. Always semantically searchable by any connected AI — just drop a Markdown file in `Knowledge/`.
>
> ```dataview
> TABLE WITHOUT ID file.link AS "Note", dateformat(file.mtime, "yyyy-MM-dd") AS "Updated"
> FROM "Knowledge"
> WHERE file.name != ".gitkeep" AND !contains(file.path, "/attachments")
> SORT file.mtime DESC
> ```

---

## Skills

> [!skills] Available to Any Connected AI
> Skills are prompt libraries — playbooks, best practices, domain knowledge — that any AI can load on demand. Add a `.md` file to `Skills/` and it appears here automatically.
>
> ```dataview
> TABLE WITHOUT ID file.link AS "Skill", trigger AS "Trigger", description AS "What it does"
> FROM "Skills"
> WHERE type = "skill"
> SORT category ASC, file.name ASC
> ```

---

## Engine

> [!engine] Engine Status
> | | |
> |---|---|
> | **API** | `http://localhost:8765` |
> | **Start** | `python engine/omniscience.py start` |
> | **Status** | `python engine/omniscience.py status` |
> | **Health** | `python engine/omniscience.py doctor` |
> | **Logs** | `python engine/omniscience.py logs` |
> | **Sync Skills** | `python engine/omniscience.py sync-skills` |
>
> Connect via MCP — see `README.md` for config snippets for Claude Code, Claude Desktop, Cursor, and Zed.

---

> [!tip] How Memory Flows
> Your AI calls `store("content")` → engine classifier reads it → routes to the right tier automatically.
> No manual classification. No configuration. It just works.
>
> See [[ARCHITECTURE]] to visualize the full system.
