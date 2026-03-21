#!/usr/bin/env python3
"""
Command Center AI — MCP Server
Exposes your vault as an MCP (Model Context Protocol) server.

Any MCP-compatible AI (Claude Desktop, Claude Code, Cursor, Zed, etc.)
gets your persistent memory automatically — no manual commands needed.

Memory is stored in three automatic tiers:
  cache      → Session context. Cleared nightly.
  short_term → Project/task state. Auto-expires after 30 days.
  long_term  → Preferences, decisions, identity. Never expires.

The AI never decides the tier — the engine's classifier does.

── Transport Modes ───────────────────────────────────────────────────────────

  stdio (default — local machine)
      python engine/mcp_server.py
      Works instantly. Claude Code, Claude Desktop, Cursor, Zed spawn it
      as a child process. No network, no auth needed.

  http (NAS / network — all machines on your LAN share one vault)
      python engine/mcp_server.py --transport http --port 8766
      Any AI on your network connects via URL instead of spawning a process.
      Protect with a Bearer token (OMNI_MCP_KEY env var).

── Connecting Claude Code (local stdio) ──────────────────────────────────────

  ~/.claude/settings.json:
  {
    "mcpServers": {
      "command-center": {
        "command": "/path/to/.venv/bin/python",
        "args": ["/path/to/Command-Center-AI/engine/mcp_server.py"],
        "env": {
          "OMNI_VAULT_PATH": "/path/to/Command-Center-AI/vault",
          "OMNI_ENGINE_URL": "http://127.0.0.1:8765"
        }
      }
    }
  }

── Connecting Claude Code (network HTTP — NAS or server) ─────────────────────

  ~/.claude/settings.json:
  {
    "mcpServers": {
      "command-center": {
        "url": "http://YOUR_NAS_IP:8766/mcp",
        "headers": { "Authorization": "Bearer YOUR_MCP_KEY" }
      }
    }
  }

── Running the HTTP server on your NAS ───────────────────────────────────────

  OMNI_MCP_KEY=your_secret_token \\
  OMNI_VAULT_PATH=/path/to/vault \\
  OMNI_ENGINE_URL=http://127.0.0.1:8765 \\
  python engine/mcp_server.py --transport http --port 8766
"""

import argparse
import json
import os
import sys
import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

# Optional HTTP transport deps — imported at module level so FastAPI can
# resolve all type annotations properly (local imports break Pydantic forward refs).
try:
    from fastapi import FastAPI, Request, HTTPException
    from fastapi.responses import JSONResponse
    import uvicorn
    _HTTP_TRANSPORT_AVAILABLE = True
except ImportError:
    _HTTP_TRANSPORT_AVAILABLE = False

sys.path.insert(0, str(Path(__file__).parent))
from memory_classifier import classify, write_to_tier, MemoryTier
from context_state import (
    ACTIVE_CONTEXT_PATH,
    FRESHNESS_PATH,
    SESSION_HANDOFF_PATH,
    ensure_state_files,
    read_handoff,
    read_working_set,
    record_handoff as write_session_handoff,
    refresh_freshness_report,
    update_working_set as write_working_set,
    verify_vault_file as mark_vault_file_verified,
)

# ─── Config ───────────────────────────────────────────────────────────────────

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "command-center"
from __version__ import __version__ as SERVER_VERSION

ENGINE_URL = os.environ.get("OMNI_ENGINE_URL", "http://127.0.0.1:8765")
ENGINE_API_KEY = os.environ.get("OMNI_API_KEY", "")
VAULT_PATH = Path(os.environ.get("OMNI_VAULT_PATH", Path(__file__).parent.parent / "vault"))
SKILL_PATHS_ENV = os.environ.get("OMNI_SKILL_PATHS", "")

# Bearer token protecting the HTTP MCP endpoint (separate from the engine key)
MCP_KEY = os.environ.get("OMNI_MCP_KEY", "")
MCP_DEFAULT_PORT = int(os.environ.get("OMNI_MCP_PORT", "8766"))

# ─── Tools ────────────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "search_memory",
        "description": (
            "Semantic search across the entire knowledge vault. "
            "Returns relevant context: preferences, decisions, project state, notes. "
            "Call this at the START of any session to load relevant context, "
            "and whenever you need to recall something."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for or recall"
                },
                "k": {
                    "type": "integer",
                    "description": "Number of results (default: 5, max: 20)",
                    "default": 5
                },
                "namespace": {
                    "type": "string",
                    "description": "Optional: filter to a namespace (e.g. 'company_core', 'knowledge', 'projects')"
                },
                "agent_id": {
                    "type": "string",
                    "description": "Optional: include this agent's private memory in the search alongside shared vault (e.g. 'claude', 'grok', 'gemini')"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "store",
        "description": (
            "Store something worth remembering. "
            "The engine automatically decides if this is cache (session noise), "
            "short-term (project/task state), or long-term (preference/decision). "
            "You don't need to classify it — just pass the content. "
            "Call this when you learn something the user would want recalled in future sessions. "
            "Pass agent_id to write to that agent's private memory space instead of the shared vault."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The fact, preference, decision, or context to store"
                },
                "source": {
                    "type": "string",
                    "description": "Where this came from (e.g. 'conversation', 'user_stated', 'inferred')",
                    "default": "conversation"
                },
                "agent_id": {
                    "type": "string",
                    "description": "Optional: store in this agent's private namespace instead of shared vault (e.g. 'claude', 'grok', 'gemini')"
                }
            },
            "required": ["content"]
        }
    },
    {
        "name": "read_vault_file",
        "description": "Read a specific file from the vault. Useful for loading identity files or project notes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path within vault (e.g. 'Core/USER.md', 'Archive/MEMORY.md')"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "list_vault",
        "description": "List markdown files in a vault directory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Subdirectory to list (e.g. 'Core', 'Archive', 'Knowledge'). Empty for root.",
                    "default": ""
                }
            }
        }
    },
    {
        "name": "migrate_history",
        "description": (
            "Parse an AI provider export and write a full project history analysis "
            "to vault/Migration/. Supports ChatGPT, Claude, and Gemini exports. "
            "Output is gitignored — your data stays local. "
            "Use this when migrating from another AI provider into Command Center."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "export_path": {
                    "type": "string",
                    "description": "Absolute path to the export folder or file"
                },
                "provider": {
                    "type": "string",
                    "enum": ["chatgpt", "claude", "gemini", "auto"],
                    "description": "Export format. Use 'auto' to detect automatically.",
                    "default": "auto"
                },
                "output_name": {
                    "type": "string",
                    "description": "Optional custom output filename (e.g. 'MY_CHATGPT_ANALYSIS.md')"
                }
            },
            "required": ["export_path"]
        }
    },
    {
        "name": "list_skills",
        "description": (
            "List the cross-AI skill catalog aggregated by Command Center. "
            "This includes native vault skills plus external libraries such as ~/.claude/skills."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Optional free-text filter for skill name or description",
                    "default": ""
                },
                "source": {
                    "type": "string",
                    "description": "Optional skill source filter (e.g. 'vault', 'claude')",
                    "default": ""
                },
                "category": {
                    "type": "string",
                    "description": "Optional category filter",
                    "default": ""
                },
                "target": {
                    "type": "string",
                    "description": "Optional target/domain hint (e.g. 'flutter', 'react', 'trading')",
                    "default": ""
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of skills to return (default: 25, max: 100)",
                    "default": 25
                }
            }
        }
    },
    {
        "name": "read_skill",
        "description": (
            "Read the full contents of one registered skill. "
            "Use after list_skills or resolve_skills to load the exact skill instructions."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "skill_id": {
                    "type": "string",
                    "description": "Canonical skill id (for example 'claude:elite-landing-page')"
                },
                "source": {
                    "type": "string",
                    "description": "Optional source override when looking up by name",
                    "default": ""
                },
                "name": {
                    "type": "string",
                    "description": "Optional skill name when skill_id is not known yet",
                    "default": ""
                }
            }
        }
    },
    {
        "name": "resolve_skills",
        "description": (
            "Recommend the most relevant skills for a task, agent, or target stack. "
            "Use this to map skill knowledge onto any AI runtime."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Task description or user request"
                },
                "agent": {
                    "type": "string",
                    "description": "Optional agent/client name (e.g. 'Custom AI', 'Codex', 'Claude')",
                    "default": ""
                },
                "target": {
                    "type": "string",
                    "description": "Optional delivery target (e.g. 'frontend', 'flutter', '3d', 'trading')",
                    "default": ""
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of matches to return (default: 8, max: 20)",
                    "default": 8
                }
            },
            "required": ["task"]
        }
    },
    {
        "name": "bootstrap_agent",
        "description": (
            "Generate a Command Center startup packet for an AI agent. "
            "Returns the core resources to load, the first search to run, the active working set, "
            "and the skills to read. Use this at startup and after compaction."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent": {
                    "type": "string",
                    "description": "Agent or runtime name (e.g. 'Custom AI', 'Claude', 'Codex')"
                },
                "task": {
                    "type": "string",
                    "description": "Optional active task to tailor the bootstrap packet",
                    "default": ""
                },
                "target": {
                    "type": "string",
                    "description": "Optional domain target (e.g. 'frontend', 'flutter', '3d', 'trading')",
                    "default": ""
                },
                "reason": {
                    "type": "string",
                    "description": "Why the bootstrap is being requested (e.g. 'startup', 'compact_recovery', 'handoff')",
                    "default": "startup"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum recommended skills to include (default: 6, max: 12)",
                    "default": 6
                },
                "agent_id": {
                    "type": "string",
                    "description": "Optional: include this agent's private context files in the boot packet alongside shared vault resources",
                    "default": ""
                }
            },
            "required": ["agent"]
        }
    },
    {
        "name": "update_working_set",
        "description": (
            "Update the canonical active working set. "
            "Use this after major strategy changes, live incidents, or priority shifts so every agent reloads the same state."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Active project name", "default": ""},
                "mission": {"type": "string", "description": "Current mission statement", "default": ""},
                "summary": {"type": "string", "description": "Current state summary", "default": ""},
                "priorities": {"type": "array", "items": {"type": "string"}, "description": "Ordered current priorities"},
                "constraints": {"type": "array", "items": {"type": "string"}, "description": "Constraints or guardrails"},
                "open_questions": {"type": "array", "items": {"type": "string"}, "description": "Open questions or unresolved decisions"},
                "next_actions": {"type": "array", "items": {"type": "string"}, "description": "Immediate next actions"},
                "files": {"type": "array", "items": {"type": "string"}, "description": "Relevant file paths or systems"},
                "source": {"type": "string", "description": "Who updated the working set", "default": "agent"}
            }
        }
    },
    {
        "name": "record_handoff",
        "description": (
            "Write the latest session handoff snapshot. "
            "Use this before ending a session or after completing a meaningful chunk of work."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Durable handoff summary"},
                "next_actions": {"type": "array", "items": {"type": "string"}, "description": "What should happen next"},
                "changed_files": {"type": "array", "items": {"type": "string"}, "description": "Changed files or systems"},
                "open_questions": {"type": "array", "items": {"type": "string"}, "description": "Open questions that remain"},
                "risks": {"type": "array", "items": {"type": "string"}, "description": "Live risks or caveats"},
                "source": {"type": "string", "description": "Who wrote the handoff", "default": "agent"}
            },
            "required": ["summary"]
        }
    },
    {
        "name": "verify_vault_file",
        "description": (
            "Mark a vault file as freshly verified and attach freshness metadata. "
            "Use this when you confirm a file is current so stale state can be detected later."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path within the vault"},
                "status": {"type": "string", "description": "Declared file status (e.g. 'active', 'deprecated')", "default": "active"},
                "note": {"type": "string", "description": "Optional verification note", "default": ""},
                "review_after_days": {"type": "integer", "description": "Days before this file should be reviewed again"},
                "source": {"type": "string", "description": "Who verified the file", "default": "agent"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "freshness_report",
        "description": (
            "Generate or read the freshness report for the core operating files. "
            "Use this to catch stale identity docs, handoffs, or working state before they drift."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "stale_days": {
                    "type": "integer",
                    "description": "Default review window in days when a file has no explicit metadata",
                    "default": 7
                },
                "write": {
                    "type": "boolean",
                    "description": "Whether to persist the refreshed report to Core/FRESHNESS.md",
                    "default": True
                }
            }
        }
    },
    {
        "name": "sync_skills",
        "description": (
            "Sync vault/Skills/ to all connected AI runtimes (Claude Code, Gemini CLI, Codex, Custom AI). "
            "Vault is the canonical source. Each runtime gets skills in its own native format. "
            "Use this after adding or editing a skill so every AI gets the update automatically. "
            "Set dry_run=true to preview what would be written without making changes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "runtimes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Runtimes to sync (e.g. ['claude', 'gemini']). Default: all registered runtimes.",
                    "default": []
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If true, preview changes without writing files.",
                    "default": False
                },
                "reverse": {
                    "type": "boolean",
                    "description": "If true, import skills FROM runtimes INTO vault (one-way promotion, vault wins on conflicts).",
                    "default": False
                }
            }
        }
    }
]

# ─── Resources (auto-loaded context) ──────────────────────────────────────────

RESOURCES = [
    {
        "uri": "vault://core/soul",
        "name": "AI Soul — Identity & Behavior",
        "description": "Who you are and how to behave. Load every session.",
        "mimeType": "text/markdown"
    },
    {
        "uri": "vault://core/user",
        "name": "User Context",
        "description": "Who you're helping. Load every session.",
        "mimeType": "text/markdown"
    },
    {
        "uri": "vault://core/company-soul",
        "name": "Organization Mission",
        "description": "Company/project mission and operating principles.",
        "mimeType": "text/markdown"
    },
    {
        "uri": "vault://archive/memory",
        "name": "Long-Term Memory",
        "description": "Permanent preferences, decisions, and context accumulated over time.",
        "mimeType": "text/markdown"
    },
    {
        "uri": "vault://core/active-context",
        "name": "Active Context",
        "description": "Current mission, priorities, and constraints. Load on startup and after compaction.",
        "mimeType": "text/markdown"
    },
    {
        "uri": "vault://core/session-handoff",
        "name": "Session Handoff",
        "description": "Latest durable session summary, next actions, and risks.",
        "mimeType": "text/markdown"
    },
    {
        "uri": "vault://core/freshness",
        "name": "Freshness Report",
        "description": "Freshness status for the critical operating files.",
        "mimeType": "text/markdown"
    }
]

RESOURCE_FILE_MAP = {
    "vault://core/soul": "Core/SOUL.md",
    "vault://core/user": "Core/USER.md",
    "vault://core/company-soul": "Core/COMPANY-SOUL.md",
    "vault://archive/memory": "Archive/MEMORY.md",
    "vault://core/active-context": ACTIVE_CONTEXT_PATH,
    "vault://core/session-handoff": SESSION_HANDOFF_PATH,
    "vault://core/freshness": FRESHNESS_PATH,
}

# ─── Helpers ──────────────────────────────────────────────────────────────────

SKILL_EXCLUDE_DIRS = {"assets", "scripts", "references", "eval-viewer", "__pycache__"}
META_TOOL_TRIGGERS = {
    "search_memory",
    "store",
    "read_vault_file",
    "list_vault",
    "migrate_history",
    "list_skills",
    "read_skill",
    "resolve_skills",
    "bootstrap_agent",
    "update_working_set",
    "record_handoff",
    "verify_vault_file",
    "freshness_report",
    "sync_skills",
}
STOPWORDS = {
    "a", "an", "and", "any", "app", "apps", "as", "at", "be", "bot", "build", "for",
    "from", "how", "i", "in", "into", "is", "it", "make", "me", "need", "of", "on",
    "or", "our", "project", "session", "so", "that", "the", "this", "to", "use",
    "want", "we", "with", "you", "your",
}


@dataclass
class SkillRecord:
    skill_id: str
    name: str
    description: str
    source: str
    path: Path
    relative_path: str
    category: str
    trigger: str
    targets: list[str]
    body: str


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _split_path_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(os.pathsep) if item.strip()]


def _parse_listish(value: str) -> list[str]:
    if not value:
        return []
    text = value.strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    return [
        item.strip().strip("\"'")
        for item in text.split(",")
        if item.strip()
    ]


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    metadata: dict[str, str] = {}
    for i in range(1, len(lines)):
        line = lines[i]
        if line.strip() == "---":
            body = "\n".join(lines[i + 1:]).lstrip()
            return metadata, body
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()

    return {}, text


def _skill_roots() -> list[tuple[str, Path]]:
    roots: list[tuple[str, Path]] = [
        ("vault", VAULT_PATH / "Skills"),
        ("claude", Path.home() / ".claude" / "skills"),
    ]
    for idx, raw in enumerate(_split_path_list(SKILL_PATHS_ENV), 1):
        roots.append((f"external{idx}", Path(raw).expanduser()))

    deduped: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for source, root in roots:
        try:
            resolved = str(root.expanduser().resolve())
        except FileNotFoundError:
            resolved = str(root.expanduser())
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append((source, root.expanduser()))
    return deduped


def _is_skill_candidate(path: Path, metadata: dict[str, str]) -> bool:
    if path.suffix.lower() != ".md":
        return False
    if any(part in SKILL_EXCLUDE_DIRS for part in path.parts):
        return False
    if metadata.get("type", "").lower() == "skill":
        return True
    return bool(metadata.get("name") and metadata.get("description"))


def _discover_skills() -> list[SkillRecord]:
    records: list[SkillRecord] = []

    for source, root in _skill_roots():
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.md")):
            try:
                relative = str(path.relative_to(root))
            except ValueError:
                relative = path.name
            if any(part in SKILL_EXCLUDE_DIRS for part in Path(relative).parts[:-1]):
                continue

            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue

            metadata, body = _parse_frontmatter(text)
            if not _is_skill_candidate(path, metadata):
                continue

            name = metadata.get("name", path.stem)
            slug = metadata.get("skill_id", _slugify(name))
            description = metadata.get("description", "").strip()
            category = metadata.get("category", "knowledge").strip() or "knowledge"
            trigger = metadata.get("trigger", "").strip()
            targets = [item.lower() for item in _parse_listish(metadata.get("targets", ""))]

            records.append(
                SkillRecord(
                    skill_id=f"{source}:{slug}",
                    name=name,
                    description=description,
                    source=source,
                    path=path,
                    relative_path=relative,
                    category=category,
                    trigger=trigger,
                    targets=targets,
                    body=body,
                )
            )

    return records


def _find_skill(skill_id: str = "", name: str = "", source: str = "") -> SkillRecord | None:
    source = source.strip().lower()
    name = name.strip().lower()
    skill_id = skill_id.strip().lower()

    for skill in _discover_skills():
        if skill_id and skill.skill_id.lower() == skill_id:
            return skill
        if name and skill.name.lower() == name and (not source or skill.source == source):
            return skill
    return None


def _tokenize(text: str) -> list[str]:
    return [
        token for token in re.findall(r"[a-z0-9][a-z0-9+._-]*", text.lower())
        if len(token) > 1 and token not in STOPWORDS
    ]


def _score_skill(skill: SkillRecord, task: str, agent: str, target: str) -> tuple[int, list[str]]:
    combined = " ".join(
        [
            skill.name,
            skill.description,
            skill.category,
            skill.trigger,
            " ".join(skill.targets),
            skill.body[:6000],
        ]
    ).lower()
    name_desc = f"{skill.name} {skill.description}".lower()
    tokens = list(dict.fromkeys(_tokenize(" ".join([task, agent, target]))))

    score = 0
    matched: list[str] = []
    for token in tokens:
        if token not in combined:
            continue
        matched.append(token)
        score += 5 if token in name_desc else 2
        if token in skill.targets:
            score += 2
        if token == skill.source:
            score += 1

    if target and skill.targets and target.lower() in skill.targets:
        score += 3
    if agent and agent.lower() in combined:
        score += 2

    return score, matched


def _resolve_skill_matches(
    task: str,
    agent: str = "",
    target: str = "",
    limit: int = 8,
) -> list[tuple[SkillRecord, int, list[str]]]:
    scored: list[tuple[SkillRecord, int, list[str]]] = []
    for skill in _discover_skills():
        if skill.trigger in META_TOOL_TRIGGERS:
            continue
        score, matched = _score_skill(skill, task, agent, target)
        if score <= 0:
            continue
        scored.append((skill, score, sorted(set(matched))))

    scored.sort(key=lambda item: (-item[1], item[0].source, item[0].name.lower()))
    return scored[: max(1, min(limit, 20))]

def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if ENGINE_API_KEY:
        h["Authorization"] = f"Bearer {ENGINE_API_KEY}"
    return h


async def _engine_search(
    query: str,
    k: int = 5,
    namespace: str | None = None,
    namespaces: list[str] | None = None,
) -> dict:
    payload: dict = {"query": query, "k": k}
    # namespaces list takes precedence; namespace (singular) is the legacy param
    ns = namespaces or ([namespace] if namespace else None)
    if ns:
        payload["namespaces"] = ns
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{ENGINE_URL}/search", json=payload, headers=_headers())
        resp.raise_for_status()
        return resp.json()


def _read_vault_file(relative_path: str) -> str:
    if relative_path in {ACTIVE_CONTEXT_PATH, SESSION_HANDOFF_PATH, FRESHNESS_PATH}:
        ensure_state_files(VAULT_PATH)
    full_path = (VAULT_PATH / relative_path).resolve()
    if not str(full_path).startswith(str(VAULT_PATH.resolve())):
        raise PermissionError("Path traversal not allowed")
    if not full_path.exists():
        raise FileNotFoundError(f"Not found: {relative_path}")
    return full_path.read_text(encoding="utf-8")


def _list_vault(directory: str = "") -> list[str]:
    target = (VAULT_PATH / directory).resolve() if directory else VAULT_PATH.resolve()
    if not target.exists() or not target.is_dir():
        return []
    return [str(p.relative_to(VAULT_PATH)) for p in sorted(target.rglob("*.md"))]


def _format_skill_summary(
    skill: SkillRecord,
    matched: list[str] | None = None,
    score: int | None = None,
) -> str:
    lines = [
        f"**{skill.skill_id}**",
        f"source: {skill.source}",
        f"name: {skill.name}",
        f"path: {skill.path}",
        f"category: {skill.category}",
    ]
    if skill.trigger:
        lines.append(f"trigger: {skill.trigger}")
    if skill.targets:
        lines.append(f"targets: {', '.join(skill.targets)}")
    if score is not None:
        lines.append(f"score: {score}")
    if matched:
        lines.append(f"matched: {', '.join(matched)}")
    if skill.description:
        lines.append(f"description: {skill.description}")
    return "\n".join(lines)

# ─── Tool Handlers ────────────────────────────────────────────────────────────

async def handle_tool_call(name: str, arguments: dict) -> str:

    if name == "search_memory":
        try:
            # When agent_id is provided, search both the shared vault and the
            # agent's private namespace. The agent sees everything it's allowed
            # to see — shared global memory plus its own private context.
            agent_id = arguments.get("agent_id", "").strip()
            namespace = arguments.get("namespace")
            namespaces = None
            if agent_id:
                private_ns = f"agent_{agent_id.lower().replace(' ', '_')}"
                namespaces = [private_ns] if not namespace else [namespace, private_ns]
            elif namespace:
                namespaces = [namespace]

            result = await _engine_search(
                query=arguments["query"],
                k=arguments.get("k", 5),
                namespaces=namespaces,
            )
            results = result.get("results", [])
            if not results:
                return "No relevant context found in vault."
            parts = []
            for i, r in enumerate(results, 1):
                score = r.get("score", 0)
                source = r.get("source", "unknown")
                text = r.get("text", "").strip()
                parts.append(f"**[{i}] {source}** (score: {score:.2f})\n{text}")
            return "\n\n---\n\n".join(parts)
        except Exception as e:
            return (
                f"Engine not reachable at {ENGINE_URL}.\n"
                f"Start it with: python engine/engine.py --vault ./vault --watch\n"
                f"Error: {e}"
            )

    elif name == "store":
        content = arguments.get("content", "").strip()
        source = arguments.get("source", "conversation")
        agent_id = arguments.get("agent_id", "").strip()
        if not content:
            return "Nothing to store."

        # Agent-private writes go to vault/Agents/{agent_id}/ and are indexed
        # under the agent_{id} namespace — isolated from the shared vault.
        # Shared writes (no agent_id) go through the normal classifier pipeline.
        if agent_id:
            from datetime import datetime as _dt
            safe_id = agent_id.lower().replace(" ", "_")
            agent_dir = VAULT_PATH / "Agents" / safe_id
            agent_dir.mkdir(parents=True, exist_ok=True)
            date_stamp = _dt.utcnow().strftime("%Y-%m-%d")
            target = agent_dir / f"memory-{date_stamp}.md"
            ts = _dt.utcnow().isoformat()
            with target.open("a", encoding="utf-8") as f:
                f.write(f"- [{ts}] [source={source}] — {content}\n")
            try:
                async with httpx.AsyncClient(timeout=3) as client:
                    await client.post(f"{ENGINE_URL}/admin/reindex", headers=_headers())
            except Exception:
                pass
            return (
                f"Stored in **agent private memory** ({safe_id}).\n"
                f"Namespace: agent_{safe_id}\n"
                f"File: Agents/{safe_id}/{target.name}"
            )

        result = classify(content)
        tier = result.tier

        try:
            target = write_to_tier(
                content=content,
                tier=tier,
                vault=VAULT_PATH,
                category=result.category,
                source=source
            )
            try:
                async with httpx.AsyncClient(timeout=3) as client:
                    await client.post(
                        f"{ENGINE_URL}/admin/reindex",
                        headers=_headers()
                    )
            except Exception:
                pass

            tier_label = {
                MemoryTier.CACHE: "cache (clears tonight)",
                MemoryTier.SHORT_TERM: "short-term (30-day TTL)",
                MemoryTier.LONG_TERM: "long-term (permanent)",
            }[tier]

            return (
                f"Stored as **{tier_label}**.\n"
                f"Category: {result.category} (confidence: {result.confidence:.0%})\n"
                f"File: {target.relative_to(VAULT_PATH)}"
            )
        except Exception as e:
            return f"Failed to store: {e}"

    elif name == "read_vault_file":
        try:
            return _read_vault_file(arguments["path"])
        except FileNotFoundError as e:
            return f"File not found: {e}"
        except Exception as e:
            return f"Error: {e}"

    elif name == "list_vault":
        files = _list_vault(arguments.get("directory", ""))
        return "\n".join(files) if files else "No markdown files found."

    elif name == "migrate_history":
        export_path = arguments.get("export_path", "").strip()
        provider = arguments.get("provider", "auto")
        output_name = arguments.get("output_name")

        if not export_path:
            return "export_path is required."

        try:
            repo_root = Path(__file__).parent.parent
            sys.path.insert(0, str(repo_root))

            from migration.classifier import Classifier
            from migration.writer import write_analysis

            if provider == "auto":
                from migration.parsers import auto_detect
                parser = auto_detect(export_path)
                if not parser:
                    return (
                        "Could not auto-detect provider.\n"
                        "Specify provider explicitly: chatgpt, claude, or gemini."
                    )
            else:
                from migration.parsers import PARSERS
                if provider not in PARSERS:
                    return f"Unknown provider: {provider}. Options: chatgpt, claude, gemini, auto"
                parser = PARSERS[provider](export_path)

            summary = parser.parse()
            Classifier().classify_batch(summary.conversations)
            output = write_analysis(summary, VAULT_PATH, output_name)

            from collections import Counter
            cats = Counter(c.category for c in summary.conversations)
            top_cats = "\n".join(
                f"  {count:4d}  {cat}" for cat, count in cats.most_common(5)
            )

            return (
                f"Migration complete.\n"
                f"Provider: {summary.provider}\n"
                f"Conversations: {summary.total}\n"
                f"Date range: {summary.date_range[0]} → {summary.date_range[1]}\n"
                f"Top categories:\n{top_cats}\n"
                f"Output: vault/Migration/{output.name}\n"
                f"Size: {output.stat().st_size // 1024} KB"
            )
        except Exception as e:
            return f"Migration failed: {e}"

    elif name == "list_skills":
        query = arguments.get("query", "").strip().lower()
        source = arguments.get("source", "").strip().lower()
        category = arguments.get("category", "").strip().lower()
        target = arguments.get("target", "").strip().lower()
        limit = max(1, min(int(arguments.get("limit", 25)), 100))

        skills = []
        for skill in _discover_skills():
            if source and skill.source != source:
                continue
            if category and skill.category.lower() != category:
                continue
            if target and target not in " ".join(
                [skill.name, skill.description, " ".join(skill.targets)]
            ).lower():
                continue
            if query:
                haystack = " ".join(
                    [skill.skill_id, skill.name, skill.description, skill.body[:2000]]
                ).lower()
                if query not in haystack:
                    continue
            skills.append(skill)

        if not skills:
            return "No skills matched the filters."

        parts = [_format_skill_summary(skill) for skill in skills[:limit]]
        return f"Registered skills: {len(skills)} match(es)\n\n" + "\n\n---\n\n".join(parts)

    elif name == "read_skill":
        skill = _find_skill(
            skill_id=arguments.get("skill_id", ""),
            name=arguments.get("name", ""),
            source=arguments.get("source", ""),
        )
        if not skill:
            return "Skill not found. Use list_skills first."
        return (
            f"# {skill.name}\n\n"
            f"- skill_id: `{skill.skill_id}`\n"
            f"- source: `{skill.source}`\n"
            f"- path: `{skill.path}`\n"
            f"- category: `{skill.category}`\n"
            f"- trigger: `{skill.trigger or 'n/a'}`\n"
            f"- targets: `{', '.join(skill.targets) if skill.targets else 'n/a'}`\n\n"
            f"{skill.body}"
        )

    elif name == "resolve_skills":
        task = arguments.get("task", "").strip()
        agent = arguments.get("agent", "").strip()
        target = arguments.get("target", "").strip()
        limit = max(1, min(int(arguments.get("limit", 8)), 20))

        matches = _resolve_skill_matches(task=task, agent=agent, target=target, limit=limit)
        if not matches:
            return "No relevant skills matched. Try list_skills with a broader query."

        parts = [
            _format_skill_summary(skill, matched=matched, score=score)
            for skill, score, matched in matches
        ]
        return (
            f"Recommended skills for task: {task}\n"
            f"agent: {agent or 'n/a'}\n"
            f"target: {target or 'n/a'}\n\n"
            + "\n\n---\n\n".join(parts)
        )

    elif name == "bootstrap_agent":
        agent = arguments.get("agent", "").strip()
        task = arguments.get("task", "").strip()
        target = arguments.get("target", "").strip()
        reason = arguments.get("reason", "startup").strip() or "startup"
        limit = max(1, min(int(arguments.get("limit", 6)), 12))
        agent_id = arguments.get("agent_id", "").strip()

        ensure_state_files(VAULT_PATH)
        working_set = read_working_set(VAULT_PATH)
        handoff = read_handoff(VAULT_PATH)
        freshness = refresh_freshness_report(VAULT_PATH, write=False)
        stale_entries = [item for item in freshness["entries"] if item["freshness"] != "fresh"]

        effective_task = task or working_set["mission"] or working_set["summary"] or agent
        matches = _resolve_skill_matches(task=effective_task, agent=agent, target=target, limit=limit)
        skill_lines = []
        for skill, score, matched in matches:
            skill_lines.append(
                f"- {skill.skill_id} ({skill.source})"
                f" — score {score}, matched: {', '.join(matched) if matched else 'general'}"
            )

        search_query = " | ".join(part for part in [effective_task, target, agent] if part).strip() or agent
        priority_lines = "\n".join(f"- {item}" for item in working_set["priorities"]) or "- No priorities set."
        next_action_lines = "\n".join(f"- {item}" for item in handoff["next_actions"]) or "- No next actions recorded."
        stale_lines = "\n".join(
            f"- {item['path']} — {item['freshness']} ({item['notes']})"
            for item in stale_entries[:8]
        ) or "- No stale core files detected."

        # If the agent has a private namespace, surface its memory files too.
        agent_private_section = ""
        if agent_id:
            safe_id = agent_id.lower().replace(" ", "_")
            agent_dir = VAULT_PATH / "Agents" / safe_id
            if agent_dir.exists():
                private_files = sorted(agent_dir.glob("*.md"))
                if private_files:
                    file_lines = "\n".join(f"- Agents/{safe_id}/{p.name}" for p in private_files[-5:])
                    agent_private_section = (
                        f"\n## Agent Private Context ({safe_id})\n"
                        f"Include these in your load order after shared core files:\n"
                        f"{file_lines}\n"
                    )

        return (
            f"# Command Center Bootstrap\n\n"
            f"agent: {agent}\n"
            f"agent_id: {agent_id or 'shared'}\n"
            f"reason: {reason}\n"
            f"task: {task or effective_task or 'n/a'}\n"
            f"target: {target or 'n/a'}\n\n"
            f"## Load These Resources First\n"
            f"- vault://core/soul\n"
            f"- vault://core/user\n"
            f"- vault://core/company-soul\n"
            f"- vault://core/active-context\n"
            f"- vault://core/session-handoff\n"
            f"- vault://core/freshness\n"
            f"- vault://archive/memory\n\n"
            f"## Working Set Snapshot\n"
            f"- active_project: {working_set['metadata'].get('active_project', 'n/a') or 'n/a'}\n"
            f"- mission: {working_set['mission'] or 'n/a'}\n"
            f"- summary: {working_set['summary'] or 'n/a'}\n\n"
            f"### Current Priorities\n"
            f"{priority_lines}\n\n"
            f"### Next Actions\n"
            f"{next_action_lines}\n\n"
            f"## First Memory Search\n"
            f"- search_memory(query=\"{search_query}\")\n\n"
            f"## Recommended Skills\n"
            f"{chr(10).join(skill_lines) if skill_lines else '- No direct skill matches found yet.'}\n\n"
            f"## Freshness Warnings\n"
            f"{stale_lines}\n\n"
            f"## Operating Order\n"
            f"1. Read the core identity files plus active-context, session-handoff, and freshness.\n"
            f"2. Run the first memory search.\n"
            f"3. Call read_skill() on each recommended skill before planning.\n"
            f"4. If this is a post-compact recovery, trust the working set and handoff before old chat fragments.\n"
            f"5. Store durable preferences with store(), update_working_set(), record_handoff(), or verify_vault_file()."
            + agent_private_section
        )

    elif name == "update_working_set":
        try:
            path = write_working_set(
                VAULT_PATH,
                project=arguments.get("project", ""),
                mission=arguments.get("mission", ""),
                summary=arguments.get("summary", ""),
                priorities=arguments.get("priorities"),
                constraints=arguments.get("constraints"),
                open_questions=arguments.get("open_questions"),
                next_actions=arguments.get("next_actions"),
                files=arguments.get("files"),
                source=arguments.get("source", "agent"),
            )
            return (
                "Updated active working set.\n"
                f"File: {path.relative_to(VAULT_PATH)}\n\n"
                f"{_read_vault_file(ACTIVE_CONTEXT_PATH)}"
            )
        except Exception as e:
            return f"Failed to update working set: {e}"

    elif name == "record_handoff":
        try:
            path = write_session_handoff(
                VAULT_PATH,
                summary=arguments.get("summary", ""),
                next_actions=arguments.get("next_actions"),
                changed_files=arguments.get("changed_files"),
                open_questions=arguments.get("open_questions"),
                risks=arguments.get("risks"),
                source=arguments.get("source", "agent"),
            )
            return (
                "Recorded session handoff.\n"
                f"File: {path.relative_to(VAULT_PATH)}\n\n"
                f"{_read_vault_file(SESSION_HANDOFF_PATH)}"
            )
        except Exception as e:
            return f"Failed to record handoff: {e}"

    elif name == "verify_vault_file":
        try:
            path = mark_vault_file_verified(
                VAULT_PATH,
                relative_path=arguments.get("path", ""),
                status=arguments.get("status", "active"),
                note=arguments.get("note", ""),
                review_after_days=arguments.get("review_after_days"),
                source=arguments.get("source", "agent"),
            )
            return (
                "Verified vault file freshness.\n"
                f"File: {path.relative_to(VAULT_PATH)}"
            )
        except FileNotFoundError as e:
            return f"File not found: {e}"
        except Exception as e:
            return f"Failed to verify vault file: {e}"

    elif name == "freshness_report":
        try:
            report = refresh_freshness_report(
                VAULT_PATH,
                stale_days=max(1, int(arguments.get("stale_days", 7))),
                write=bool(arguments.get("write", True)),
            )
            counts = report["counts"]
            return (
                f"Freshness report generated.\n"
                f"fresh={counts['fresh']} stale={counts['stale']} missing={counts['missing']}\n\n"
                f"{report['markdown']}"
            )
        except Exception as e:
            return f"Failed to generate freshness report: {e}"

    elif name == "sync_skills":
        try:
            from engine.skill_adapter import sync_skills, import_from_runtimes, ADAPTERS
            runtimes_arg = arguments.get("runtimes") or []
            runtimes = [r for r in runtimes_arg if r in ADAPTERS] or None
            dry_run = bool(arguments.get("dry_run", False))
            reverse = bool(arguments.get("reverse", False))

            if reverse:
                results = import_from_runtimes(
                    runtimes=runtimes,
                    vault_skills_path=VAULT_PATH / "Skills",
                    dry_run=dry_run,
                    verbose=False,
                )
                lines = ["Imported skills from runtimes into vault/Skills/\n"]
            else:
                results = sync_skills(
                    runtimes=runtimes,
                    source=VAULT_PATH / "Skills",
                    dry_run=dry_run,
                    verbose=False,
                )
                lines = [f"{'[DRY RUN] ' if dry_run else ''}Skill sync complete\n"]

            for runtime, runtime_results in results.items():
                written = sum(1 for r in runtime_results if r.action == "write")
                unchanged = sum(1 for r in runtime_results if r.action == "unchanged")
                dry = sum(1 for r in runtime_results if r.action == "dry_run")
                errors = [r for r in runtime_results if r.action == "error"]
                parts = []
                if dry_run:
                    parts.append(f"{dry} would write")
                else:
                    parts.append(f"{written} written, {unchanged} unchanged")
                if errors:
                    parts.append(f"{len(errors)} errors")
                lines.append(f"  {runtime}: {', '.join(parts)}")
                for e in errors:
                    lines.append(f"    ERROR {e.skill_slug}: {e.error}")

            return "\n".join(lines)
        except Exception as e:
            return f"Failed to sync skills: {e}"

    return f"Unknown tool: {name}"

# ─── Resource Handler ─────────────────────────────────────────────────────────

async def handle_resource_read(uri: str) -> str:
    relative = RESOURCE_FILE_MAP.get(uri)
    if not relative:
        raise ValueError(f"Unknown resource: {uri}")
    try:
        return _read_vault_file(relative)
    except FileNotFoundError:
        return f"# Not configured yet\n\nFill in `vault/{relative}` with your details."

# ─── Shared JSON-RPC Handler ──────────────────────────────────────────────────

async def handle_jsonrpc(request: dict) -> dict | None:
    """Process one MCP JSON-RPC message. Returns response dict or None (for notifications)."""
    req_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION}
            }
        }

    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

    elif method == "tools/call":
        result_text = await handle_tool_call(
            params.get("name", ""),
            params.get("arguments", {})
        )
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "content": [{"type": "text", "text": result_text}],
                "isError": False
            }
        }

    elif method == "resources/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"resources": RESOURCES}}

    elif method == "resources/read":
        uri = params.get("uri", "")
        try:
            content = await handle_resource_read(uri)
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "contents": [{"uri": uri, "mimeType": "text/markdown", "text": content}]
                }
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32600, "message": str(e)}
            }

    elif method == "notifications/initialized":
        return None  # No response for notifications

    else:
        return {
            "jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        }

# ─── Transport: stdio ─────────────────────────────────────────────────────────

async def run_stdio() -> None:
    """Local transport. Claude Code / Claude Desktop spawns this as a child process."""
    while True:
        try:
            line = sys.stdin.readline()
        except EOFError:
            break
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        response = await handle_jsonrpc(request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

# ─── Transport: Streamable HTTP ───────────────────────────────────────────────

async def run_http(port: int) -> None:
    """
    Network transport — MCP over HTTP (Streamable HTTP, MCP spec 2025-03-26).

    Run this on a NAS or server. Any AI on your LAN connects via URL.
    Protect with OMNI_MCP_KEY env var (Bearer token).

    Why this exists:
      stdio requires the MCP server to run on the same machine as the AI client.
      HTTP lets one Command Center instance serve every machine on your network.
      One vault. One memory. Accessible from laptop, desktop, and agents alike.
    """
    if not _HTTP_TRANSPORT_AVAILABLE:
        print(
            "ERROR: HTTP transport requires fastapi and uvicorn.\n"
            "Install with: pip install fastapi uvicorn",
            file=sys.stderr
        )
        sys.exit(1)

    app = FastAPI(title="Command Center MCP", version=SERVER_VERSION)

    def _verify_auth(authorization: str | None) -> None:
        """Enforce Bearer token when OMNI_MCP_KEY is set. Open mode if not set."""
        if not MCP_KEY:
            return  # No key configured — open mode (local network only, no internet)
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Authorization header required")
        if authorization[len("Bearer "):] != MCP_KEY:
            raise HTTPException(status_code=403, detail="Invalid token")

    @app.post("/mcp")
    async def mcp_endpoint(request: Request) -> JSONResponse:
        _verify_auth(request.headers.get("Authorization"))
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")

        response = await handle_jsonrpc(body)
        if response is None:
            return JSONResponse({})
        return JSONResponse(response)

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok", "server": SERVER_NAME, "version": SERVER_VERSION})

    print(f"Command Center MCP — HTTP transport")
    print(f"Listening on http://0.0.0.0:{port}/mcp")
    print(f"Auth: {'enabled (OMNI_MCP_KEY set)' if MCP_KEY else 'OPEN — set OMNI_MCP_KEY to secure'}")
    print(f"Vault: {VAULT_PATH}")
    print(f"Engine: {ENGINE_URL}")

    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()

# ─── Entry Point ──────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(description="Command Center MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="stdio (default, local) or http (network/NAS)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=MCP_DEFAULT_PORT,
        help=f"Port for HTTP transport (default: {MCP_DEFAULT_PORT})"
    )
    args = parser.parse_args()

    if args.transport == "http":
        await run_http(args.port)
    else:
        await run_stdio()


if __name__ == "__main__":
    asyncio.run(main())
