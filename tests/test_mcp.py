
"""Tests for the Company Brain MCP server."""

import asyncio
import json

from app.mcp_server import (
    call_tool,
    get_document,
    list_tools,
    search_knowledge,
)


def configure_role(monkeypatch, role="employee"):
    """Configure the trusted server-side MCP role for a test."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "MCP_DEFAULT_ROLE", role)


def test_mcp_search_knowledge_authorized(
    temp_environment, monkeypatch
):
    """Employee search returns accessible documents."""
    configure_role(monkeypatch, "employee")

    monkeypatch.setattr(
        "app.mcp_server.get_knowledge_service",
        lambda: temp_environment["knowledge_service"],
    )

    raw_result = search_knowledge(
        query="laptop maintenance",
        limit=5,
    )
    result = json.loads(raw_result)

    assert "error" not in result
    assert result["role_applied"] == "employee"
    assert result["total_results"] >= 1


def test_mcp_search_knowledge_unauthorized_filter(
    temp_environment, monkeypatch
):
    """Employee search excludes restricted treasury documents."""
    configure_role(monkeypatch, "employee")

    monkeypatch.setattr(
        "app.mcp_server.get_knowledge_service",
        lambda: temp_environment["knowledge_service"],
    )

    raw_result = search_knowledge(
        query="treasury bills reserves",
        limit=5,
    )
    result = json.loads(raw_result)

    assert result["role_applied"] == "employee"
    assert all(
        item["document_id"] != "NEX-TEST-002"
        for item in result["results"]
    )


def test_mcp_get_document_authorized_vs_unauthorized(
    temp_environment, monkeypatch
):
    """Document retrieval respects the configured MCP role."""
    configure_role(monkeypatch, "employee")

    monkeypatch.setattr(
        "app.mcp_server.get_knowledge_service",
        lambda: temp_environment["knowledge_service"],
    )

    authorized_result = get_document("NEX-TEST-001")

    assert "NEX-TEST-001" in authorized_result
    assert "ACCESS DENIED" not in authorized_result

    restricted_result = get_document("NEX-TEST-002")

    assert "ACCESS DENIED" in restricted_result


def test_mcp_invalid_inputs(temp_environment, monkeypatch):
    """Invalid queries, document IDs, and role configuration are handled."""
    configure_role(monkeypatch, "employee")

    monkeypatch.setattr(
        "app.mcp_server.get_knowledge_service",
        lambda: temp_environment["knowledge_service"],
    )

    empty_query_result = json.loads(
        search_knowledge(query="   ")
    )
    assert "error" in empty_query_result

    empty_document_result = get_document("   ")
    assert "required" in empty_document_result.lower()

    configure_role(monkeypatch, "super_hacker")

    invalid_role_search = json.loads(
        search_knowledge(query="hello")
    )
    assert "error" in invalid_role_search

    invalid_role_document = get_document("NEX-TEST-001")
    assert "configuration is invalid" in invalid_role_document.lower()


def test_mcp_tool_schemas_do_not_expose_role():
    """MCP tool schemas must not allow callers to select their role."""
    tools = asyncio.run(list_tools())

    assert len(tools) == 2

    for tool in tools:
        properties = tool.inputSchema.get("properties", {})
        assert "role" not in properties


def test_mcp_dispatch_ignores_supplied_role(
    temp_environment, monkeypatch
):
    """A caller-supplied admin role must not elevate employee access."""
    configure_role(monkeypatch, "employee")

    monkeypatch.setattr(
        "app.mcp_server.get_knowledge_service",
        lambda: temp_environment["knowledge_service"],
    )

    result = asyncio.run(
        call_tool(
            "search_knowledge",
            {
                "query": "treasury bills reserves",
                "role": "admin",
                "limit": 5,
            },
        )
    )

    payload = json.loads(result[0].text)

    assert payload["role_applied"] == "employee"
    assert all(
        item["document_id"] != "NEX-TEST-002"
        for item in payload["results"]
    )


def test_mcp_dispatch_unknown_tool():
    """Unknown MCP tool names return a structured error."""
    result = asyncio.run(
        call_tool("unknown_tool", {})
    )

    assert len(result) == 1

    payload = json.loads(result[0].text)
    assert "error" in payload
    assert "Unknown tool" in payload["error"]