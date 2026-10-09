# QueueLens MCP Server

Implemented: a local **stdio MCP server** exposing the same eight read-only GIS tools as `/api/tools/catalog`. Python uses the official MCP SDK 1.x maintenance line (`mcp>=1.28,<2`); the protocol layer contains no GIS calculations or SQL. See the [official low-level server documentation](https://github.com/modelcontextprotocol/python-sdk/blob/v1.x/docs/low-level-server.md).

```text
QueueLens Agent ── ToolClient ─┐
                              ├─ Express typed tools ─ domain/store ─ PostGIS
External MCP client ─ stdio ───┘
```

## Run

Start the existing Node API, then install `python -m pip install -r mcp/requirements.txt` and run `python mcp/server.py` from the repository. Set `GIS_API_URL` to the trusted Node URL and `GIS_TOOLS_TOKEN` if the API requires authentication. Do not log to stdout; stdout carries the MCP protocol.

Example client configuration (replace executable/path with your environment):

```json
{
  "mcpServers": {
    "queuelens": {
      "command": "/absolute/path/to/python",
      "args": ["/absolute/path/to/Hospital-queue-webgis/mcp/server.py"],
      "env": {"GIS_API_URL": "http://127.0.0.1:3000"}
    }
  }
}
```

## Contracts and limits

- Input schemas come directly from the Express catalog. Structured outputs retain the tool name, original arguments, data, evidence, and warnings.
- ToolClient validates inputs and outputs against those schemas. Express validates again and executes parameterized queries.
- No write tool, arbitrary URL tool, or arbitrary SQL tool is exposed. Hospital names and cleanliness notes remain data, never instructions.
- Four calls may execute concurrently; each call has an eight-second total deadline and five-second HTTP timeout. Upstream errors become `isError` results without database details or credentials.
- SDK tool annotations declare read-only, non-destructive behavior. Transport credentials are configured by the operator, never accepted from a model argument.

## Verification

`agent-service/tests/test_mcp.py` starts an actual stdio server, performs initialize/list/call through the SDK client, checks all eight calls against the real Node API, and rejects invalid coordinates and non-allowlisted SQL calls.

Remote Streamable HTTP hosting and OAuth are future work. Do not publish this stdio bridge as an unauthenticated network service.
