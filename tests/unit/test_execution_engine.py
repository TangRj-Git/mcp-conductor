from __future__ import annotations

import asyncio
from typing import Any

from mcp_conductor.execution.engine import GatewayExecutionEngine
from mcp_conductor.models import Capability, CapabilityType, RiskLevel


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, arguments))
        return {"called": name, "arguments": arguments}


class FakeManager:
    def __init__(self, client: FakeClient) -> None:
        self.client = client

    def get_client(self, server_id: str) -> FakeClient:
        assert server_id == "github"
        return self.client


def test_execution_engine_routes_tool_call_to_capability_upstream_client() -> None:
    client = FakeClient()
    engine = GatewayExecutionEngine(upstream_manager=FakeManager(client))
    capability = Capability(
        capability_id="github.tools.get_pr_checks",
        capability_type=CapabilityType.TOOL,
        upstream_server_id="github",
        upstream_client_id="github",
        original_name_or_uri="get_pr_checks",
        risk_level=RiskLevel.READ_ONLY,
    )

    result = engine.call_tool(capability, {"pr_number": 12})

    assert result == {
        "called": "get_pr_checks",
        "arguments": {"pr_number": 12},
    }
    assert client.calls == [("get_pr_checks", {"pr_number": 12})]


def test_execution_engine_supports_async_upstream_client_calls() -> None:
    class FakeAsyncClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, Any]]] = []

        async def call_tool_async(
                self,
                name: str,
                arguments: dict[str, Any],
        ) -> dict[str, Any]:
            self.calls.append((name, arguments))
            return {"state": "success"}

    class FakeAsyncManager:
        def __init__(self) -> None:
            self.client = FakeAsyncClient()

        def get_client(self, server_id: str) -> FakeAsyncClient:
            assert server_id == "github"
            return self.client

    async def run() -> None:
        manager = FakeAsyncManager()
        engine = GatewayExecutionEngine(upstream_manager=manager)
        capability = Capability(
            capability_id="github.tools.get_pr_checks",
            capability_type=CapabilityType.TOOL,
            upstream_server_id="github",
            upstream_client_id="github",
            original_name_or_uri="get_pr_checks",
            risk_level=RiskLevel.READ_ONLY,
        )

        result = await engine.call_tool_async(capability, {"pr_number": 12})

        assert result == {"state": "success"}
        assert manager.client.calls == [("get_pr_checks", {"pr_number": 12})]

    asyncio.run(run())
