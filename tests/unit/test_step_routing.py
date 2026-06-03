from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from mcp_conductor.models import Capability, CapabilityType, RiskLevel
from mcp_conductor.registry.store import CapabilityRegistry
from mcp_conductor.routing.session import RoutingSessionStore
from mcp_conductor.runtime import GatewayRuntime


def make_tool(
    capability_id: str,
    *,
    name: str,
    description: str,
    tags: list[str],
    upstream_server_id: str = "demo",
    input_schema: dict[str, Any] | None = None,
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
            "properties": {},
            "additionalProperties": False,
        },
        tags=tags,
        risk_level=RiskLevel.READ_ONLY,
        read_only_hint=True,
        enabled=True,
    )


class FakeToolExecutor:
    def __init__(self, result: Any) -> None:
        self.result = result

    def call_tool(self, capability: Capability, arguments: dict[str, Any]) -> Any:
        return self.result


class FailingToolExecutor:
    def call_tool(self, capability: Capability, arguments: dict[str, Any]) -> Any:
        raise RuntimeError("upstream failed")


def test_routing_session_store_records_step_summaries_and_prunes_expired() -> None:
    store = RoutingSessionStore(ttl_seconds=60, max_recent_steps=2)
    session = store.create(original_task_summary="Investigate a CI failure")

    store.record_step(
        session.session_id,
        step_index=1,
        step_type="tool_result",
        step_content="First result",
    )
    store.record_step(
        session.session_id,
        step_index=2,
        step_type="tool_result",
        step_content="Second result",
    )
    store.record_step(
        session.session_id,
        step_index=3,
        step_type="tool_result",
        step_content="Third result",
    )
    payload_before_expiration = store.to_payload(session.session_id)
    session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    store.prune_expired()

    assert payload_before_expiration is not None
    assert payload_before_expiration["recent_steps"] == [
        {
            "step_index": 2,
            "step_type": "tool_result",
            "step_content_preview": "Second result",
        },
        {
            "step_index": 3,
            "step_type": "tool_result",
            "step_content_preview": "Third result",
        },
    ]
    assert store.get(session.session_id) is None


def test_routing_session_payload_lists_are_snapshots() -> None:
    store = RoutingSessionStore(ttl_seconds=60)
    session = store.create(original_task_summary="Investigate a CI failure")
    store.record_recommendation(session.session_id, ["github.tools.get_pr_checks"])
    session.called_capability_ids.append("github.tools.get_pr_checks")
    session.failed_capability_ids.append("github.tools.retry_failed_job")

    payload = store.to_payload(session.session_id)
    assert payload is not None
    recommended_ids = payload["recommended_capability_ids"]
    called_ids = payload["called_capability_ids"]
    failed_ids = payload["failed_capability_ids"]
    assert isinstance(recommended_ids, list)
    assert isinstance(called_ids, list)
    assert isinstance(failed_ids, list)

    recommended_ids.append("unexpected.recommended")
    called_ids.append("unexpected.called")
    failed_ids.append("unexpected.failed")

    fresh_payload = store.to_payload(session.session_id)
    assert fresh_payload is not None
    assert fresh_payload["recommended_capability_ids"] == [
        "github.tools.get_pr_checks",
    ]
    assert fresh_payload["called_capability_ids"] == [
        "github.tools.get_pr_checks",
    ]
    assert fresh_payload["failed_capability_ids"] == [
        "github.tools.retry_failed_job",
    ]


def test_routing_session_store_payload_rejects_expired_session() -> None:
    store = RoutingSessionStore(ttl_seconds=60)
    session = store.create(original_task_summary="Investigate a CI failure")
    session.expires_at = datetime.now(UTC) - timedelta(seconds=1)

    assert store.to_payload(session.session_id) is None
    assert session.session_id not in store.values


def test_start_routing_session_returns_initial_route_gated_recommendation() -> None:
    registry = CapabilityRegistry()
    registry.add(
        make_tool(
            "github.tools.get_pr_checks",
            name="get_pr_checks",
            description="Read GitHub pull request CI checks",
            tags=["github", "pull", "request", "ci"],
            upstream_server_id="github",
            input_schema={
                "type": "object",
                "properties": {"pr_number": {"type": "integer"}},
                "required": ["pr_number"],
            },
        )
    )
    runtime = GatewayRuntime(registry=registry)

    result = runtime.start_routing_session(
        user_task="Check pull request CI status",
        context_summary="GitHub repository",
        limit=5,
    )
    state = runtime.list_routing_session_state(session_id=result["session_id"])

    assert result["status"] == "ok"
    assert result["session_id"].startswith("session_")
    assert result["recommendation_id"].startswith("rec_")
    assert result["recommended_capabilities"][0]["capability_id"] == (
        "github.tools.get_pr_checks"
    )
    assert result["recommended_capabilities"][0]["next_public_tool"] == (
        "call_upstream_tool"
    )
    assert result["recommended_capabilities"][0]["ready_to_call_arguments"][
        "routing_session_id"
    ] == result["session_id"]
    assert state["recommended_capability_ids"] == ["github.tools.get_pr_checks"]


def test_tool_call_records_successful_routing_session_access() -> None:
    registry = CapabilityRegistry()
    registry.add(
        make_tool(
            "github.tools.get_pr_checks",
            name="get_pr_checks",
            description="Read GitHub pull request CI checks",
            tags=["github", "pull", "request", "ci"],
            upstream_server_id="github",
            input_schema={
                "type": "object",
                "properties": {"pr_number": {"type": "integer"}},
                "required": ["pr_number"],
            },
        )
    )
    runtime = GatewayRuntime(
        registry=registry,
        tool_executor=FakeToolExecutor({"ok": True}),
    )
    session = runtime.start_routing_session(
        user_task="Check pull request CI status",
        limit=1,
    )
    recommended = session["recommended_capabilities"][0]

    result = runtime.call_upstream_tool(
        recommendation_id=session["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments={"pr_number": 12},
        routing_session_id=session["session_id"],
    )
    state = runtime.list_routing_session_state(session_id=session["session_id"])

    assert result["status"] == "ok"
    assert state["called_capability_ids"] == ["github.tools.get_pr_checks"]
    assert state["failed_capability_ids"] == []


def test_tool_call_records_failed_routing_session_access() -> None:
    registry = CapabilityRegistry()
    registry.add(
        make_tool(
            "github.tools.get_pr_checks",
            name="get_pr_checks",
            description="Read GitHub pull request CI checks",
            tags=["github", "pull", "request", "ci"],
            upstream_server_id="github",
            input_schema={
                "type": "object",
                "properties": {"pr_number": {"type": "integer"}},
                "required": ["pr_number"],
            },
        )
    )
    runtime = GatewayRuntime(
        registry=registry,
        tool_executor=FailingToolExecutor(),
    )
    session = runtime.start_routing_session(
        user_task="Check pull request CI status",
        limit=1,
    )
    recommended = session["recommended_capabilities"][0]

    result = runtime.call_upstream_tool(
        recommendation_id=session["recommendation_id"],
        route_token=recommended["route_token"],
        capability_id=recommended["capability_id"],
        arguments={"pr_number": 12},
        routing_session_id=session["session_id"],
    )
    state = runtime.list_routing_session_state(session_id=session["session_id"])

    assert result["status"] == "error"
    assert result["error_code"] == "upstream_tool_error"
    assert state["called_capability_ids"] == []
    assert state["failed_capability_ids"] == ["github.tools.get_pr_checks"]


def test_tool_call_rejects_invalid_routing_session_id() -> None:
    runtime = GatewayRuntime(
        registry=CapabilityRegistry(),
        tool_executor=FakeToolExecutor({"ok": True}),
    )

    result = runtime.call_upstream_tool(
        recommendation_id="rec_missing",
        route_token="route_missing",
        capability_id="github.tools.get_pr_checks",
        arguments={"pr_number": 12},
        routing_session_id="session_missing",
    )

    assert result["status"] == "error"
    assert result["error_code"] == "invalid_routing_session"


def test_analyze_agent_step_routes_using_current_step_content() -> None:
    registry = CapabilityRegistry()
    registry.add(
        make_tool(
            "github.tools.get_pr_checks",
            name="get_pr_checks",
            description="Read GitHub pull request CI checks",
            tags=["github", "pull", "request", "ci"],
            upstream_server_id="github",
        )
    )
    registry.add(
        make_tool(
            "docs.tools.read_documentation",
            name="read_documentation",
            description="Read product documentation and guides",
            tags=["docs", "documentation", "guide"],
            upstream_server_id="docs",
        )
    )
    runtime = GatewayRuntime(registry=registry)
    session = runtime.start_routing_session(
        user_task="Check pull request CI status",
        context_summary="GitHub repository",
        limit=1,
    )

    result = runtime.analyze_agent_step(
        session_id=session["session_id"],
        step_index=2,
        step_type="tool_result",
        step_content="The next step is to read documentation guide material.",
        limit=1,
    )
    state = runtime.list_routing_session_state(session_id=session["session_id"])

    assert result["status"] == "ok"
    assert result["routing_round_id"].startswith("round_")
    assert result["recommendation_id"].startswith("rec_")
    assert result["recommended_capabilities"][0]["capability_id"] == (
        "docs.tools.read_documentation"
    )
    assert state["recent_steps"][-1] == {
        "step_index": 2,
        "step_type": "tool_result",
        "step_content_preview": (
            "The next step is to read documentation guide material."
        ),
    }


def test_analyze_agent_step_deprioritizes_called_capabilities() -> None:
    registry = CapabilityRegistry()
    registry.add(
        make_tool(
            "docs.tools.read_primary_docs",
            name="read_primary_docs",
            description="Read documentation guide material",
            tags=["docs", "documentation", "guide"],
            upstream_server_id="docs",
        )
    )
    registry.add(
        make_tool(
            "docs.tools.read_backup_docs",
            name="read_backup_docs",
            description="Read documentation guide material",
            tags=["docs", "documentation", "guide"],
            upstream_server_id="docs",
        )
    )
    runtime = GatewayRuntime(
        registry=registry,
        tool_executor=FakeToolExecutor({"ok": True}),
    )
    session = runtime.start_routing_session(
        user_task="Read documentation guide material",
        limit=1,
    )
    first_recommendation = session["recommended_capabilities"][0]

    runtime.call_upstream_tool(
        recommendation_id=session["recommendation_id"],
        route_token=first_recommendation["route_token"],
        capability_id=first_recommendation["capability_id"],
        arguments={},
        routing_session_id=session["session_id"],
    )
    next_route = runtime.analyze_agent_step(
        session_id=session["session_id"],
        step_index=2,
        step_type="tool_result",
        step_content="Need more documentation guide material.",
        limit=1,
    )

    assert first_recommendation["capability_id"] == "docs.tools.read_primary_docs"
    assert next_route["recommended_capabilities"][0]["capability_id"] == (
        "docs.tools.read_backup_docs"
    )


def test_analyze_agent_step_deprioritizes_failed_capabilities() -> None:
    registry = CapabilityRegistry()
    registry.add(
        make_tool(
            "docs.tools.read_primary_docs",
            name="read_primary_docs",
            description="Read documentation guide material",
            tags=["docs", "documentation", "guide"],
            upstream_server_id="docs",
        )
    )
    registry.add(
        make_tool(
            "docs.tools.read_backup_docs",
            name="read_backup_docs",
            description="Read documentation guide material",
            tags=["docs", "documentation", "guide"],
            upstream_server_id="docs",
        )
    )
    runtime = GatewayRuntime(
        registry=registry,
        tool_executor=FailingToolExecutor(),
    )
    session = runtime.start_routing_session(
        user_task="Read documentation guide material",
        limit=1,
    )
    first_recommendation = session["recommended_capabilities"][0]

    failed_result = runtime.call_upstream_tool(
        recommendation_id=session["recommendation_id"],
        route_token=first_recommendation["route_token"],
        capability_id=first_recommendation["capability_id"],
        arguments={},
        routing_session_id=session["session_id"],
    )
    next_route = runtime.analyze_agent_step(
        session_id=session["session_id"],
        step_index=2,
        step_type="tool_result",
        step_content="Need more documentation guide material.",
        limit=1,
    )

    assert failed_result["status"] == "error"
    assert first_recommendation["capability_id"] == "docs.tools.read_primary_docs"
    assert next_route["recommended_capabilities"][0]["capability_id"] == (
        "docs.tools.read_backup_docs"
    )


def test_analyze_agent_step_rejects_missing_session() -> None:
    runtime = GatewayRuntime(registry=CapabilityRegistry())

    result = runtime.analyze_agent_step(
        session_id="session_missing",
        step_index=1,
        step_type="tool_result",
        step_content="Need docs",
    )

    assert result["status"] == "error"
    assert result["error_code"] == "invalid_routing_session"


def test_end_routing_session_removes_session_state() -> None:
    runtime = GatewayRuntime(registry=CapabilityRegistry())
    session = runtime.start_routing_session(user_task="Check docs")

    result = runtime.end_routing_session(session_id=session["session_id"])
    state = runtime.list_routing_session_state(session_id=session["session_id"])

    assert result == {
        "status": "ok",
        "session_id": session["session_id"],
        "ended": True,
    }
    assert state["status"] == "error"
    assert state["error_code"] == "invalid_routing_session"
