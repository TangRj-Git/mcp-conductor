from __future__ import annotations

import asyncio

from mcp_conductor.discovery.service import CapabilityDiscoveryService
from mcp_conductor.models import CapabilityType, RiskLevel


class FakeClient:
    def list_tools(self):
        return [
            {
                "name": "get_pr_checks",
                "description": "Read PR CI checks",
                "input_schema": {
                    "type": "object",
                    "properties": {"pr_number": {"type": "integer"}},
                },
            }
        ]

    def list_resources(self):
        return [
            {
                "uri": "repo://owner/project/README.md",
                "name": "README.md",
                "description": "Repository README",
                "mime_type": "text/markdown",
            }
        ]

    def list_resource_templates(self):
        return [
            {
                "uri_template": "repo://owner/project/{path}",
                "name": "Repository file",
                "description": "Read a repository file by path",
                "mime_type": "text/plain",
            }
        ]

    def list_prompts(self):
        return [
            {
                "name": "summarize_pr",
                "description": "Summarize a pull request",
                "arguments": [{"name": "pr_number", "required": True}],
            }
        ]


class FakeManager:
    clients = {"github": FakeClient()}


def test_discovery_service_converts_upstream_tools_to_capabilities() -> None:
    service = CapabilityDiscoveryService(upstream_manager=FakeManager())

    capabilities = service.discover()

    assert len(capabilities) == 4
    capability = capabilities[0]
    assert capability.capability_id == "github.tools.get_pr_checks"
    assert capability.capability_type == CapabilityType.TOOL
    assert capability.upstream_server_id == "github"
    assert capability.upstream_client_id == "github"
    assert capability.original_name_or_uri == "get_pr_checks"
    assert capability.description == "Read PR CI checks"
    assert capability.schema_or_metadata["properties"]["pr_number"]["type"] == "integer"
    assert capability.risk_level == RiskLevel.READ_ONLY
    assert capability.read_only_hint is True

    resource = capabilities[1]
    assert resource.capability_type == CapabilityType.RESOURCE
    assert resource.upstream_server_id == "github"
    assert resource.original_name_or_uri == "repo://owner/project/README.md"
    assert resource.schema_or_metadata["name"] == "README.md"
    assert resource.schema_or_metadata["mime_type"] == "text/markdown"

    resource_template = capabilities[2]
    assert resource_template.capability_type == CapabilityType.RESOURCE_TEMPLATE
    assert resource_template.original_name_or_uri == "repo://owner/project/{path}"
    assert resource_template.schema_or_metadata["uri_template"] == "repo://owner/project/{path}"

    prompt = capabilities[3]
    assert prompt.capability_type == CapabilityType.PROMPT
    assert prompt.capability_id == "github.prompts.summarize_pr"
    assert prompt.schema_or_metadata["arguments"][0]["name"] == "pr_number"


def test_discovery_service_supports_async_upstream_clients() -> None:
    class FakeAsyncClient:
        async def list_tools_async(self):
            return [
                {
                    "name": "list_issues",
                    "description": "List repository issues",
                    "input_schema": {"type": "object"},
                }
            ]

    class FakeAsyncManager:
        clients = {"github": FakeAsyncClient()}

    async def run() -> None:
        service = CapabilityDiscoveryService(upstream_manager=FakeAsyncManager())
        capabilities = await service.discover_async()

        assert len(capabilities) == 1
        assert capabilities[0].capability_id == "github.tools.list_issues"
        assert capabilities[0].risk_level == RiskLevel.READ_ONLY

    asyncio.run(run())


def test_discovery_service_records_errors_without_stopping_other_discovery() -> None:
    class PartiallyBrokenClient:
        def list_tools(self):
            raise RuntimeError("tools unavailable")

        def list_resources(self):
            return [
                {
                    "uri": "repo://owner/project/README.md",
                    "name": "README.md",
                    "description": "Repository README",
                    "mime_type": "text/markdown",
                }
            ]

    class HealthyClient:
        def list_tools(self):
            return [
                {
                    "name": "list_issues",
                    "description": "List repository issues",
                    "input_schema": {"type": "object"},
                }
            ]

    class MixedManager:
        clients = {
            "broken": PartiallyBrokenClient(),
            "github": HealthyClient(),
        }

    service = CapabilityDiscoveryService(upstream_manager=MixedManager())

    capabilities = service.discover()

    assert [capability.capability_id for capability in capabilities] == [
        "broken.resources.repo%3A%2F%2Fowner%2Fproject%2FREADME.md",
        "github.tools.list_issues",
    ]
    assert service.errors == [
        {
            "upstream_server_id": "broken",
            "capability_type": "tool",
            "operation": "list_tools",
            "error": "tools unavailable",
        }
    ]


def test_discovery_service_records_async_errors_without_stopping_other_discovery() -> None:
    class PartiallyBrokenAsyncClient:
        async def list_tools_async(self):
            raise RuntimeError("async tools unavailable")

        async def list_prompts_async(self):
            return [
                {
                    "name": "summarize_pr",
                    "description": "Summarize a pull request",
                    "arguments": [],
                }
            ]

    class AsyncManager:
        clients = {"github": PartiallyBrokenAsyncClient()}

    async def run() -> None:
        service = CapabilityDiscoveryService(upstream_manager=AsyncManager())

        capabilities = await service.discover_async()

        assert [capability.capability_id for capability in capabilities] == [
            "github.prompts.summarize_pr"
        ]
        assert service.errors == [
            {
                "upstream_server_id": "github",
                "capability_type": "tool",
                "operation": "list_tools",
                "error": "async tools unavailable",
            }
        ]

    asyncio.run(run())
