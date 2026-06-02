from __future__ import annotations

from typing import Any

from mcp_conductor.config.schema import (
    ExposureConfig,
    ExposureMode,
    GatewayConfig,
    RiskPolicy,
    UpstreamServerConfig,
)
from mcp_conductor.exposure.planner import plan_exposed_capabilities
from mcp_conductor.models import Capability, CapabilityType, RiskLevel


def make_capability(
    capability_id: str,
    *,
    capability_type: CapabilityType = CapabilityType.TOOL,
    upstream_server_id: str = "github",
    name: str = "get_pr_checks",
    description: str = "Read PR CI checks",
    schema: dict[str, Any] | None = None,
    risk_level: RiskLevel = RiskLevel.READ_ONLY,
    read_only_hint: bool | None = True,
    enabled: bool = True,
) -> Capability:
    return Capability(
        capability_id=capability_id,
        capability_type=capability_type,
        upstream_server_id=upstream_server_id,
        upstream_client_id=upstream_server_id,
        original_name_or_uri=name,
        description=description,
        schema_or_metadata=schema
        or {
            "type": "object",
            "properties": {"pr_number": {"type": "integer"}},
            "required": ["pr_number"],
        },
        tags=["github", "ci"],
        risk_level=risk_level,
        read_only_hint=read_only_hint,
        enabled=enabled,
    )


def test_router_mode_exposes_no_direct_proxy_tools() -> None:
    config = GatewayConfig(
        exposure=ExposureConfig(mode=ExposureMode.ROUTER),
    )

    plan = plan_exposed_capabilities(
        config,
        [make_capability("github.tools.get_pr_checks")],
    )

    assert plan.mode == ExposureMode.ROUTER
    assert plan.dynamic_registration_enabled is False
    assert plan.exposed_capabilities == []


def test_hybrid_mode_exposes_only_allowed_read_only_tools() -> None:
    config = GatewayConfig(
        exposure=ExposureConfig(mode=ExposureMode.HYBRID),
        upstream_servers={
            "github": UpstreamServerConfig(
                server_id="github",
                risk_policy=RiskPolicy.READ_ONLY_ONLY,
            ),
            "filesystem": UpstreamServerConfig(
                server_id="filesystem",
                risk_policy=RiskPolicy.CONFIRM_MUTATIONS,
            ),
            "disabled": UpstreamServerConfig(
                server_id="disabled",
                disabled=True,
            ),
        },
    )

    plan = plan_exposed_capabilities(
        config,
        [
            make_capability("github.tools.get_pr_checks"),
            make_capability(
                "github.resources.readme",
                capability_type=CapabilityType.RESOURCE,
                name="mcp://README.md",
            ),
            make_capability(
                "filesystem.tools.delete_file",
                upstream_server_id="filesystem",
                name="delete_file",
                risk_level=RiskLevel.DESTRUCTIVE,
                read_only_hint=False,
            ),
            make_capability(
                "disabled.tools.list_items",
                upstream_server_id="disabled",
                name="list_items",
            ),
            make_capability(
                "github.tools.disabled_capability",
                name="disabled_capability",
                enabled=False,
            ),
        ],
    )

    assert [item.capability_id for item in plan.exposed_capabilities] == [
        "github.tools.get_pr_checks"
    ]
    assert {item.capability_id for item in plan.skipped_capabilities} == {
        "github.resources.readme",
        "filesystem.tools.delete_file",
        "disabled.tools.list_items",
        "github.tools.disabled_capability",
    }


def test_exposure_filters_include_and_exclude_capabilities() -> None:
    config = GatewayConfig(
        exposure=ExposureConfig(
            mode=ExposureMode.PROXY,
            include_upstreams=["github", "docs"],
            exclude_capabilities=["docs.tools.delete_doc"],
            include_capabilities=["github.tools.get_pr_checks", "read_docs"],
        ),
    )

    plan = plan_exposed_capabilities(
        config,
        [
            make_capability("github.tools.get_pr_checks"),
            make_capability("github.tools.list_issues", name="list_issues"),
            make_capability("docs.tools.read_docs", upstream_server_id="docs", name="read_docs"),
            make_capability(
                "docs.tools.delete_doc",
                upstream_server_id="docs",
                name="delete_doc",
            ),
            make_capability(
                "filesystem.tools.read_file",
                upstream_server_id="filesystem",
                name="read_file",
            ),
        ],
    )

    assert [item.capability_id for item in plan.exposed_capabilities] == [
        "docs.tools.read_docs",
        "github.tools.get_pr_checks",
    ]


def test_exposure_names_are_sanitized_and_collision_safe() -> None:
    config = GatewayConfig(
        exposure=ExposureConfig(mode=ExposureMode.PROXY),
    )

    plan = plan_exposed_capabilities(
        config,
        [
            make_capability(
                "learn-a.tools.get_info",
                upstream_server_id="learn-mcp-server",
                name="get server info",
            ),
            make_capability(
                "learn-b.tools.get_info",
                upstream_server_id="learn_mcp_server",
                name="get-server-info",
            ),
        ],
    )

    assert [item.exposed_name for item in plan.exposed_capabilities] == [
        "learn_mcp_server__get_server_info",
        "learn_mcp_server__get_server_info__2",
    ]


def test_exposure_plan_respects_max_exposed_tools() -> None:
    config = GatewayConfig(
        exposure=ExposureConfig(
            mode=ExposureMode.PROXY,
            max_exposed_tools=1,
        ),
    )

    plan = plan_exposed_capabilities(
        config,
        [
            make_capability("github.tools.a", name="a"),
            make_capability("github.tools.b", name="b"),
        ],
    )

    assert [item.capability_id for item in plan.exposed_capabilities] == ["github.tools.a"]
    assert plan.skipped_capabilities[-1].capability_id == "github.tools.b"
    assert plan.skipped_capabilities[-1].reason == "max_exposed_tools_reached"
