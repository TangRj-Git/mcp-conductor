from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from mcp_conductor.config.schema import (
    GatewayConfig,
    RiskPolicy,
    RootsPolicy,
    UpstreamServerConfig,
)
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


def make_runtime(
    capability: Capability,
    *,
    executor_result: Any = {"ok": True},
    result_preview_limit: int = 3,
) -> tuple[GatewayRuntime, FakeToolExecutor]:
    registry = CapabilityRegistry()
    registry.add(capability)
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
    )

    assert result["status"] == "ok"
    assert result["truncated"] is True
    assert len(result["preview"]) == 2
    assert result["result_id"].startswith("result_")
    assert executor.calls[0][1] == {"pr_number": 12}

    cached = runtime.read_result(result_id=result["result_id"], limit=10)
    assert cached["status"] == "ok"
    assert len(cached["items"]) == 5


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
