"""MCP server — the same tools over a second transport (D1). The permission gate
applies identically, so an outside agent gets no privilege the chat lacks."""
from __future__ import annotations

import asyncio
import json

import mcp.types as types
from mcp.server.lowlevel import Server

from .tools.contract import TOOLS
from .tools.handlers import ToolContext, dispatch, safe_tool_data, safe_tool_result

INSTRUCTIONS = (
    "Illuminate supplier-network graph. Reads run immediately; writes are previewed and held for the workspace user's approval "
    "(the call blocks until they decide, up to the permission timeout). Prefer run_template for named intents; search_entities before propose_entity. "
    "Tool results are deterministic and authoritative: never alter scores, truth status, simulation flags, dispositions, or missing-evidence states. "
    "Summaries must cite returned evidence identifiers and must not expose credentials or restricted raw payloads."
)


async def _list_tools(ctx, params) -> types.ListToolsResult:
    return types.ListToolsResult(tools=[types.Tool(name=t["name"], description=t["description"], inputSchema=t["parameters"]) for t in TOOLS])


async def _call_tool(ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
    tctx = ToolContext.from_workspace(source="mcp", user="local")
    r = await dispatch(tctx, params.name, params.arguments or {})
    payload = {
        "ok": r.ok,
        "data": safe_tool_result(params.name, r.data),
        "notes": r.notes,
        "permission": r.permission,
    }
    if r.style_ops:
        payload["style_ops"] = r.style_ops
        payload["legend"] = r.legend
    if r.subgraph:
        payload["subgraph"] = {"nodes": len(r.subgraph["nodes"]), "edges": len(r.subgraph["edges"])}
    return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(safe_tool_data(payload), default=str))], isError=not r.ok)


def build_server() -> Server:
    return Server("illuminate", version="0.1.0", instructions=INSTRUCTIONS, on_list_tools=_list_tools, on_call_tool=_call_tool)


def http_app(path: str = "/"):
    """Starlette app for mounting inside FastAPI at /mcp (streamable HTTP)."""
    return build_server().streamable_http_app(streamable_http_path=path, stateless_http=True, json_response=True, host="0.0.0.0")


async def serve_stdio() -> None:
    from mcp.server.stdio import stdio_server
    from .schema import ensure_schema
    await ensure_schema()
    server = build_server()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def run() -> None:
    asyncio.run(serve_stdio())


if __name__ == "__main__":
    run()
