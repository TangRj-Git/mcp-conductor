from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from mcp_conductor.config.schema import ExposureMode, GatewayConfig, RiskPolicy
from mcp_conductor.models import Capability, CapabilityType, RiskLevel
from mcp_conductor.routing.schemas import recommendation_input_schema


@dataclass(slots=True)
class ExposedCapability:
    """One upstream tool selected for a future direct proxy surface."""

    exposed_name: str
    capability_id: str
    upstream_server_id: str
    original_name: str
    description: str | None
    input_schema: dict[str, Any]
    risk_level: str


@dataclass(slots=True)
class SkippedCapability:
    """Records why a discovered capability was not included in the exposure plan."""

    capability_id: str
    reason: str


@dataclass(slots=True)
class ExposurePlan:
    """A deterministic plan for which upstream capabilities may be directly exposed."""

    mode: ExposureMode
    exposed_capabilities: list[ExposedCapability] = field(default_factory=list)
    skipped_capabilities: list[SkippedCapability] = field(default_factory=list)
    dynamic_registration_enabled: bool = False

    def to_payload(self, *, include_skipped: bool = True) -> dict[str, Any]:
        """Convert the plan into a public diagnostic payload."""
        return {
            "mode": self.mode.value,
            "dynamic_registration_enabled": self.dynamic_registration_enabled,
            "exposed_count": len(self.exposed_capabilities),
            "skipped_count": len(self.skipped_capabilities),
            "exposed_capabilities": [
                {
                    "exposed_name": item.exposed_name,
                    "capability_id": item.capability_id,
                    "upstream_server_id": item.upstream_server_id,
                    "original_name": item.original_name,
                    "description": item.description,
                    "input_schema": item.input_schema,
                    "risk_level": item.risk_level,
                }
                for item in self.exposed_capabilities
            ],
            "skipped_capabilities": [
                {
                    "capability_id": item.capability_id,
                    "reason": item.reason,
                }
                for item in self.skipped_capabilities
            ] if include_skipped else [],
        }


def plan_exposed_capabilities(
    config: GatewayConfig,
    capabilities: Iterable[Capability],
) -> ExposurePlan:
    """Build a deterministic direct-exposure plan from config and discovery output."""
    exposure = config.exposure
    plan = ExposurePlan(mode=exposure.mode)
    if exposure.mode == ExposureMode.ROUTER:
        return plan

    used_names: dict[str, int] = {}
    exposed_count = 0
    for capability in sorted(capabilities, key=_capability_sort_key):
        skip_reason = _skip_reason(config, capability)
        if skip_reason is not None:
            plan.skipped_capabilities.append(
                SkippedCapability(
                    capability_id=capability.capability_id,
                    reason=skip_reason,
                )
            )
            continue

        if exposed_count >= exposure.max_exposed_tools:
            plan.skipped_capabilities.append(
                SkippedCapability(
                    capability_id=capability.capability_id,
                    reason="max_exposed_tools_reached",
                )
            )
            continue

        exposed_name = _unique_exposed_name(
            _base_exposed_name(capability),
            used_names,
        )
        plan.exposed_capabilities.append(
            ExposedCapability(
                exposed_name=exposed_name,
                capability_id=capability.capability_id,
                upstream_server_id=capability.upstream_server_id,
                original_name=capability.original_name_or_uri,
                description=capability.description,
                input_schema=recommendation_input_schema(capability),
                risk_level=capability.risk_level.value,
            )
        )
        exposed_count += 1
    return plan


def _skip_reason(config: GatewayConfig, capability: Capability) -> str | None:
    server_config = config.upstream_servers.get(capability.upstream_server_id)
    if server_config is not None and server_config.disabled:
        return "upstream_disabled"
    if server_config is not None and server_config.risk_policy == RiskPolicy.DISABLED:
        return "risk_policy_disabled"
    if not capability.enabled:
        return "capability_disabled"
    if not _matches_exposure_filters(config, capability):
        return "not_included_by_filter"
    if capability.capability_type != CapabilityType.TOOL:
        return "unsupported_capability_type"
    if capability.risk_level != RiskLevel.READ_ONLY:
        return "risk_not_read_only"
    if capability.read_only_hint is False:
        return "read_only_hint_false"
    return None


def _matches_exposure_filters(config: GatewayConfig, capability: Capability) -> bool:
    exposure = config.exposure
    capability_names = {
        capability.capability_id,
        capability.original_name_or_uri,
    }
    if (
        exposure.include_upstreams
        and capability.upstream_server_id not in exposure.include_upstreams
    ):
        return False
    if capability.upstream_server_id in exposure.exclude_upstreams:
        return False
    if (
        exposure.include_capability_types
        and capability.capability_type.value not in exposure.include_capability_types
    ):
        return False
    if capability.capability_type.value in exposure.exclude_capability_types:
        return False
    if exposure.include_capabilities and not capability_names.intersection(
        exposure.include_capabilities,
    ):
        return False
    return not capability_names.intersection(exposure.exclude_capabilities)


def _base_exposed_name(capability: Capability) -> str:
    upstream = _safe_identifier(capability.upstream_server_id, fallback="upstream")
    name = _safe_identifier(capability.original_name_or_uri, fallback="capability")
    return f"{upstream}__{name}"


def _unique_exposed_name(base_name: str, used_names: dict[str, int]) -> str:
    current_count = used_names.get(base_name, 0) + 1
    used_names[base_name] = current_count
    if current_count == 1:
        return base_name
    return f"{base_name}__{current_count}"


def _safe_identifier(value: str, *, fallback: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_]+", "_", value).strip("_").lower()
    if not safe:
        safe = fallback
    if safe[0].isdigit():
        safe = f"mcp_{safe}"
    return safe


def _capability_sort_key(capability: Capability) -> tuple[str, str, str]:
    return (
        capability.upstream_server_id,
        capability.original_name_or_uri,
        capability.capability_id,
    )
