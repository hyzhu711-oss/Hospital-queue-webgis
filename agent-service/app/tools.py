import json
import os
import httpx
from urllib.parse import urlparse
from jsonschema import Draft7Validator, FormatChecker
from .schemas import AgentFailure


class ToolClient:
    def __init__(self, base_url=None, token=None, transport=None):
        self.base_url = (base_url or os.getenv("GIS_API_URL", "http://127.0.0.1:3000")).rstrip("/")
        self.token = token if token is not None else os.getenv("GIS_TOOLS_TOKEN", "")
        self.transport = transport
        self.catalog = {}

    def client(self):
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        local = urlparse(self.base_url).hostname in ('127.0.0.1', 'localhost', '::1')
        return httpx.AsyncClient(base_url=self.base_url, headers=headers, timeout=5, transport=self.transport, follow_redirects=False, trust_env=not local)

    async def load_catalog(self):
        async with self.client() as client:
            result = await client.get("/api/tools/catalog")
        result.raise_for_status()
        body = result.json()
        if body.get("version") != "1.0":
            raise AgentFailure("tool_execution_failure", "Unsupported GIS tool catalog version")
        self.catalog = {tool["name"]: tool for tool in body["tools"]}
        return body

    async def call(self, name, arguments):
        if not self.catalog:
            await self.load_catalog()
        if name not in self.catalog:
            raise AgentFailure("wrong_tool_selection", "Tool is not in the GIS allowlist")
        tool = self.catalog[name]
        try:
            Draft7Validator(tool["input_schema"], format_checker=FormatChecker()).validate(arguments)
        except Exception as error:
            raise AgentFailure("wrong_argument_extraction", "Tool arguments violate the schema") from error
        async with self.client() as client:
            response = await client.post(f"/api/tools/{name}", json=arguments)
        if response.status_code >= 400:
            raise AgentFailure("tool_execution_failure", f"GIS tool failed with HTTP {response.status_code}")
        result = response.json()
        try:
            json.dumps(result, allow_nan=False)
            if result.get("tool") != name or result.get("arguments") != arguments or result.get("version") != "1.0":
                raise ValueError("Inconsistent result envelope")
            Draft7Validator(tool["output_schema"], format_checker=FormatChecker()).validate(result["data"])
            if not result.get("evidence", {}).get("data_source"):
                raise ValueError("Missing evidence")
        except Exception as error:
            raise AgentFailure("verification_failure", "Invalid or inconsistent GIS tool output") from error
        return result
