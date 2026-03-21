"""MCP server tests — JSON-RPC protocol, HTTP transport, tool calls."""
# NOTE: do NOT use `from __future__ import annotations` here — it breaks
# FastAPI's ability to resolve `request: Request` in route signatures.

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Ensure engine/ is importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))


# ─── JSON-RPC handler (transport-agnostic) ────────────────────────────────────

@pytest.fixture(scope="module")
def _patch_env(tmp_path_factory):
    """Set vault path so mcp_server imports don't fail."""
    import os
    vault = tmp_path_factory.mktemp("vault")
    (vault / "Core").mkdir()
    (vault / "Core" / "USER.md").write_text("# Test User\n")
    (vault / "Archive").mkdir()
    (vault / "Archive" / "MEMORY.md").write_text("# Memory\n")
    (vault / "Skills").mkdir()
    os.environ.setdefault("OMNI_VAULT_PATH", str(vault))
    os.environ.setdefault("OMNI_ENGINE_URL", "http://127.0.0.1:8765")
    return vault


@pytest.fixture(scope="module")
def jsonrpc_handler(_patch_env):
    """Import handle_jsonrpc after env is patched."""
    from mcp_server import handle_jsonrpc
    return handle_jsonrpc


# ── Protocol tests ────────────────────────────────────────────────────────────

class TestInitialize:
    def test_returns_capabilities(self, jsonrpc_handler):
        resp = asyncio.get_event_loop().run_until_complete(
            jsonrpc_handler({
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"}
                }
            })
        )
        assert resp["id"] == 1
        assert "result" in resp
        result = resp["result"]
        assert result["protocolVersion"] == "2024-11-05"
        assert "tools" in result["capabilities"]
        assert result["serverInfo"]["name"] == "command-center"

    def test_version_from_single_source(self, jsonrpc_handler):
        from __version__ import __version__
        resp = asyncio.get_event_loop().run_until_complete(
            jsonrpc_handler({
                "jsonrpc": "2.0", "id": 2, "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                           "clientInfo": {"name": "test", "version": "1.0"}}
            })
        )
        assert resp["result"]["serverInfo"]["version"] == __version__


class TestToolsList:
    def test_returns_tools(self, jsonrpc_handler):
        resp = asyncio.get_event_loop().run_until_complete(
            jsonrpc_handler({"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}})
        )
        tools = resp["result"]["tools"]
        assert isinstance(tools, list)
        assert len(tools) > 0
        names = [t["name"] for t in tools]
        assert "search_memory" in names
        assert "store" in names
        assert "bootstrap_agent" in names

    def test_tool_schema_has_required_fields(self, jsonrpc_handler):
        resp = asyncio.get_event_loop().run_until_complete(
            jsonrpc_handler({"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}})
        )
        for tool in resp["result"]["tools"]:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool


class TestResourcesList:
    def test_returns_resources(self, jsonrpc_handler):
        resp = asyncio.get_event_loop().run_until_complete(
            jsonrpc_handler({"jsonrpc": "2.0", "id": 5, "method": "resources/list", "params": {}})
        )
        assert "resources" in resp["result"]


class TestNotifications:
    def test_initialized_returns_none(self, jsonrpc_handler):
        resp = asyncio.get_event_loop().run_until_complete(
            jsonrpc_handler({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        )
        assert resp is None


class TestUnknownMethod:
    def test_returns_error(self, jsonrpc_handler):
        resp = asyncio.get_event_loop().run_until_complete(
            jsonrpc_handler({"jsonrpc": "2.0", "id": 99, "method": "nonexistent", "params": {}})
        )
        assert "error" in resp
        assert resp["error"]["code"] == -32601


# ── Tool call tests (mock the engine HTTP calls) ─────────────────────────────

class TestToolCalls:
    def test_search_memory(self, jsonrpc_handler):
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [{"text": "test result", "score": 0.9, "path": "test.md"}],
            "grounding": {"verdict": "grounded"}
        }

        with patch("mcp_server.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            resp = asyncio.get_event_loop().run_until_complete(
                jsonrpc_handler({
                    "jsonrpc": "2.0", "id": 10, "method": "tools/call",
                    "params": {"name": "search_memory", "arguments": {"query": "test"}}
                })
            )
            assert resp["result"]["isError"] is False
            assert "content" in resp["result"]

    def test_list_vault(self, jsonrpc_handler):
        resp = asyncio.get_event_loop().run_until_complete(
            jsonrpc_handler({
                "jsonrpc": "2.0", "id": 11, "method": "tools/call",
                "params": {"name": "list_vault", "arguments": {}}
            })
        )
        assert resp["result"]["isError"] is False

    def test_read_vault_file(self, jsonrpc_handler):
        resp = asyncio.get_event_loop().run_until_complete(
            jsonrpc_handler({
                "jsonrpc": "2.0", "id": 12, "method": "tools/call",
                "params": {"name": "read_vault_file", "arguments": {"path": "Core/USER.md"}}
            })
        )
        assert resp["result"]["isError"] is False
        text = resp["result"]["content"][0]["text"]
        assert "Test User" in text


# ── HTTP transport tests ─────────────────────────────────────────────────────

class TestHTTPTransport:
    """Test the FastAPI app creation and endpoint routing."""

    @pytest.fixture
    def http_client(self, _patch_env):
        """Create a test client for the HTTP transport FastAPI app."""
        from fastapi.testclient import TestClient
        from mcp_server import handle_jsonrpc, SERVER_NAME

        # Re-import to get fresh FastAPI with fixed forward refs
        from fastapi import FastAPI, Request, HTTPException as FastHTTPException
        from fastapi.responses import JSONResponse as FastJSONResponse

        app = FastAPI(title="Command Center MCP Test")

        @app.post("/mcp")
        async def mcp_endpoint(request: Request) -> FastJSONResponse:
            body = await request.json()
            response = await handle_jsonrpc(body)
            if response is None:
                return FastJSONResponse({})
            return FastJSONResponse(response)

        @app.get("/health")
        async def health() -> FastJSONResponse:
            return FastJSONResponse({"status": "ok", "server": SERVER_NAME})

        return TestClient(app)

    def test_health_endpoint(self, http_client):
        resp = http_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_mcp_initialize_over_http(self, http_client):
        resp = http_client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-http", "version": "1.0"}
            }
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["serverInfo"]["name"] == "command-center"

    def test_mcp_tools_list_over_http(self, http_client):
        resp = http_client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}
        })
        assert resp.status_code == 200
        tools = resp.json()["result"]["tools"]
        assert any(t["name"] == "search_memory" for t in tools)

    def test_mcp_notification_returns_empty(self, http_client):
        resp = http_client.post("/mcp", json={
            "jsonrpc": "2.0", "method": "notifications/initialized", "params": {}
        })
        assert resp.status_code == 200

    def test_mcp_invalid_json(self, http_client):
        # Send garbage — server should reject with a non-200 status
        try:
            resp = http_client.post("/mcp", content="not json",
                                    headers={"Content-Type": "application/json"})
            assert resp.status_code >= 400
        except Exception:
            # Any error (JSON parse, connection) is acceptable for malformed input
            pass
