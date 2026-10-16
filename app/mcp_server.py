
"""Model Context Protocol (MCP) server for Company Brain knowledge retrieval."""

import json
import logging
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from app.config import get_settings
from app.database import init_db
from app.permissions import normalize_role
from app.services import get_knowledge_service

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [MCP Server] %(levelname)s: %(message)s",
)
logger = logging.getLogger("mcp_server")

mcp_server = Server(
    "company-brain-mcp-server",
    instructions=(
        "Nexora Technologies internal knowledge assistant. "
        "Search company policies, engineering standards, product "
        "documentation, and operational procedures with role-based "
        "document filtering. Access is determined by the server's "
        "configured role, not by tool arguments."
    ),
)


def get_mcp_role() -> str:
    """Resolve the role from trusted server configuration."""
    settings = get_settings()
    return normalize_role(settings.MCP_DEFAULT_ROLE).value


def search_knowledge(
    query: str,
    limit: int = 5,
) -> str:
    """Search company knowledge using the server-configured role."""

    clean_query = query.strip() if isinstance(query, str) else ""

    if not clean_query:
        return json.dumps(
            {
                "error": "Query cannot be empty.",
                "role_applied": None,
                "total_results": 0,
                "results": [],
            },
            indent=2,
        )

    try:
        user_role = get_mcp_role()
    except Exception:
        logger.exception("Invalid MCP role configuration")
        return json.dumps(
            {"error": "MCP role configuration is invalid."},
            indent=2,
        )

    try:
        safe_limit = max(1, min(int(limit), 20))
    except (TypeError, ValueError):
        safe_limit = 5

    try:
        knowledge_service = get_knowledge_service()
        response = knowledge_service.search(
            query=clean_query,
            role=user_role,
            limit=safe_limit,
        )

        results_data = [
            {
                "document_id": item.document_id,
                "title": item.title,
                "category": item.category,
                "access_classification": item.access_classification,
                "heading": item.heading,
                "excerpt": item.excerpt.replace("[[", "").replace("]]", ""),
                "relevance_score": item.score,
            }
            for item in response.results
        ]

        return json.dumps(
            {
                "query": clean_query,
                "role_applied": response.role_applied,
                "total_results": len(results_data),
                "results": results_data,
            },
            indent=2,
        )

    except Exception:
        logger.exception("Knowledge search failed")
        return json.dumps(
            {
                "error": "Knowledge search failed.",
                "role_applied": user_role,
                "total_results": 0,
                "results": [],
            },
            indent=2,
        )


def get_document(document_id: str) -> str:
    """Retrieve a document using the server-configured role."""

    clean_id = document_id.strip() if isinstance(document_id, str) else ""

    if not clean_id:
        return "Error: document_id parameter is required."

    try:
        user_role = get_mcp_role()
    except Exception:
        logger.exception("Invalid MCP role configuration")
        return "Error: MCP role configuration is invalid."

    try:
        knowledge_service = get_knowledge_service()
        doc = knowledge_service.get_document(
            document_id=clean_id,
            role=user_role,
        )

        return (
            f"# {doc.title}\n\n"
            f"- **Document ID**: {doc.id}\n"
            f"- **Category**: {doc.category}\n"
            f"- **Author**: {doc.author}\n"
            f"- **Last Updated**: {doc.last_updated}\n"
            f"- **Version**: {doc.version}\n"
            f"- **Classification**: {doc.access_classification}\n\n"
            f"---\n\n"
            f"{doc.raw_content}"
        )

    except Exception as exc:
        status_code = getattr(exc, "status_code", None)
        detail = getattr(exc, "detail", str(exc))
        detail_text = str(detail)

        is_permission_error = (
            status_code == 403
            or "permission" in detail_text.lower()
            or "insufficient clearance" in detail_text.lower()
            or "access denied" in detail_text.lower()
        )

        if is_permission_error:
            return (
                f"ACCESS DENIED (403): The configured MCP role "
                f"'{user_role}' lacks clearance to view document "
                f"'{clean_id}'."
            )

        if status_code == 404 or "not found" in detail_text.lower():
            return (
                f"NOT FOUND (404): Document '{clean_id}' "
                "was not found in the knowledge repository."
            )

        logger.exception("Document retrieval failed for %s", clean_id)
        return f"Error ({status_code or 500}): Document retrieval failed."


@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    """Expose MCP tools without caller-controlled role parameters."""

    return [
        Tool(
            name="search_knowledge",
            description=(
                "Search company knowledge documents. Results are filtered "
                "using the role configured by the MCP server operator."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The question or terms to search for.",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_document",
            description=(
                "Retrieve a company document if the MCP server's "
                "configured role has sufficient clearance."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {
                        "type": "string",
                        "description": "The document ID to retrieve.",
                    },
                },
                "required": ["document_id"],
            },
        ),
    ]


@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Dispatch MCP tool calls."""

    arguments = arguments or {}

    if name == "search_knowledge":
        result = search_knowledge(
            query=arguments.get("query", ""),
            limit=arguments.get("limit", 5),
        )
        return [TextContent(type="text", text=result)]

    if name == "get_document":
        result = get_document(
            document_id=arguments.get("document_id", ""),
        )
        return [TextContent(type="text", text=result)]

    return [
        TextContent(
            type="text",
            text=json.dumps({"error": f"Unknown tool: {name}"}),
        )
    ]


async def run_server() -> None:
    """Run the MCP server over standard input/output."""

    settings = get_settings()
    init_db(settings.DATABASE_PATH)

    # Validate the configured role before serving any MCP requests.
    try:
        role = get_mcp_role()
    except Exception:
        logger.exception("Invalid MCP_DEFAULT_ROLE configuration")
        raise

    logger.info(
        "Starting Company Brain MCP Server with configured role '%s'",
        role,
    )

    async with stdio_server() as (read_stream, write_stream):
        await mcp_server.run(
            read_stream,
            write_stream,
            mcp_server.create_initialization_options(),
        )


def main() -> None:
    """Application entry point."""

    import asyncio

    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        logger.info("MCP server stopped")


if __name__ == "__main__":
    main()
