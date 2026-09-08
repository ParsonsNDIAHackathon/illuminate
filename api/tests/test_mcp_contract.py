import json

import pytest
from mcp import types

from illuminate import mcp_server
from illuminate.tools.contract import TOOLS
from illuminate.tools.handlers import ToolContext, dispatch


async def test_mcp_publishes_the_shared_tool_contract():
    result = await mcp_server._list_tools(None, None)
    assert [tool.name for tool in result.tools] == [tool["name"] for tool in TOOLS]
    assert [tool.input_schema for tool in result.tools] == [tool["parameters"] for tool in TOOLS]


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("not_a_tool", {}),
        ("search_entities", {}),
        ("get_entity_report", {}),
    ],
)
async def test_malformed_calls_have_dispatch_and_mcp_error_parity(name, arguments):
    direct = await dispatch(
        ToolContext(source="chat", user="local", layers={}, root_id=None),
        name,
        arguments,
    )
    mcp = await mcp_server._call_tool(
        None,
        types.CallToolRequestParams(name=name, arguments=arguments),
    )
    payload = json.loads(mcp.content[0].text)

    assert direct.ok is False
    assert mcp.is_error is True
    assert payload["ok"] is False
    assert payload["data"]["error"] == direct.data["error"]
    assert "Traceback" not in mcp.content[0].text