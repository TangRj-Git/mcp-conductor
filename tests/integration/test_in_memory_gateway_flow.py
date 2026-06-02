from __future__ import annotations

import asyncio
import json

from fastmcp import Client, FastMCP

from mcp_conductor.config.schema import GatewayConfig, UpstreamServerConfig
from mcp_conductor.runtime import GatewayRuntime
from mcp_conductor.server import create_server
from mcp_conductor.upstream.client import UpstreamClient


def test_gateway_discovers_recommends_and_calls_in_memory_upstream(tmp_path) -> None:
    config_path = tmp_path / "mcp-conductor.config.json"
    config_path.write_text(
        json.dumps({"mcpServers": {"github": {"transport": "stdio"}}}),
        encoding="utf-8",
    )
    upstream = FastMCP("github")

    @upstream.tool(name="get_pr_checks")
    def get_pr_checks(pr_number: int) -> dict:
        """Read PR CI checks."""
        return {"pr_number": pr_number, "state": "success"}

    class InMemoryManager:
        def __init__(self, config: GatewayConfig) -> None:
            assert "github" in config.upstream_servers
            self.clients = {
                "github": UpstreamClient(
                    UpstreamServerConfig(server_id="github"),
                    session=Client(upstream),
                )
            }

        async def astartup(self) -> None:
            for client in self.clients.values():
                await client.connect()

        async def ashutdown(self) -> None:
            for client in self.clients.values():
                await client.shutdown()
            self.clients = {}

        def get_client(self, server_id: str) -> UpstreamClient:
            return self.clients[server_id]

    async def run() -> None:
        runtime = GatewayRuntime(
            config_path=str(config_path),
            upstream_manager_factory=InMemoryManager,
        )
        server = create_server(runtime)

        async with Client(server) as gateway_client:
            listed = await gateway_client.call_tool("list_upstream_capabilities", {})
            assert listed.data["capabilities"][0]["capability_id"] == (
                "github.tools.get_pr_checks"
            )

            recommendation = await gateway_client.call_tool(
                "recommend_capabilities",
                {"user_task": "check PR CI", "limit": 5},
            )
            recommended = recommendation.data["recommended_capabilities"][0]

            result = await gateway_client.call_tool(
                "call_upstream_tool",
                {
                    "recommendation_id": recommendation.data["recommendation_id"],
                    "route_token": recommended["route_token"],
                    "capability_id": recommended["capability_id"],
                    "arguments": {"pr_number": 12},
                },
            )

            assert result.data["status"] == "ok"
            assert result.data["data"] == {"pr_number": 12, "state": "success"}

    asyncio.run(run())


def test_gateway_reads_resource_and_gets_prompt_from_in_memory_upstream(tmp_path) -> None:
    config_path = tmp_path / "mcp-conductor.config.json"
    config_path.write_text(
        json.dumps({"mcpServers": {"learn": {"transport": "stdio"}}}),
        encoding="utf-8",
    )
    upstream = FastMCP("learn")

    @upstream.resource("mcp://docs/intro", name="intro", mime_type="text/markdown")
    def intro() -> str:
        return "# Intro\nMCP basics."

    @upstream.resource(
        "mcp://concepts/{name}",
        name="concept",
        mime_type="text/markdown",
    )
    def concept(name: str) -> str:
        return f"# Concept\n{name}"

    @upstream.prompt(name="explain_topic")
    def explain_topic(topic: str) -> str:
        return f"Explain {topic}"

    class InMemoryManager:
        def __init__(self, config: GatewayConfig) -> None:
            assert "learn" in config.upstream_servers
            self.clients = {
                "learn": UpstreamClient(
                    UpstreamServerConfig(server_id="learn"),
                    session=Client(upstream),
                )
            }

        async def astartup(self) -> None:
            for client in self.clients.values():
                await client.connect()

        async def ashutdown(self) -> None:
            for client in self.clients.values():
                await client.shutdown()
            self.clients = {}

        def get_client(self, server_id: str) -> UpstreamClient:
            return self.clients[server_id]

    async def run() -> None:
        runtime = GatewayRuntime(
            config_path=str(config_path),
            upstream_manager_factory=InMemoryManager,
        )
        server = create_server(runtime)

        async with Client(server) as gateway_client:
            recommendation = await gateway_client.call_tool(
                "recommend_capabilities",
                {"user_task": "intro explain topic docs", "limit": 10},
            )
            resource = next(
                item
                for item in recommendation.data["recommended_capabilities"]
                if item["capability_type"] == "resource"
            )
            template = next(
                item
                for item in recommendation.data["recommended_capabilities"]
                if item["capability_type"] == "resource_template"
            )
            prompt = next(
                item
                for item in recommendation.data["recommended_capabilities"]
                if item["capability_type"] == "prompt"
            )

            resource_result = await gateway_client.call_tool(
                "read_upstream_resource",
                {
                    "recommendation_id": recommendation.data["recommendation_id"],
                    "route_token": resource["route_token"],
                    "capability_id": resource["capability_id"],
                },
            )
            prompt_result = await gateway_client.call_tool(
                "get_upstream_prompt",
                {
                    "recommendation_id": recommendation.data["recommendation_id"],
                    "route_token": prompt["route_token"],
                    "capability_id": prompt["capability_id"],
                    "arguments": {"topic": "resources"},
                },
            )
            template_result = await gateway_client.call_tool(
                "read_upstream_resource_template",
                {
                    "recommendation_id": recommendation.data["recommendation_id"],
                    "route_token": template["route_token"],
                    "capability_id": template["capability_id"],
                    "arguments": {"name": "resources"},
                },
            )

            assert resource_result.data["status"] == "ok"
            assert resource_result.data["data"][0]["text"] == "# Intro\nMCP basics."
            assert prompt_result.data["status"] == "ok"
            assert prompt_result.data["data"]["messages"][0]["content"]["text"] == (
                "Explain resources"
            )
            assert template_result.data["status"] == "ok"
            assert template_result.data["data"][0]["text"] == "# Concept\nresources"

    asyncio.run(run())
