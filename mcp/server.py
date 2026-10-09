"""QueueLens stdio MCP bridge. All GIS business logic lives in Express/PostGIS."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent-service"))

from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, ToolAnnotations, TextContent, CallToolResult
from app.tools import ToolClient
from app.schemas import AgentFailure


def build_server(client=None):
    client = client or ToolClient()
    server = Server("QueueLens Spatial Tools", version="1.0.0")
    slots = asyncio.Semaphore(4)

    @server.list_tools()
    async def list_tools():
        catalog = await client.load_catalog()
        return [Tool(
            name=tool["name"], description=tool["description"],
            inputSchema=tool["input_schema"],
            outputSchema={"type":"object","required":["version","tool","arguments","data","evidence","warnings"],
                "properties":{"version":{"const":"1.0"},"tool":{"const":tool["name"]},
                    "arguments":tool["input_schema"],"data":tool["output_schema"],
                    "evidence":{"type":"object"},"warnings":{"type":"array","items":{"type":"string"}}},
                "additionalProperties":False},
            annotations=ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=True,openWorldHint=False)
        ) for tool in catalog["tools"]]

    @server.call_tool()
    async def call_tool(name, arguments):
        try:
            async with slots:
                return await asyncio.wait_for(client.call(name,arguments), timeout=8)
        except AgentFailure as error:
            problem={"code":error.code,"message":error.message}
        except asyncio.TimeoutError:
            problem={"code":"tool_timeout","message":"GIS tool exceeded eight seconds"}
        except Exception:
            problem={"code":"tool_execution_failure","message":"GIS service unavailable or returned invalid data"}
        return CallToolResult(isError=True,content=[TextContent(type="text",text=json.dumps(problem))])

    return server


async def main():
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream,write_stream,server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
