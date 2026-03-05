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

from __future__ import annotations

import argparse
import json
import os
import sys
import asyncio
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from memory_classifier import classify, write_to_tier, MemoryTier

# ─── Config ───────────────────────────────────────────────────────────────────

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "command-center"
SERVER_VERSION = "1.2.0"

ENGINE_URL = os.environ.get("OMNI_ENGINE_URL", "http://127.0.0.1:8765")
ENGINE_API_KEY = os.environ.get("OMNI_API_KEY", "")
VAULT_PATH = Path(os.environ.get("OMNI_VAULT_PATH", Path(__file__).parent.parent / "vault"))

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
            "Call this when you learn something the user would want recalled in future sessions."
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
    }
]

RESOURCE_FILE_MAP = {
    "vault://core/soul": "Core/SOUL.md",
    "vault://core/user": "Core/USER.md",
    "vault://core/company-soul": "Core/COMPANY-SOUL.md",
    "vault://archive/memory": "Archive/MEMORY.md",
}

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if ENGINE_API_KEY:
        h["Authorization"] = f"Bearer {ENGINE_API_KEY}"
    return h


async def _engine_search(query: str, k: int = 5, namespace: str | None = None) -> dict:
    payload: dict = {"query": query, "k": k}
    if namespace:
        payload["namespaces"] = [namespace]
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{ENGINE_URL}/search", json=payload, headers=_headers())
        resp.raise_for_status()
        return resp.json()


def _read_vault_file(relative_path: str) -> str:
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

# ─── Tool Handlers ────────────────────────────────────────────────────────────

async def handle_tool_call(name: str, arguments: dict) -> str:

    if name == "search_memory":
        try:
            result = await _engine_search(
                query=arguments["query"],
                k=arguments.get("k", 5),
                namespace=arguments.get("namespace")
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
        if not content:
            return "Nothing to store."

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
    try:
        from fastapi import FastAPI, Request, HTTPException
        from fastapi.responses import JSONResponse
        import uvicorn
    except ImportError:
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
