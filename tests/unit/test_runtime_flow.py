from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from mcp_conductor.config.schema import (
    ExposureConfig,
    ExposureMode,
    GatewayConfig,
    RiskPolicy,
    RootsPolicy,
    UpstreamServerConfig,
)
from mcp_conductor.execution.validation import validate_arguments
from mcp_conductor.models import Capability, CapabilityType, RiskLevel
from mcp_conductor.registry.store import CapabilityRegistry
from mcp_conductor.runtime import GatewayRuntime


class FakeToolExecutor:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[tuple[Capability, dict[str, Any]]] = []

    def call_tool(self, capability: Capability, arguments: dict[str, Any]) -> Any:
        self.calls.append((capability, arguments))
        return self.result


class AsyncFakeToolExecutor:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[tuple[Capability, dict[str, Any]]] = []

    async def call_tool_async(
        self,
        capability: Capability,
        arguments: dict[str, Any],
    ) -> Any:
        self.calls.append((capability, arguments))
        return self.result


class FailingToolExecutor:
    def call_tool(self, capability: Capability, arguments: dict[str, Any]) -> Any:
        raise RuntimeError("upstream exploded")


class AsyncFailingToolExecutor:
    async def call_tool_async(
        self,
        capability: Capability,
        arguments: dict[str, Any],
    ) -> Any:
        raise RuntimeError("async upstream exploded")


class FakeCapabilityExecutor(FakeToolExecutor):
    def __init__(
        self,
        tool_result: Any | None = None,
        resource_result: Any | None = None,
        prompt_result: Any | None = None,
    ) -> None:
        super().__init__({"ok": True} if tool_result is None else tool_result)
        self.resource_result = (
            [{"uri": "repo://README.md", "text": "# README"}]
            if resource_result is None
            else resource_result
        )
        self.prompt_result = (
            {"messages": [{"role": "user", "content": {"type": "text", "text": "Hi"}}]}
            if prompt_result is None
            else prompt_result
        )
        self.resource_calls: list[Capability] = []
        self.resource_uri_calls: list[tuple[Capability, str]] = []
        self.prompt_calls: list[tuple[Capability, dict[str, Any]]] = []

    def read_resource(self, capability: Capability) -> Any:
        self.resource_calls.append(capability)
        return self.resource_result

    def read_resource_uri(self, capability: Capability, uri: str) -> Any:
        self.resource_uri_calls.append((capability, uri))
        return self.resource_result

    def get_prompt(self, capability: Capability, arguments: dict[str, Any]) -> Any:
        self.prompt_calls.append((capability, arguments))
        return self.prompt_result


def make_tool(
    capability_id: str = "github.tools.get_pr_checks",
    *,
    name: str = "get_pr_checks",
    description: str = "Read PR CI check status",
    upstream_server_id: str = "github",
    input_schema: dict[str, Any] | None = None,
    risk_level: RiskLevel = RiskLevel.READ_ONLY,
    read_only_hint: bool | None = True,
) -> Capability:
    return Capability(
        capability_id=capability_id,
        capability_type=CapabilityType.TOOL,
        upstream_server_id=upstream_server_id,
        upstream_client_id=upstream_server_id,
        original_name_or_uri=name,
        description=description,
        schema_or_metadata=input_schema
        or {
            "type": "object",
            "properties": {"pr_number": {"type": "integer"}},
            "required": ["pr_number"],
        },
        tags=["github", "pr", "ci"],
        risk_level=risk_level,
        read_only_hint=read_only_hint,
        enabled=True,
    )


def make_resource() -> Capability:
    return Capability(
        capability_id="learn.resources.mcp%3A%2F%2Fdocs%2Fintro",
        capability_type=CapabilityType.RESOURCE,
        upstream_server_id="learn",
        upstream_client_id="learn",
        original_name_or_uri="mcp://docs/intro",
        description="MCP introduction resource",
        schema_or_metadata={
            "uri": "mcp://docs/intro",
            "name": "MCP introduction",
            "mime_type": "text/markdown",
        },
        tags=["learn", "docs"],
        risk_level=RiskLevel.READ_ONLY,
        read_only_hint=True,
        enabled=True,
    )


def make_resource_template() -> Capability:
    return Capability(
        capability_id="learn.resource_templates.mcp%3A%2F%2Fconcepts%2F%7Bname%7D",
        capability_type=CapabilityType.RESOURCE_TEMPLATE,
        upstream_server_id="learn",
        upstream_client_id="learn",
        original_name_or_uri="mcp://concepts/{name}",
        description="Read an MCP concept by name",
        schema_or_metadata={
            "uri_template": "mcp://concepts/{name}",
            "name": "MCP concept",
            "mime_type": "text/markdown",
        },
        tags=["learn", "concepts"],
        risk_level=RiskLevel.READ_ONLY,
        read_only_hint=True,
        enabled=True,
    )


def make_prompt() -> Capability:
    return Capability(
        capability_id="learn.prompts.explain_mcp_topic",
        capability_type=CapabilityType.PROMPT,
        upstream_server_id="learn",
        upstream_client_id="learn",
        original_name_or_uri="explain_mcp_topic",
        description="Explain an MCP topic",
        schema_or_metadata={
            "name": "explain_mcp_topic",
            "arguments": [
                {
                    "name": "topic",
                    "description": "Topic to explain",
                    "required": True,
                }
            ],
        },
        tags=["learn", "prompt"],
        risk_level=RiskLevel.READ_ONLY,
        read_only_hint=True,
        enabled=True,
    )


def make_runtime(
    capability: Capability,
    *,
    executor_result: Any | None = None,
    result_preview_limit: int = 3,
) -> tuple[GatewayRuntime, FakeToolExecutor]:
    registry = CapabilityRegistry()
    registry.add(capability)
    if executor_result is None:
        executor_result = {"ok": True}
    executor = FakeToolExecutor(executor_result)
    runtime = GatewayRuntime(
        registry=registry,
        tool_executor=executor,
        result_preview_limit=result_preview_limit,
    )
    return runtime, executor


def test_list_upstream_capabilities_reports_unavailable_upstreams() -> None:
    class FakeManager:
        startup_errors = {"github": "boom"}

    runtime = GatewayRuntime(registry=CapabilityRegistry())
    runtime.upstream_manager = FakeManager()

    result = runtime.list_upstream_capabilities()

    assert result["status"] == "ok"
    assert result["unavailable_upstreams"] == [
        {"upstream_server_id": "github", "error": "boom"}
    ]


def test_list_upstream_capabilities_reports_discovery_errors() -> None:
    runtime = GatewayRuntime(registry=CapabilityRegistry())
    runtime.discovery_errors = [
        {
            "upstream_server_id": "github",
            "capability_type": "tool",
            "operation": "list_tools",
            "error": "tools unavailable",
        }
    ]

    result = runtime.list_upstream_capabilities()

    assert result["status"] == "ok"
    assert result["discovery_errors"] == [
        {
            "upstream_server_id": "github",
            "capability_type": "tool",
            "operation": "list_tools",
            "error": "tools unavailable",
        }
    ]


def test_list_upstream_capabilities_rejects_invalid_cursor() -> None:
    runtime = GatewayRuntime(registry=CapabilityRegistry())

    result = runtime.list_upstream_capabilities(cursor="not-a-cursor")

    assert result["status"] == "error"
    assert result["error_code"] == "invalid_cursor"


def test_list_upstream_capabilities_rejects_invalid_limit() -> None:
    runtime = GatewayRuntime(registry=CapabilityRegistry())

    result = runtime.list_upstream_capabilities(limit=0)

    assert result["status"] == "error"
    assert result["error_code"] == "invalid_limit"


def test_list_upstream_capabilities_filters_and_reports_counts() -> None:
    registry = CapabilityRegistry()
    registry.add(make_tool())
    registry.add(make_resource())
    registry.add(make_prompt())
    runtime = GatewayRuntime(registry=registry)

    result = runtime.list_upstream_capabilities(
        capability_type="resource",
        upstream_server_id="learn",
        query="intro",
        limit=10,
    )

    assert result["status"] == "ok"
    assert result["total_count"] == 3
    assert result["filtered_count"] == 1
    assert result["type_counts"] == {
        "prompt": 1,
        "resource": 1,
        "tool": 1,
    }
    assert result["upstream_counts"] == {"github": 1, "learn": 2}
    assert result["capabilities"][0]["capability_id"] == (
        "learn.resources.mcp%3A%2F%2Fdocs%2Fintro"
    )


def test_list_upstream_capabilities_rejects_unknown_capability_type_filter() -> None:
    runtime = GatewayRuntime(registry=CapabilityRegistry())

    result = runtime.list_upstream_capabilities(capability_type="unknown")

    assert result["status"] == "error"
    assert result["error_code"] == "invalid_capability_type_filter"
    assert "next_step" in result


def test_list_exposed_capabilities_returns_current_exposure_plan() -> None:
    registry = CapabilityRegistry()
    registry.add(make_tool())
    registry.add(make_resource())
    runtime = GatewayRuntime(
        config=GatewayConfig(
            exposure=ExposureConfig(mode=ExposureMode.HYBRID),
        ),
        registry=registry,
    )

    result = runtime.list_exposed_capabilities()

    assert result["status"] == "ok"
    assert result["mode"] == "hybrid"
    assert result["dynamic_registration_enabled"] is False
    assert result["exposed_count"] == 1
    assert result["exposed_capabilities"][0]["exposed_name"] == "github__get_pr_checks"
    assert result["exposed_capabilities"][0]["capability_id"] == "github.tools.get_pr_checks"
    assert result["skipped_capabilities"] == []
    assert result["skipped_count"] == 1
    assert "next_step" in result


def test_list_exposed_capabilities_can_include_skipped_details() -> None:
    registry = CapabilityRegistry()
    registry.add(make_tool())
    registry.add(make_resource())
    runtime = GatewayRuntime(
        config=GatewayConfig(
            exposure=ExposureConfig(mode=ExposureMode.HYBRID),
        ),
        registry=registry,
    )

    result = runtime.list_exposed_capabilities(include_skipped=True)

    assert result["status"] == "ok"
    assert result["skipped_capabilities"][0]["capability_id"] == (
        "learn.resources.mcp%3A%2F%2Fdocs%2Fintro"
    )


def test_list_exposed_capabilities_paginates_exposed_capabilities() -> None:
    registry = CapabilityRegistry()
    registry.add(make_tool(capability_id="github.tools.a", name="a"))
    registry.add(make_tool(capability_id="github.tools.b", name="b"))
    registry.add(make_tool(capability_id="github.tools.c", name="c"))
    runtime = GatewayRuntime(
        config=GatewayConfig(
            exposure=ExposureConfig(mode=ExposureMode.HYBRID),
        ),
        registry=registry,
    )

    first_page = runtime.list_exposed_capabilities(limit=2)
    second_page = runtime.list_exposed_capabilities(cursor=first_page["next_cursor"], limit=2)

    assert [item["capability_id"] for item in first_page["exposed_capabilities"]] == [
        "github.tools.a",
        "github.tools.b",
    ]
    assert first_page["next_cursor"] == "2"
    assert first_page["has_more"] is True
    assert [item["capability_id"] for item in second_page["exposed_capabilities"]] == [
        "github.tools.c"
    ]
    assert second_page["next_cursor"] is None
    assert second_page["has_more"] is False


def test_list_exposed_capabilities_rejects_invalid_cursor() -> None:
    runtime = GatewayRuntime(registry=CapabilityRegistry())

    result = runtime.list_exposed_capabilities(cursor="bad")

    assert result["status"] == "error"
    assert result["error_code"] == "invalid_cursor"


def test_recommend_capabilities_returns_route_token_for_matching_tool() -> None:
    runtime, _ = make_runtime(make_tool())

    result = runtime.recommend_capabilities(
        user_task="check PR CI status",
        context_summary="GitHub repository",
        limit=5,
    )

    assert result["status"] == "ok"
    assert result["recommendation_id"].startswith("rec_")
    assert len(result["recommended_capabilities"]) == 1
    recommended = result["recommended_capabilities"][0]
    assert recommended["capability_id"] == "github.tools.get_pr_checks"
    assert recommended["route_token"].startswith("route_")
    assert recommended["input_schema"]["required"] == ["pr_number"]
    assert recommended["next_public_tool"] == "call_upstream_tool"
    assert recommended["example_arguments"] == {"pr_number": 1}
    assert recommended["ready_to_call_arguments"] == {
        "recommendation_id": result["recommendation_id"],
        "route_token": recommended["route_token"],
        "capability_id": "github.tools.get_pr_checks",
        "arguments": {"pr_number": 1},
    }
    assert "call_upstream_tool" in recommended["usage_hint"]


def test_recommend_capabilities_can_recommend_readable_non_tool_capabilities() -> None:
    registry = CapabilityRegistry()
    registry.add(make_resource_template())
    registry.add(make_resource())
    registry.add(make_prompt())
    runtime = GatewayRuntime(registry=registry)

    result = runtime.recommend_capabilities(user_task="explain MCP topic docs", limit=10)

    assert result["status"] == "ok"
    recommended_ids = {
        item["capability_id"]
        for item in result["recommended_capabilities"]
    }
    assert "learn.resource_templates.mcp%3A%2F%2Fconcepts%2F%7Bname%7D" in recommended_ids
    assert "learn.resources.mcp%3A%2F%2Fdocs%2Fintro" in recommended_ids
    assert "learn.prompts.explain_mcp_topic" in recommended_ids
    template = next(
        item
        for item in result["recommended_capabilities"]
        if item["capability_id"] == (
            "learn.resource_templates.mcp%3A%2F%2Fconcepts%2F%7Bname%7D"
        )
    )
    assert template["input_schema"]["required"] == ["name"]
    assert template["next_public_tool"] == "read_upstream_resource_template"
    assert template["example_arguments"] == {"name": "tool"}
    assert template["ready_to_call_arguments"]["arguments"] == {"name": "tool"}
    prompt = next(
        item
        for item in result["recommended_capabilities"]
        if item["capability_id"] == "learn.prompts.explain_mcp_topic"
    )
    assert prompt["input_schema"]["required"] == ["topic"]
    assert prompt["next_public_tool"] == "get_upstream_prompt"
    assert prompt["example_arguments"] == {"topic": "tools"}


def test_recommend_capabilities_uses_context_summary_for_matching() -> None:
    registry = CapabilityRegistry()
    registry.add(make_tool())
    registry.add(
        make_tool(
            capability_id="docs.tools.read_docs",
            name="read_docs",
            description="Read documentation",
            upstream_server_id="docs",
        )
    )
    runtime = GatewayRuntime(registry=registry)

    result = runtime.recommend_capabilities(
        user_task="continue with the next step",
        context_summary="Need GitHub PR CI check status",
        limit=1,
    )

    assert result["status"] == "ok"
    assert result["recommended_capabilities"][0]["capability_id"] == (
        "github.tools.get_pr_checks"
    )


def test_recommend_capabilities_builds_schema_valid_nested_example_arguments() -> None:
    runtime, _ = make_runtime(
        make_tool(
            input_schema={
                "type": "object",
                "properties": {
                    "request": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "mode": {"type": "string", "enum": ["summary", "full"]},
                        },
                        "required": ["path", "mode"],
                        "additionalProperties": False,
                    },
                    "labels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                    },
                },
                "required": ["request", "labels"],
                "additionalProperties": False,
            }
        )
    )

    result = runtime.recommend_capabilities(user_task="check PR CI")
    recommended = result["recommended_capabilities"][0]

    assert validate_arguments(
        recommended["example_arguments"],
        recommended["input_schema"],
    ) == []
    assert recommended["ready_to_call_arguments"]["arguments"] == (
        recommended["example_arguments"]
    )


def test_recommend_capabilities_rejects_invalid_limit() -> None:
    runtime, _ = make_runtime(make_tool())

    result = runtime.recommend_capabilities(user_task="check PR CI", limit=0)

    assert result["status"] == "error"
    assert result["error_code"] == "invalid_limit"


def test_recommend_capabilities_excludes_mutations_when_risk_policy_is_read_only_only() -> None:
    registry = CapabilityRegistry()
    registry.add(
        make_tool(
            capability_id="filesystem.tools.delete_file",
            name="delete_file",
            description="Delete a file",
            upstream_server_id="filesystem",
            risk_level=RiskLevel.DESTRUCTIVE,
            read_only_hint=False,
        )
    )
    runtime = GatewayRuntime(
        config=GatewayConfig(
            upstream_servers={
                "filesystem": UpstreamServerConfig(
                    server_id="filesystem",
                    risk_policy=RiskPolicy.READ_ONLY_ONLY,
                )
            }
        ),
        registry=registry,
    )

    result = runtime.recommend_capabilities(user_task="delete file")

    assert result["status"] == "ok"
    assert result["recommended_capabilities"] == []


def test_recommend_capabilities_includes_mutations_when_risk_policy_confirms_mutations() -> None:
    registry = CapabilityRegistry()
    registry.add(
        make_tool(
            capability_id="filesystem.tools.delete_file",
            name="delete_file",
            description="Delete a file",
            upstream_server_id="filesystem",
            risk_level=RiskLevel.DESTRUCTIVE,
            read_only_hint=False,
        )
    )
    runtime = GatewayRuntime(
        config=GatewayConfig(
            upstream_servers={
                "filesystem": UpstreamServerConfig(
                    server_id="filesystem",
                    risk_policy=RiskPolicy.CONFIRM_MUTATIONS,
                )
            }
        ),
        registry=registry,
    )

    result = runtime.recommend_capabilities(user_task="delete file")

    assert result["status"] == "ok"
    assert result["recommended_capabilities"][0]["capability_id"] == (
        "filesystem.tools.delete_file"
    )
    assert result["recommended_capabilities"][0]["requires_confirmation"] is True


def test_recommend_capabilities_excludes_disabled_risk_policy_server() -> None:
    registry = CapabilityRegistry()
    registry.add(
        make_tool(
            capability_id="github.tools.get_pr_checks",
            name="get_pr_checks",
            description="Read PR CI checks",
            upstream_server_id="github",
            risk_level=RiskLevel.READ_ONLY,
        )
    )
    runtime = GatewayRuntime(
        config=GatewayConfig(
            upstream_servers={
                "github": UpstreamServerConfig(
                    server_id="github",
                    risk_policy=RiskPolicy.DISABLED,
                )
            }
        ),
        registry=registry,
    )

    result = runtime.recommend_capabilities(user_task="check PR CI")

    assert result["status"] == "ok"
    assert result["recommended_capabilities"] == []


def test_call_upstream_tool_rejects_resource_template_capabilities() -> None:
    registry = CapabilityRegistry()
    registry.add(make_resource_template())
    executor = FakeCapabilityExecutor()
    runtime = GatewayRuntime(registry=registry, tool_executor=executor)

    recommendation = runtime.recommend_capabilities(user_task="read concept", limit=5)
    recommended = recommendation["recommended_capabilities"][0]

    result = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments={"name": "resources"},
    )

    assert result["status"] == "error"
    assert result["error_code"] == "invalid_capability_type"
    assert "next_step" in result


def test_read_upstream_resource_requires_recommendation_route_token() -> None:
    registry = CapabilityRegistry()
    registry.add(make_resource())
    executor = FakeCapabilityExecutor()
    runtime = GatewayRuntime(registry=registry, tool_executor=executor)

    recommendation = runtime.recommend_capabilities(user_task="read MCP docs")
    recommended = recommendation["recommended_capabilities"][0]

    result = runtime.read_upstream_resource(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
    )

    assert result["status"] == "ok"
    assert result["data"] == [{"uri": "repo://README.md", "text": "# README"}]
    assert executor.resource_calls[0].capability_id == recommended["capability_id"]


def test_read_upstream_resource_template_expands_encoded_arguments() -> None:
    registry = CapabilityRegistry()
    registry.add(make_resource_template())
    executor = FakeCapabilityExecutor()
    runtime = GatewayRuntime(registry=registry, tool_executor=executor)

    recommendation = runtime.recommend_capabilities(user_task="read MCP concept")
    recommended = recommendation["recommended_capabilities"][0]

    result = runtime.read_upstream_resource_template(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments={"name": "client/server"},
    )

    assert result["status"] == "ok"
    assert executor.resource_uri_calls[0][1] == "mcp://concepts/client%2Fserver"


def test_read_upstream_resource_template_validates_required_arguments() -> None:
    registry = CapabilityRegistry()
    registry.add(make_resource_template())
    executor = FakeCapabilityExecutor()
    runtime = GatewayRuntime(registry=registry, tool_executor=executor)

    recommendation = runtime.recommend_capabilities(user_task="read MCP concept")
    recommended = recommendation["recommended_capabilities"][0]

    result = runtime.read_upstream_resource_template(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments={},
    )

    assert result["status"] == "error"
    assert result["error_code"] == "invalid_arguments"
    assert "next_step" in result
    assert executor.resource_uri_calls == []


def test_get_upstream_prompt_validates_required_arguments() -> None:
    registry = CapabilityRegistry()
    registry.add(make_prompt())
    executor = FakeCapabilityExecutor()
    runtime = GatewayRuntime(registry=registry, tool_executor=executor)

    recommendation = runtime.recommend_capabilities(user_task="explain MCP topic")
    recommended = recommendation["recommended_capabilities"][0]

    result = runtime.get_upstream_prompt(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments={},
    )

    assert result["status"] == "error"
    assert result["error_code"] == "invalid_arguments"
    assert "next_step" in result
    assert executor.prompt_calls == []


def test_get_upstream_prompt_returns_prompt_result() -> None:
    registry = CapabilityRegistry()
    registry.add(make_prompt())
    executor = FakeCapabilityExecutor(
        prompt_result={
            "messages": [
                {
                    "role": "user",
                    "content": {"type": "text", "text": "Explain resources"},
                }
            ]
        }
    )
    runtime = GatewayRuntime(registry=registry, tool_executor=executor)

    recommendation = runtime.recommend_capabilities(user_task="explain MCP topic")
    recommended = recommendation["recommended_capabilities"][0]

    result = runtime.get_upstream_prompt(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments={"topic": "resources"},
    )

    assert result["status"] == "ok"
    assert result["data"]["messages"][0]["content"]["text"] == "Explain resources"
    assert executor.prompt_calls[0][1] == {"topic": "resources"}


def test_call_upstream_tool_rejects_invalid_route_token() -> None:
    runtime, executor = make_runtime(make_tool())
    recommendation = runtime.recommend_capabilities(user_task="check PR CI")
    recommended = recommendation["recommended_capabilities"][0]

    result = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token="route_wrong",
        capability_id=recommended["capability_id"],
        arguments={"pr_number": 12},
    )

    assert result["status"] == "error"
    assert result["error_code"] == "invalid_route_token"
    assert "next_step" in result
    assert executor.calls == []


def test_call_upstream_tool_rejects_arguments_that_do_not_match_schema() -> None:
    runtime, executor = make_runtime(
        make_tool(
            input_schema={
                "type": "object",
                "properties": {
                    "pr_number": {"type": "integer"},
                    "mode": {"type": "string", "enum": ["checks"]},
                },
                "required": ["pr_number", "mode"],
                "additionalProperties": False,
            }
        )
    )
    recommendation = runtime.recommend_capabilities(user_task="check PR CI")
    recommended = recommendation["recommended_capabilities"][0]

    result = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments={
            "pr_number": True,
            "mode": "wrong",
            "unexpected": "value",
        },
    )

    assert result["status"] == "error"
    assert result["error_code"] == "invalid_arguments"
    assert "next_step" in result
    assert executor.calls == []


def test_call_upstream_tool_executes_recommended_read_only_tool_and_caches_large_result() -> None:
    runtime, executor = make_runtime(
        make_tool(),
        executor_result=[{"job": "unit", "index": index} for index in range(5)],
        result_preview_limit=2,
    )
    recommendation = runtime.recommend_capabilities(user_task="check PR CI")
    recommended = recommendation["recommended_capabilities"][0]

    result = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments={"pr_number": 12},
        session_id="session-a",
    )

    assert result["status"] == "ok"
    assert result["truncated"] is True
    assert len(result["preview"]) == 2
    assert result["result_id"].startswith("result_")
    assert executor.calls[0][1] == {"pr_number": 12}

    cached = runtime.read_result(result_id=result["result_id"], limit=10, session_id="session-a")
    assert cached["status"] == "ok"
    assert len(cached["items"]) == 5


def test_call_upstream_tool_scopes_cached_results_by_session() -> None:
    runtime, _ = make_runtime(
        make_tool(),
        executor_result=[{"job": "unit", "index": index} for index in range(5)],
        result_preview_limit=2,
    )
    recommendation = runtime.recommend_capabilities(user_task="check PR CI")
    recommended = recommendation["recommended_capabilities"][0]

    result = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments={"pr_number": 12},
        session_id="session-a",
    )

    assert result["status"] == "ok"
    assert result["truncated"] is True
    assert runtime.read_result(
        result_id=result["result_id"],
        session_id="session-a",
    )["status"] == "ok"
    assert runtime.read_result(
        result_id=result["result_id"],
        session_id="session-b",
    )["status"] == "not_found"


def test_read_result_rejects_invalid_cursor() -> None:
    runtime, _ = make_runtime(
        make_tool(),
        executor_result=[{"job": "unit", "index": index} for index in range(5)],
        result_preview_limit=2,
    )
    recommendation = runtime.recommend_capabilities(user_task="check PR CI")
    recommended = recommendation["recommended_capabilities"][0]
    result = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments={"pr_number": 12},
        session_id="session-a",
    )

    cached = runtime.read_result(
        result_id=result["result_id"],
        cursor="bad",
        session_id="session-a",
    )

    assert cached["status"] == "error"
    assert cached["error_code"] == "invalid_cursor"


def test_read_result_rejects_invalid_limit() -> None:
    runtime, _ = make_runtime(
        make_tool(),
        executor_result=[{"job": "unit", "index": index} for index in range(5)],
        result_preview_limit=2,
    )
    recommendation = runtime.recommend_capabilities(user_task="check PR CI")
    recommended = recommendation["recommended_capabilities"][0]
    result = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments={"pr_number": 12},
        session_id="session-a",
    )

    cached = runtime.read_result(
        result_id=result["result_id"],
        limit=0,
        session_id="session-a",
    )

    assert cached["status"] == "error"
    assert cached["error_code"] == "invalid_limit"


def test_call_upstream_tool_async_executes_recommended_read_only_tool() -> None:
    capability = make_tool()
    registry = CapabilityRegistry()
    registry.add(capability)
    executor = AsyncFakeToolExecutor({"state": "success"})
    runtime = GatewayRuntime(registry=registry, tool_executor=executor)

    async def run() -> None:
        recommendation = runtime.recommend_capabilities(user_task="check PR CI")
        recommended = recommendation["recommended_capabilities"][0]

        result = await runtime.call_upstream_tool_async(
            recommendation_id=recommendation["recommendation_id"],
            route_token=recommended["route_token"],
            capability_id=recommended["capability_id"],
            arguments={"pr_number": 12},
        )

        assert result["status"] == "ok"
        assert result["data"] == {"state": "success"}
        assert executor.calls[0][1] == {"pr_number": 12}

    asyncio.run(run())


def test_call_upstream_tool_wraps_upstream_execution_errors() -> None:
    capability = make_tool()
    registry = CapabilityRegistry()
    registry.add(capability)
    runtime = GatewayRuntime(registry=registry, tool_executor=FailingToolExecutor())
    recommendation = runtime.recommend_capabilities(user_task="check PR CI")
    recommended = recommendation["recommended_capabilities"][0]

    result = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments={"pr_number": 12},
    )

    assert result["status"] == "error"
    assert result["error_code"] == "upstream_tool_error"
    assert result["message"] == "Upstream tool call failed."
    assert result["details"]["capability_id"] == "github.tools.get_pr_checks"
    assert result["details"]["upstream_server_id"] == "github"
    assert "upstream exploded" in result["details"]["error"]


def test_call_upstream_tool_async_wraps_upstream_execution_errors() -> None:
    capability = make_tool()
    registry = CapabilityRegistry()
    registry.add(capability)
    runtime = GatewayRuntime(
        registry=registry,
        tool_executor=AsyncFailingToolExecutor(),
    )

    async def run() -> None:
        recommendation = runtime.recommend_capabilities(user_task="check PR CI")
        recommended = recommendation["recommended_capabilities"][0]

        result = await runtime.call_upstream_tool_async(
            recommendation_id=recommendation["recommendation_id"],
            route_token=recommended["route_token"],
            capability_id=recommended["capability_id"],
            arguments={"pr_number": 12},
        )

        assert result["status"] == "error"
        assert result["error_code"] == "upstream_tool_error"
        assert result["message"] == "Upstream tool call failed."
        assert result["details"]["capability_id"] == "github.tools.get_pr_checks"
        assert result["details"]["upstream_server_id"] == "github"
        assert "async upstream exploded" in result["details"]["error"]

    asyncio.run(run())


def test_call_upstream_tool_denies_disabled_risk_policy_server_even_for_read_only() -> None:
    capability = make_tool(upstream_server_id="github")
    registry = CapabilityRegistry()
    registry.add(capability)
    executor = FakeToolExecutor({"ok": True})
    runtime = GatewayRuntime(
        config=GatewayConfig(
            upstream_servers={
                "github": UpstreamServerConfig(
                    server_id="github",
                    risk_policy=RiskPolicy.CONFIRM_MUTATIONS,
                )
            }
        ),
        registry=registry,
        tool_executor=executor,
    )
    recommendation = runtime.recommend_capabilities(user_task="check PR CI")
    recommended = recommendation["recommended_capabilities"][0]
    runtime.config = GatewayConfig(
        upstream_servers={
            "github": UpstreamServerConfig(
                server_id="github",
                risk_policy=RiskPolicy.DISABLED,
            )
        }
    )

    result = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments={"pr_number": 12},
    )

    assert result["status"] == "error"
    assert result["error_code"] == "risk_policy_denied"
    assert executor.calls == []


def test_call_upstream_tool_requires_confirmation_for_unknown_risk() -> None:
    runtime, executor = make_runtime(
        make_tool(
            capability_id="filesystem.tools.delete_file",
            name="delete_file",
            description="Delete a file",
            risk_level=RiskLevel.UNKNOWN,
            read_only_hint=None,
        )
    )
    recommendation = runtime.recommend_capabilities(user_task="delete file")
    recommended = recommendation["recommended_capabilities"][0]

    result = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments={"pr_number": 12},
    )

    assert result["status"] == "confirmation_required"
    assert result["pending_action_id"].startswith("pending_")
    assert result["capability_id"] == "filesystem.tools.delete_file"
    assert executor.calls == []


def test_call_upstream_tool_denies_mutation_when_risk_policy_is_read_only_only() -> None:
    capability = make_tool(
        capability_id="filesystem.tools.delete_file",
        name="delete_file",
        description="Delete a file",
        upstream_server_id="filesystem",
        risk_level=RiskLevel.DESTRUCTIVE,
        read_only_hint=False,
    )
    registry = CapabilityRegistry()
    registry.add(capability)
    executor = FakeToolExecutor({"ok": True})
    runtime = GatewayRuntime(
        config=GatewayConfig(
            upstream_servers={
                "filesystem": UpstreamServerConfig(
                    server_id="filesystem",
                    risk_policy=RiskPolicy.CONFIRM_MUTATIONS,
                )
            }
        ),
        registry=registry,
        tool_executor=executor,
    )
    recommendation = runtime.recommend_capabilities(user_task="delete file")
    recommended = recommendation["recommended_capabilities"][0]
    runtime.config = GatewayConfig(
        upstream_servers={
            "filesystem": UpstreamServerConfig(
                server_id="filesystem",
                risk_policy=RiskPolicy.READ_ONLY_ONLY,
            )
        }
    )

    result = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments={"pr_number": 12},
    )

    assert result["status"] == "error"
    assert result["error_code"] == "risk_policy_denied"
    assert "pending_action_id" not in result
    assert executor.calls == []


def test_call_upstream_tool_uses_pending_confirmation_when_risk_policy_confirms_mutations() -> None:
    capability = make_tool(
        capability_id="filesystem.tools.delete_file",
        name="delete_file",
        description="Delete a file",
        upstream_server_id="filesystem",
        risk_level=RiskLevel.DESTRUCTIVE,
        read_only_hint=False,
    )
    registry = CapabilityRegistry()
    registry.add(capability)
    executor = FakeToolExecutor({"ok": True})
    runtime = GatewayRuntime(
        config=GatewayConfig(
            upstream_servers={
                "filesystem": UpstreamServerConfig(
                    server_id="filesystem",
                    risk_policy=RiskPolicy.CONFIRM_MUTATIONS,
                )
            }
        ),
        registry=registry,
        tool_executor=executor,
    )
    recommendation = runtime.recommend_capabilities(user_task="delete file")
    recommended = recommendation["recommended_capabilities"][0]

    pending = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments={"pr_number": 12},
    )
    runtime.pending_actions.mark_confirmed(pending["pending_action_id"])
    result = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments={"pr_number": 12},
        pending_action_id=pending["pending_action_id"],
    )

    assert pending["status"] == "confirmation_required"
    assert result["status"] == "ok"
    assert executor.calls[0][1] == {"pr_number": 12}


def test_call_upstream_tool_rejects_unconfirmed_pending_action() -> None:
    runtime, executor = make_runtime(
        make_tool(
            capability_id="filesystem.tools.delete_file",
            name="delete_file",
            description="Delete a file",
            risk_level=RiskLevel.DESTRUCTIVE,
            read_only_hint=False,
        )
    )
    recommendation = runtime.recommend_capabilities(user_task="delete file")
    recommended = recommendation["recommended_capabilities"][0]
    arguments = {"pr_number": 12}

    pending = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments=arguments,
    )

    result = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments=arguments,
        pending_action_id=pending["pending_action_id"],
    )

    assert result["status"] == "error"
    assert result["error_code"] == "confirmation_not_completed"
    assert executor.calls == []


def test_confirm_pending_action_marks_host_confirmed_action() -> None:
    runtime, executor = make_runtime(
        make_tool(
            capability_id="filesystem.tools.delete_file",
            name="delete_file",
            description="Delete a file",
            risk_level=RiskLevel.DESTRUCTIVE,
            read_only_hint=False,
        )
    )
    recommendation = runtime.recommend_capabilities(user_task="delete file")
    recommended = recommendation["recommended_capabilities"][0]
    arguments = {"pr_number": 12}
    pending = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments=arguments,
    )

    confirmation = runtime.confirm_pending_action(
        pending_action_id=pending["pending_action_id"],
    )
    result = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments=arguments,
        pending_action_id=pending["pending_action_id"],
    )

    assert confirmation["status"] == "ok"
    assert confirmation["pending_action_id"] == pending["pending_action_id"]
    assert result["status"] == "ok"
    assert executor.calls[0][1] == arguments


def test_confirm_pending_action_rejects_unknown_pending_action() -> None:
    runtime, _ = make_runtime(make_tool())

    result = runtime.confirm_pending_action(pending_action_id="pending_missing")

    assert result["status"] == "error"
    assert result["error_code"] == "pending_action_not_found"


def test_call_upstream_tool_executes_confirmed_pending_action_once() -> None:
    runtime, executor = make_runtime(
        make_tool(
            capability_id="filesystem.tools.delete_file",
            name="delete_file",
            description="Delete a file",
            risk_level=RiskLevel.DESTRUCTIVE,
            read_only_hint=False,
        )
    )
    recommendation = runtime.recommend_capabilities(user_task="delete file")
    recommended = recommendation["recommended_capabilities"][0]
    arguments = {"pr_number": 12}

    pending = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments=arguments,
    )
    runtime.pending_actions.mark_confirmed(pending["pending_action_id"])

    result = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments=arguments,
        pending_action_id=pending["pending_action_id"],
    )
    replay = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments=arguments,
        pending_action_id=pending["pending_action_id"],
    )

    assert result["status"] == "ok"
    assert executor.calls == [(runtime.registry.get(recommended["capability_id"]), arguments)]
    assert replay["status"] == "error"
    assert replay["error_code"] == "pending_action_not_found"


def test_call_upstream_tool_rejects_pending_action_when_arguments_change() -> None:
    runtime, executor = make_runtime(
        make_tool(
            capability_id="filesystem.tools.delete_file",
            name="delete_file",
            description="Delete a file",
            risk_level=RiskLevel.DESTRUCTIVE,
            read_only_hint=False,
        )
    )
    recommendation = runtime.recommend_capabilities(user_task="delete file")
    recommended = recommendation["recommended_capabilities"][0]

    pending = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments={"pr_number": 12},
    )

    result = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments={"pr_number": 13},
        pending_action_id=pending["pending_action_id"],
    )

    assert result["status"] == "error"
    assert result["error_code"] == "pending_action_arguments_changed"
    assert executor.calls == []


def test_call_upstream_tool_rejects_expired_pending_action() -> None:
    runtime, executor = make_runtime(
        make_tool(
            capability_id="filesystem.tools.delete_file",
            name="delete_file",
            description="Delete a file",
            risk_level=RiskLevel.DESTRUCTIVE,
            read_only_hint=False,
        )
    )
    recommendation = runtime.recommend_capabilities(user_task="delete file")
    recommended = recommendation["recommended_capabilities"][0]
    arguments = {"pr_number": 12}

    pending = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments=arguments,
    )
    pending_action = runtime.pending_actions.get(pending["pending_action_id"])
    assert pending_action is not None
    pending_action.expires_at = datetime.now(UTC) - timedelta(seconds=1)

    result = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments=arguments,
        pending_action_id=pending["pending_action_id"],
    )

    assert result["status"] == "error"
    assert result["error_code"] == "pending_action_expired"
    assert executor.calls == []


def test_runtime_prunes_expired_pending_actions_during_state_cleanup() -> None:
    runtime, _ = make_runtime(
        make_tool(
            capability_id="filesystem.tools.delete_file",
            name="delete_file",
            description="Delete a file",
            risk_level=RiskLevel.DESTRUCTIVE,
            read_only_hint=False,
        )
    )
    pending = runtime.pending_actions.create(
        capability_id="filesystem.tools.delete_file",
        arguments={"pr_number": 12},
        risk_level=RiskLevel.DESTRUCTIVE,
    )
    pending.expires_at = datetime.now(UTC) - timedelta(seconds=1)

    runtime.read_result(result_id="missing")

    assert runtime.pending_actions.get(pending.pending_action_id) is None


def test_call_upstream_tool_rejects_path_outside_allowed_roots() -> None:
    capability = make_tool(
        capability_id="filesystem.tools.read_file",
        name="read_file",
        description="Read a local file",
        upstream_server_id="filesystem",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        risk_level=RiskLevel.READ_ONLY,
    )
    registry = CapabilityRegistry()
    registry.add(capability)
    executor = FakeToolExecutor({"ok": True})
    runtime = GatewayRuntime(
        config=GatewayConfig(
            upstream_servers={
                "filesystem": UpstreamServerConfig(
                    server_id="filesystem",
                    roots_policy=RootsPolicy.CONFIG_ALLOWLIST_ONLY,
                    allowed_roots=["E:\\SoftwareProject\\allowed"],
                )
            }
        ),
        registry=registry,
        tool_executor=executor,
    )
    recommendation = runtime.recommend_capabilities(user_task="read file")
    recommended = recommendation["recommended_capabilities"][0]

    result = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments={"path": "E:\\SoftwareProject\\outside\\secret.txt"},
    )

    assert result["status"] == "error"
    assert result["error_code"] == "path_not_allowed"
    assert executor.calls == []


def test_call_upstream_tool_rejects_filename_outside_allowed_roots() -> None:
    capability = make_tool(
        capability_id="filesystem.tools.read_file",
        name="read_file",
        description="Read a local file",
        upstream_server_id="filesystem",
        input_schema={
            "type": "object",
            "properties": {"filename": {"type": "string"}},
            "required": ["filename"],
        },
        risk_level=RiskLevel.READ_ONLY,
    )
    registry = CapabilityRegistry()
    registry.add(capability)
    executor = FakeToolExecutor({"ok": True})
    runtime = GatewayRuntime(
        config=GatewayConfig(
            upstream_servers={
                "filesystem": UpstreamServerConfig(
                    server_id="filesystem",
                    roots_policy=RootsPolicy.CONFIG_ALLOWLIST_ONLY,
                    allowed_roots=["E:\\SoftwareProject\\allowed"],
                )
            }
        ),
        registry=registry,
        tool_executor=executor,
    )
    recommendation = runtime.recommend_capabilities(user_task="read file")
    recommended = recommendation["recommended_capabilities"][0]

    result = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments={"filename": "E:\\SoftwareProject\\outside\\secret.txt"},
    )

    assert result["status"] == "error"
    assert result["error_code"] == "path_not_allowed"
    assert executor.calls == []


def test_call_upstream_tool_allows_path_inside_allowed_roots() -> None:
    capability = make_tool(
        capability_id="filesystem.tools.read_file",
        name="read_file",
        description="Read a local file",
        upstream_server_id="filesystem",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        risk_level=RiskLevel.READ_ONLY,
    )
    registry = CapabilityRegistry()
    registry.add(capability)
    executor = FakeToolExecutor({"ok": True})
    runtime = GatewayRuntime(
        config=GatewayConfig(
            upstream_servers={
                "filesystem": UpstreamServerConfig(
                    server_id="filesystem",
                    roots_policy=RootsPolicy.CONFIG_ALLOWLIST_ONLY,
                    allowed_roots=["E:\\SoftwareProject\\allowed"],
                )
            }
        ),
        registry=registry,
        tool_executor=executor,
    )
    recommendation = runtime.recommend_capabilities(user_task="read file")
    recommended = recommendation["recommended_capabilities"][0]

    result = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments={"path": "E:\\SoftwareProject\\allowed\\README.md"},
    )

    assert result["status"] == "ok"
    assert executor.calls[0][1] == {"path": "E:\\SoftwareProject\\allowed\\README.md"}


def test_call_upstream_tool_rejects_path_when_roots_are_not_configured() -> None:
    capability = make_tool(
        capability_id="filesystem.tools.read_file",
        name="read_file",
        description="Read a local file",
        upstream_server_id="filesystem",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        risk_level=RiskLevel.READ_ONLY,
    )
    registry = CapabilityRegistry()
    registry.add(capability)
    executor = FakeToolExecutor({"ok": True})
    runtime = GatewayRuntime(
        config=GatewayConfig(
            upstream_servers={
                "filesystem": UpstreamServerConfig(
                    server_id="filesystem",
                    roots_policy=RootsPolicy.CONFIG_ALLOWLIST_ONLY,
                )
            }
        ),
        registry=registry,
        tool_executor=executor,
    )
    recommendation = runtime.recommend_capabilities(user_task="read file")
    recommended = recommendation["recommended_capabilities"][0]

    result = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments={"path": "E:\\SoftwareProject\\allowed\\README.md"},
    )

    assert result["status"] == "error"
    assert result["error_code"] == "roots_not_configured"
    assert executor.calls == []


def test_call_upstream_tool_rejects_nested_path_outside_allowed_roots() -> None:
    capability = make_tool(
        capability_id="filesystem.tools.read_file",
        name="read_file",
        description="Read a local file",
        upstream_server_id="filesystem",
        input_schema={
            "type": "object",
            "properties": {
                "request": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                }
            },
            "required": ["request"],
        },
        risk_level=RiskLevel.READ_ONLY,
    )
    registry = CapabilityRegistry()
    registry.add(capability)
    executor = FakeToolExecutor({"ok": True})
    runtime = GatewayRuntime(
        config=GatewayConfig(
            upstream_servers={
                "filesystem": UpstreamServerConfig(
                    server_id="filesystem",
                    roots_policy=RootsPolicy.CONFIG_ALLOWLIST_ONLY,
                    allowed_roots=["E:\\SoftwareProject\\allowed"],
                )
            }
        ),
        registry=registry,
        tool_executor=executor,
    )
    recommendation = runtime.recommend_capabilities(user_task="read file")
    recommended = recommendation["recommended_capabilities"][0]

    result = runtime.call_upstream_tool(
        recommendation_id=recommendation["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments={"request": {"path": "E:\\SoftwareProject\\outside\\secret.txt"}},
    )

    assert result["status"] == "error"
    assert result["error_code"] == "path_not_allowed"
    assert executor.calls == []
