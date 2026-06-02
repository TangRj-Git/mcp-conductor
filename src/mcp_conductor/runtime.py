"""Gateway runtime that coordinates config, discovery, routing, and execution."""

from __future__ import annotations

import inspect
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from .config.loader import load_config
from .config.schema import GatewayConfig, RiskPolicy
from .discovery.service import CapabilityDiscoveryService
from .execution.engine import GatewayExecutionEngine
from .execution.validation import (
    ToolCallValidationInput,
    validate_arguments,
    validate_tool_call,
)
from .exposure.planner import plan_exposed_capabilities
from .models import Capability, CapabilityType, Recommendation, RiskLevel
from .policy.confirmation import PendingActionStore
from .policy.roots import is_path_allowed
from .primitives.templates import expand_resource_template_uri
from .registry.cards import build_capability_card
from .registry.store import CapabilityRegistry
from .results.manager import ResultManager
from .results.pagination import is_valid_limit, parse_cursor
from .routing.recommender import build_recommended_capability, create_empty_recommendation
from .routing.rules import select_candidate_cards
from .routing.schemas import recommendation_input_schema
from .upstream.manager import UpstreamClientManager


class ToolExecutor(Protocol):
    """Minimal interface used by the runtime to execute upstream capabilities."""

    def call_tool(self, capability: Capability, arguments: dict[str, Any]) -> Any:
        """Call the upstream tool and return the raw result."""

    def read_resource(self, capability: Capability) -> Any:
        """Read one upstream resource and return the raw result."""

    def read_resource_uri(self, capability: Capability, uri: str) -> Any:
        """Read one concrete upstream resource URI and return the raw result."""

    def get_prompt(self, capability: Capability, arguments: dict[str, Any]) -> Any:
        """Get one upstream prompt and return the raw result."""


@dataclass(slots=True)
class GatewayRuntime:
    """Main orchestration layer for the mcp-conductor gateway."""

    config_path: str | None = None
    config: GatewayConfig = field(default_factory=GatewayConfig)
    upstream_manager: UpstreamClientManager | None = None
    upstream_manager_factory: Callable[[GatewayConfig], Any] = UpstreamClientManager
    registry: CapabilityRegistry = field(default_factory=CapabilityRegistry)
    tool_executor: ToolExecutor | None = None
    result_preview_limit: int = 20
    result_manager: ResultManager | None = None
    recommendations: dict[str, Recommendation] = field(default_factory=dict)
    pending_actions: PendingActionStore = field(default_factory=PendingActionStore)
    discovery_errors: list[dict[str, str]] = field(default_factory=list)
    _owns_tool_executor: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if self.result_manager is None:
            self.result_manager = ResultManager(preview_limit=self.result_preview_limit)

    def startup(self) -> None:
        """Synchronous startup path used by tests and sync-only callers."""
        self._reset_volatile_state()
        self.config = load_config(self.config_path)
        self.upstream_manager = self.upstream_manager_factory(self.config)
        self.upstream_manager.startup()

        self.registry = CapabilityRegistry()
        discovery = CapabilityDiscoveryService(self.upstream_manager)
        for capability in discovery.discover():
            self.registry.add(capability)
        self.discovery_errors = list(discovery.errors)

        self._install_default_executor()

    async def async_startup(self) -> None:
        """Load config, connect upstreams, discover capabilities, and prepare execution."""
        self._reset_volatile_state()
        self.config = load_config(self.config_path)
        self.upstream_manager = self.upstream_manager_factory(self.config)
        await self.upstream_manager.astartup()

        # Rebuild the registry on each startup so stale session state cannot leak
        # into the current gateway lifecycle.
        self.registry = CapabilityRegistry()
        discovery = CapabilityDiscoveryService(self.upstream_manager)
        for capability in await discovery.discover_async():
            self.registry.add(capability)
        self.discovery_errors = list(discovery.errors)

        self._install_default_executor()

    def shutdown(self) -> None:
        """Release synchronous manager state."""
        if self.upstream_manager is not None:
            self.upstream_manager.shutdown()

    async def async_shutdown(self) -> None:
        """Close connected upstream client sessions."""
        if self.upstream_manager is not None:
            await self.upstream_manager.ashutdown()

    def _install_default_executor(self) -> None:
        """Bind the default executor to the currently active upstream manager."""
        if self.upstream_manager is None:
            return
        if self.tool_executor is None or self._owns_tool_executor:
            self.tool_executor = GatewayExecutionEngine(self.upstream_manager)
            self._owns_tool_executor = True

    def _reset_volatile_state(self) -> None:
        """Clear per-lifecycle credentials and cached results before startup."""
        self.recommendations.clear()
        self.pending_actions = PendingActionStore()
        if self.result_manager is not None:
            self.result_manager.cache.values.clear()

    def list_upstream_capabilities(
            self,
            *,
            cursor: str | None = None,
            limit: int = 50,
            capability_type: str | None = None,
            upstream_server_id: str | None = None,
            query: str | None = None,
    ) -> dict[str, Any]:
        """Return a paginated summary of discovered upstream capabilities."""
        if not is_valid_limit(limit):
            return self._invalid_limit_error()

        capability_type_filter: CapabilityType | None = None
        if capability_type is not None:
            try:
                capability_type_filter = CapabilityType(capability_type)
            except ValueError:
                return self._error(
                    "invalid_capability_type_filter",
                    "The capability_type filter is not supported.",
                )

        enabled_capabilities = [
            capability
            for capability in self.registry.list()
            if capability.enabled
        ]
        filtered_capabilities = [
            capability
            for capability in enabled_capabilities
            if (
                (capability_type_filter is None
                 or capability.capability_type == capability_type_filter)
                and (
                    upstream_server_id is None
                    or capability.upstream_server_id == upstream_server_id
                )
                and (
                    not query
                    or query.casefold() in self._capability_search_text(capability)
                )
            )
        ]

        offset = parse_cursor(cursor)
        if offset is None:
            return self._error("invalid_cursor", "Cursor must be a non-negative integer.")
        next_offset = offset + limit
        page = [
            self._capability_summary(capability)
            for capability in filtered_capabilities[offset:next_offset]
        ]
        has_more = next_offset < len(filtered_capabilities)
        return {
            "status": "ok",
            "capabilities": page,
            "total_count": len(enabled_capabilities),
            "filtered_count": len(filtered_capabilities),
            "type_counts": self._type_counts(enabled_capabilities),
            "upstream_counts": self._upstream_counts(enabled_capabilities),
            "next_cursor": str(next_offset) if has_more else None,
            "has_more": has_more,
            "unavailable_upstreams": self._unavailable_upstream_payload(),
            "discovery_errors": self.discovery_errors,
        }

    def list_exposed_capabilities(
            self,
            *,
            cursor: str | None = None,
            limit: int = 50,
            include_skipped: bool = False,
    ) -> dict[str, Any]:
        """Return the current direct-exposure plan for diagnostic inspection."""
        if not is_valid_limit(limit):
            return self._invalid_limit_error()

        offset = parse_cursor(cursor)
        if offset is None:
            return self._error("invalid_cursor", "Cursor must be a non-negative integer.")

        plan = plan_exposed_capabilities(self.config, self.registry.list())
        payload = plan.to_payload(include_skipped=include_skipped)
        exposed_capabilities = payload["exposed_capabilities"]
        next_offset = offset + limit
        payload["exposed_capabilities"] = exposed_capabilities[offset:next_offset]
        has_more = next_offset < len(exposed_capabilities)
        payload["next_cursor"] = str(next_offset) if has_more else None
        payload["has_more"] = has_more
        payload["status"] = "ok"
        payload["next_step"] = (
            "Use this diagnostic plan to verify exposure config. Dynamic proxy "
            "tool registration is not enabled yet, so use analyze_user_task and "
            "the route-gated public tools for execution."
        )
        return payload

    def recommend_capabilities(
            self,
            *,
            user_task: str,
            context_summary: str | None = None,
            limit: int = 10,
    ) -> dict[str, Any]:
        """Recommend a small set of callable upstream tools for a user task."""
        if not is_valid_limit(limit):
            return self._invalid_limit_error()

        routing_text = user_task
        if context_summary:
            routing_text = f"{user_task}\n{context_summary}"

        self._prune_expired_recommendations()
        actionable_types = {
            CapabilityType.TOOL,
            CapabilityType.RESOURCE,
            CapabilityType.RESOURCE_TEMPLATE,
            CapabilityType.PROMPT,
        }
        candidate_capabilities = [
            capability
            for capability in self.registry.list()
            if (
                capability.enabled
                and capability.capability_type in actionable_types
                and self._can_recommend_capability(capability)
            )
        ]
        cards = [build_capability_card(capability) for capability in candidate_capabilities]
        selected_cards = select_candidate_cards(cards, user_task=routing_text, limit=limit)
        recommendation = create_empty_recommendation()

        for card in selected_cards:
            capability = self.registry.get(card.capability_id)
            input_schema = recommendation_input_schema(capability)
            recommendation.recommended_capabilities.append(
                build_recommended_capability(
                    capability_id=capability.capability_id,
                    reason="Matched task terms, capability metadata, or tags.",
                    input_schema=input_schema,
                    example_arguments=self._example_arguments_for(
                        capability,
                        input_schema,
                    ),
                )
            )

        self.recommendations[recommendation.recommendation_id] = recommendation
        return {
            "status": "ok",
            "recommendation_id": recommendation.recommendation_id,
            "expires_at": recommendation.expires_at.isoformat(),
            "recommended_capabilities": [
                self._recommended_capability_payload(
                    item,
                    recommendation_id=recommendation.recommendation_id,
                )
                for item in recommendation.recommended_capabilities
            ],
            "next_step": (
                "Pick one recommended_capabilities item, then call its "
                "next_public_tool with ready_to_call_arguments."
            ),
        }

    def call_upstream_tool(
            self,
            *,
            recommendation_id: str,
            route_token: str,
            capability_id: str,
            arguments: dict[str, Any],
            pending_action_id: str | None = None,
            session_id: str | None = None,
    ) -> dict[str, Any]:
        """Synchronously validate and execute one upstream tool call."""
        self._prune_expired_state(prune_pending_actions=False)
        try:
            validate_tool_call(
                ToolCallValidationInput(
                    recommendation_id=recommendation_id,
                    route_token=route_token,
                    capability_id=capability_id,
                    arguments=arguments,
                )
            )
        except ValueError as exc:
            return self._error("invalid_tool_call_request", str(exc))

        prepared = self._prepare_upstream_tool_call(
            recommendation_id=recommendation_id,
            route_token=route_token,
            capability_id=capability_id,
            arguments=arguments,
            pending_action_id=pending_action_id,
        )
        if isinstance(prepared, dict):
            return prepared
        capability = prepared

        if self.tool_executor is None:
            return self._error(
                "gateway_execution_not_implemented",
                "No upstream tool executor is configured.",
            )

        try:
            raw_result = self.tool_executor.call_tool(capability, arguments)
        except Exception as exc:
            return self._upstream_tool_error(capability, exc)
        assert self.result_manager is not None
        return self.result_manager.prepare_result(raw_result, session_id=session_id)

    def read_upstream_resource_template(
            self,
            *,
            recommendation_id: str,
            route_token: str,
            capability_id: str,
            arguments: dict[str, Any],
            session_id: str | None = None,
    ) -> dict[str, Any]:
        """Synchronously expand and read a recommended resource template."""
        self._prune_expired_state()
        prepared = self._prepare_recommended_capability_access(
            recommendation_id=recommendation_id,
            route_token=route_token,
            capability_id=capability_id,
            expected_type=CapabilityType.RESOURCE_TEMPLATE,
            arguments=arguments,
        )
        if isinstance(prepared, dict):
            return prepared
        capability = prepared

        read_resource_uri = getattr(self.tool_executor, "read_resource_uri", None)
        if self.tool_executor is None or read_resource_uri is None:
            return self._error(
                "gateway_execution_not_implemented",
                "No upstream resource template executor is configured.",
            )

        uri = expand_resource_template_uri(capability, arguments)
        try:
            raw_result = read_resource_uri(capability, uri)
        except Exception as exc:
            return self._upstream_capability_error(capability, exc)
        assert self.result_manager is not None
        return self.result_manager.prepare_result(raw_result, session_id=session_id)

    async def read_upstream_resource_template_async(
            self,
            *,
            recommendation_id: str,
            route_token: str,
            capability_id: str,
            arguments: dict[str, Any],
            session_id: str | None = None,
    ) -> dict[str, Any]:
        """Asynchronously expand and read a recommended resource template."""
        self._prune_expired_state()
        prepared = self._prepare_recommended_capability_access(
            recommendation_id=recommendation_id,
            route_token=route_token,
            capability_id=capability_id,
            expected_type=CapabilityType.RESOURCE_TEMPLATE,
            arguments=arguments,
        )
        if isinstance(prepared, dict):
            return prepared
        capability = prepared

        if self.tool_executor is None:
            return self._error(
                "gateway_execution_not_implemented",
                "No upstream resource template executor is configured.",
            )

        uri = expand_resource_template_uri(capability, arguments)
        read_resource_uri_async = getattr(self.tool_executor, "read_resource_uri_async", None)
        read_resource_uri = getattr(self.tool_executor, "read_resource_uri", None)
        try:
            if read_resource_uri_async is not None:
                raw_result = await read_resource_uri_async(capability, uri)
            elif read_resource_uri is not None:
                raw_result = read_resource_uri(capability, uri)
                if inspect.isawaitable(raw_result):
                    raw_result = await raw_result
            else:
                return self._error(
                    "gateway_execution_not_implemented",
                    "No upstream resource template executor is configured.",
                )
        except Exception as exc:
            return self._upstream_capability_error(capability, exc)

        assert self.result_manager is not None
        return self.result_manager.prepare_result(raw_result, session_id=session_id)

    def read_upstream_resource(
            self,
            *,
            recommendation_id: str,
            route_token: str,
            capability_id: str,
            session_id: str | None = None,
    ) -> dict[str, Any]:
        """Synchronously read a recommended upstream resource."""
        self._prune_expired_state()
        prepared = self._prepare_recommended_capability_access(
            recommendation_id=recommendation_id,
            route_token=route_token,
            capability_id=capability_id,
            expected_type=CapabilityType.RESOURCE,
        )
        if isinstance(prepared, dict):
            return prepared
        capability = prepared

        read_resource = getattr(self.tool_executor, "read_resource", None)
        if self.tool_executor is None or read_resource is None:
            return self._error(
                "gateway_execution_not_implemented",
                "No upstream resource executor is configured.",
            )

        try:
            raw_result = read_resource(capability)
        except Exception as exc:
            return self._upstream_capability_error(capability, exc)
        assert self.result_manager is not None
        return self.result_manager.prepare_result(raw_result, session_id=session_id)

    async def read_upstream_resource_async(
            self,
            *,
            recommendation_id: str,
            route_token: str,
            capability_id: str,
            session_id: str | None = None,
    ) -> dict[str, Any]:
        """Asynchronously read a recommended upstream resource."""
        self._prune_expired_state()
        prepared = self._prepare_recommended_capability_access(
            recommendation_id=recommendation_id,
            route_token=route_token,
            capability_id=capability_id,
            expected_type=CapabilityType.RESOURCE,
        )
        if isinstance(prepared, dict):
            return prepared
        capability = prepared

        if self.tool_executor is None:
            return self._error(
                "gateway_execution_not_implemented",
                "No upstream resource executor is configured.",
            )

        read_resource_async = getattr(self.tool_executor, "read_resource_async", None)
        read_resource = getattr(self.tool_executor, "read_resource", None)
        try:
            if read_resource_async is not None:
                raw_result = await read_resource_async(capability)
            elif read_resource is not None:
                raw_result = read_resource(capability)
                if inspect.isawaitable(raw_result):
                    raw_result = await raw_result
            else:
                return self._error(
                    "gateway_execution_not_implemented",
                    "No upstream resource executor is configured.",
                )
        except Exception as exc:
            return self._upstream_capability_error(capability, exc)

        assert self.result_manager is not None
        return self.result_manager.prepare_result(raw_result, session_id=session_id)

    def get_upstream_prompt(
            self,
            *,
            recommendation_id: str,
            route_token: str,
            capability_id: str,
            arguments: dict[str, Any] | None = None,
            session_id: str | None = None,
    ) -> dict[str, Any]:
        """Synchronously get a recommended upstream prompt."""
        self._prune_expired_state()
        prompt_arguments = arguments or {}
        prepared = self._prepare_recommended_capability_access(
            recommendation_id=recommendation_id,
            route_token=route_token,
            capability_id=capability_id,
            expected_type=CapabilityType.PROMPT,
            arguments=prompt_arguments,
        )
        if isinstance(prepared, dict):
            return prepared
        capability = prepared

        get_prompt = getattr(self.tool_executor, "get_prompt", None)
        if self.tool_executor is None or get_prompt is None:
            return self._error(
                "gateway_execution_not_implemented",
                "No upstream prompt executor is configured.",
            )

        try:
            raw_result = get_prompt(capability, prompt_arguments)
        except Exception as exc:
            return self._upstream_capability_error(capability, exc)
        assert self.result_manager is not None
        return self.result_manager.prepare_result(raw_result, session_id=session_id)

    async def get_upstream_prompt_async(
            self,
            *,
            recommendation_id: str,
            route_token: str,
            capability_id: str,
            arguments: dict[str, Any] | None = None,
            session_id: str | None = None,
    ) -> dict[str, Any]:
        """Asynchronously get a recommended upstream prompt."""
        self._prune_expired_state()
        prompt_arguments = arguments or {}
        prepared = self._prepare_recommended_capability_access(
            recommendation_id=recommendation_id,
            route_token=route_token,
            capability_id=capability_id,
            expected_type=CapabilityType.PROMPT,
            arguments=prompt_arguments,
        )
        if isinstance(prepared, dict):
            return prepared
        capability = prepared

        if self.tool_executor is None:
            return self._error(
                "gateway_execution_not_implemented",
                "No upstream prompt executor is configured.",
            )

        get_prompt_async = getattr(self.tool_executor, "get_prompt_async", None)
        get_prompt = getattr(self.tool_executor, "get_prompt", None)
        try:
            if get_prompt_async is not None:
                raw_result = await get_prompt_async(capability, prompt_arguments)
            elif get_prompt is not None:
                raw_result = get_prompt(capability, prompt_arguments)
                if inspect.isawaitable(raw_result):
                    raw_result = await raw_result
            else:
                return self._error(
                    "gateway_execution_not_implemented",
                    "No upstream prompt executor is configured.",
                )
        except Exception as exc:
            return self._upstream_capability_error(capability, exc)

        assert self.result_manager is not None
        return self.result_manager.prepare_result(raw_result, session_id=session_id)

    async def call_upstream_tool_async(
            self,
            *,
            recommendation_id: str,
            route_token: str,
            capability_id: str,
            arguments: dict[str, Any],
            pending_action_id: str | None = None,
            session_id: str | None = None,
    ) -> dict[str, Any]:
        """Asynchronously validate and execute one upstream tool call."""
        self._prune_expired_state(prune_pending_actions=False)
        try:
            validate_tool_call(
                ToolCallValidationInput(
                    recommendation_id=recommendation_id,
                    route_token=route_token,
                    capability_id=capability_id,
                    arguments=arguments,
                )
            )
        except ValueError as exc:
            return self._error("invalid_tool_call_request", str(exc))

        prepared = self._prepare_upstream_tool_call(
            recommendation_id=recommendation_id,
            route_token=route_token,
            capability_id=capability_id,
            arguments=arguments,
            pending_action_id=pending_action_id,
        )
        if isinstance(prepared, dict):
            return prepared
        capability = prepared

        if self.tool_executor is None:
            return self._error(
                "gateway_execution_not_implemented",
                "No upstream tool executor is configured.",
            )

        call_tool_async = getattr(self.tool_executor, "call_tool_async", None)
        try:
            if call_tool_async is not None:
                raw_result = await call_tool_async(capability, arguments)
            else:
                raw_result = self.tool_executor.call_tool(capability, arguments)
                if inspect.isawaitable(raw_result):
                    raw_result = await raw_result
        except Exception as exc:
            return self._upstream_tool_error(capability, exc)

        assert self.result_manager is not None
        return self.result_manager.prepare_result(raw_result, session_id=session_id)

    def read_result(
            self,
            *,
            result_id: str,
            cursor: str | None = None,
            limit: int = 50,
            session_id: str | None = None,
    ) -> dict[str, Any]:
        """Read a paginated page from a cached large result."""
        self._prune_expired_state()
        assert self.result_manager is not None
        return self.result_manager.read_result(
            result_id,
            cursor=cursor,
            limit=limit,
            session_id=session_id,
        )

    def confirm_pending_action(self, *, pending_action_id: str) -> dict[str, Any]:
        """Mark a pending action as confirmed by a trusted host integration."""
        pending = self.pending_actions.get(pending_action_id)
        if pending is None:
            return self._error(
                "pending_action_not_found",
                "The pending_action_id is invalid, expired, or already used.",
            )
        if self.pending_actions.is_expired(pending):
            self.pending_actions.remove(pending_action_id)
            return self._error(
                "pending_action_expired",
                "The pending action has expired.",
            )
        pending.confirmed = True
        return {
            "status": "ok",
            "pending_action_id": pending.pending_action_id,
            "expires_at": pending.expires_at.isoformat(),
            "capability_id": pending.capability_id,
            "risk_level": pending.risk_level.value,
        }

    def _not_implemented_meta(self, detail: str) -> dict[str, Any]:
        """Build a consistent metadata payload for reserved features."""
        return {
            "implemented": False,
            "detail": detail,
            "config_path": self.config_path,
        }

    def _capability_summary(self, capability: Capability) -> dict[str, Any]:
        """Convert an internal capability into the external list payload."""
        return {
            "capability_id": capability.capability_id,
            "capability_type": capability.capability_type.value,
            "upstream_server_id": capability.upstream_server_id,
            "name": capability.original_name_or_uri,
            "description": capability.description,
            "tags": capability.tags,
            "risk_level": capability.risk_level.value,
            "read_only_hint": capability.read_only_hint,
            "enabled": capability.enabled,
        }

    def _recommended_capability_payload(
            self,
            item: Any,
            *,
            recommendation_id: str,
    ) -> dict[str, Any]:
        """Convert one recommendation entry into the external payload."""
        capability = self.registry.get(item.capability_id)
        next_public_tool = self._next_public_tool(capability.capability_type)
        return {
            "capability_id": item.capability_id,
            "upstream_server_id": capability.upstream_server_id,
            "capability_type": capability.capability_type.value,
            "name": capability.original_name_or_uri,
            "reason": item.reason,
            "confidence": item.confidence,
            "risk_level": capability.risk_level.value,
            "requires_confirmation": capability.risk_level != RiskLevel.READ_ONLY,
            "input_schema": item.input_schema,
            "example_arguments": item.example_arguments,
            "next_public_tool": next_public_tool,
            "ready_to_call_arguments": self._ready_to_call_arguments(
                recommendation_id=recommendation_id,
                route_token=item.route_token,
                capability=capability,
                example_arguments=item.example_arguments,
            ),
            "usage_hint": self._usage_hint(capability, next_public_tool),
            "route_token": item.route_token,
        }

    def _next_public_tool(self, capability_type: CapabilityType) -> str:
        """Return the public gateway tool used to access a recommended capability."""
        return {
            CapabilityType.TOOL: "call_upstream_tool",
            CapabilityType.RESOURCE: "read_upstream_resource",
            CapabilityType.RESOURCE_TEMPLATE: "read_upstream_resource_template",
            CapabilityType.PROMPT: "get_upstream_prompt",
        }[capability_type]

    def _ready_to_call_arguments(
            self,
            *,
            recommendation_id: str,
            route_token: str,
            capability: Capability,
            example_arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the exact argument envelope for the next public tool."""
        arguments: dict[str, Any] = {
            "recommendation_id": recommendation_id,
            "route_token": route_token,
            "capability_id": capability.capability_id,
        }
        if capability.capability_type in {
            CapabilityType.TOOL,
            CapabilityType.RESOURCE_TEMPLATE,
            CapabilityType.PROMPT,
        }:
            arguments["arguments"] = example_arguments
        return arguments

    def _usage_hint(self, capability: Capability, next_public_tool: str) -> str:
        """Give the model a short instruction for continuing after recommendation."""
        return (
            f"Use {next_public_tool} with ready_to_call_arguments to access "
            f"{capability.capability_type.value} capability "
            f"{capability.capability_id}."
        )

    def _type_counts(self, capabilities: list[Capability]) -> dict[str, int]:
        counts = Counter(capability.capability_type.value for capability in capabilities)
        return dict(sorted(counts.items()))

    def _upstream_counts(self, capabilities: list[Capability]) -> dict[str, int]:
        counts = Counter(capability.upstream_server_id for capability in capabilities)
        return dict(sorted(counts.items()))

    def _capability_search_text(self, capability: Capability) -> str:
        """Return normalized text used by capability listing filters."""
        parts = [
            capability.capability_id,
            capability.capability_type.value,
            capability.upstream_server_id,
            capability.original_name_or_uri,
            capability.description or "",
            " ".join(capability.tags),
        ]
        return " ".join(parts).casefold()

    def _example_arguments_for(
            self,
            capability: Capability,
            input_schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Create minimal example arguments that satisfy the recommendation schema."""
        properties = input_schema.get("properties", {})
        if not isinstance(properties, dict):
            return {}
        required = input_schema.get("required", [])
        if not isinstance(required, list):
            required = []
        examples: dict[str, Any] = {}
        for property_name in required:
            property_schema = properties.get(property_name, {})
            if not isinstance(property_schema, dict):
                property_schema = {}
            examples[str(property_name)] = self._example_value_for_schema(
                capability,
                str(property_name),
                property_schema,
            )
        return examples

    def _example_value_for_schema(
            self,
            capability: Capability,
            property_name: str,
            property_schema: dict[str, Any],
    ) -> Any:
        """Choose a conservative example value for one JSON Schema property."""
        property_schema = self._select_example_schema(property_schema)
        if "default" in property_schema:
            return property_schema["default"]
        if "const" in property_schema:
            return property_schema["const"]
        enum = property_schema.get("enum")
        if isinstance(enum, list) and enum:
            return enum[0]

        property_name_lower = property_name.casefold()
        capability_text = (
            f"{capability.original_name_or_uri} {capability.description or ''}"
        ).casefold()
        if property_name_lower in {"topic", "subject"}:
            return "tools"
        if property_name_lower in {"level", "audience"}:
            return "beginner"
        if property_name_lower in {"name", "concept"}:
            if "examples" in capability_text:
                return "basic-tool"
            if "concept" in capability_text:
                return "tool"
            if "docs" in capability_text:
                return "tools"
            return "example"

        schema_type = self._schema_type(property_schema)
        if schema_type == "object":
            nested_properties = property_schema.get("properties", {})
            nested_required = property_schema.get("required", [])
            if not isinstance(nested_properties, dict) or not isinstance(
                    nested_required,
                    list,
            ):
                return {}
            return {
                str(nested_name): self._example_value_for_schema(
                    capability,
                    str(nested_name),
                    nested_properties.get(nested_name, {}),
                )
                for nested_name in nested_required
                if isinstance(nested_properties.get(nested_name, {}), dict)
            }
        if schema_type == "array":
            item_schema = property_schema.get("items", {})
            if not isinstance(item_schema, dict):
                item_schema = {}
            min_items = property_schema.get("minItems", 1)
            max_items = property_schema.get("maxItems")
            item_count = min_items if isinstance(min_items, int) else 1
            item_count = max(item_count, 1)
            if isinstance(max_items, int):
                item_count = min(item_count, max_items)
            return [
                self._example_value_for_schema(
                    capability,
                    property_name,
                    item_schema,
                )
                for _ in range(max(item_count, 0))
            ]
        if schema_type == "string":
            min_length = property_schema.get("minLength")
            max_length = property_schema.get("maxLength")
            value = "example"
            if isinstance(min_length, int) and len(value) < min_length:
                value = "x" * min_length
            if isinstance(max_length, int):
                value = value[:max_length]
            return value
        if schema_type == "integer":
            minimum = property_schema.get("minimum")
            return minimum if isinstance(minimum, int) else 1
        if schema_type == "number":
            minimum = property_schema.get("minimum")
            return minimum if isinstance(minimum, int | float) else 1
        if schema_type == "boolean":
            return True
        return "example"

    def _select_example_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        """Choose the first concrete branch from common JSON Schema combinators."""
        for key in ("oneOf", "anyOf", "allOf"):
            candidates = schema.get(key)
            if isinstance(candidates, list) and candidates:
                first = candidates[0]
                if isinstance(first, dict):
                    merged = {
                        item_key: item_value
                        for item_key, item_value in schema.items()
                        if item_key not in {"oneOf", "anyOf", "allOf"}
                    }
                    merged.update(first)
                    return merged
        return schema

    def _schema_type(self, schema: dict[str, Any]) -> str:
        """Infer a practical JSON type for example generation."""
        schema_type = schema.get("type")
        if isinstance(schema_type, list):
            return next(
                (str(item) for item in schema_type if item != "null"),
                str(schema_type[0]) if schema_type else "string",
            )
        if isinstance(schema_type, str):
            return schema_type
        if "properties" in schema or "required" in schema:
            return "object"
        if "items" in schema:
            return "array"
        return "string"

    def _unavailable_upstream_payload(self) -> list[dict[str, str]]:
        """Expose upstream startup failures in the capability listing response."""
        if self.upstream_manager is None:
            return []
        startup_errors = getattr(self.upstream_manager, "startup_errors", {})
        return [
            {"upstream_server_id": server_id, "error": error}
            for server_id, error in startup_errors.items()
        ]

    def _prepare_recommended_capability_access(
            self,
            *,
            recommendation_id: str,
            route_token: str,
            capability_id: str,
            expected_type: CapabilityType,
            arguments: dict[str, Any] | None = None,
    ) -> Capability | dict[str, Any]:
        """Validate a route-token access request for a read-only capability."""
        recommendation = self.recommendations.get(recommendation_id)
        if recommendation is None:
            return self._error("invalid_recommendation_id", "The recommendation_id is invalid.")
        if recommendation.expires_at <= datetime.now(UTC):
            return self._error("recommendation_expired", "The recommendation has expired.")

        recommended = next(
            (
                item
                for item in recommendation.recommended_capabilities
                if item.capability_id == capability_id
            ),
            None,
        )
        if recommended is None:
            return self._error(
                "capability_not_recommended",
                "The capability_id is not part of this recommendation.",
            )
        if recommended.route_token != route_token:
            return self._error("invalid_route_token", "The route token is invalid or expired.")

        capability = self.registry.get(capability_id)
        if not capability.enabled:
            return self._error("capability_disabled", "The capability is disabled.")
        if capability.capability_type != expected_type:
            return self._error(
                "invalid_capability_type",
                f"Only {expected_type.value} capabilities can be used by this tool.",
            )
        risk_policy = self._risk_policy_for(capability)
        if risk_policy == RiskPolicy.DISABLED or capability.risk_level != RiskLevel.READ_ONLY:
            return self._risk_policy_denied(capability, risk_policy)

        if arguments is not None:
            argument_errors = validate_arguments(arguments, recommended.input_schema)
            if argument_errors:
                return self._invalid_arguments_error(argument_errors)
        return capability

    def _prepare_upstream_tool_call(
            self,
            *,
            recommendation_id: str,
            route_token: str,
            capability_id: str,
            arguments: dict[str, Any],
            pending_action_id: str | None = None,
    ) -> Capability | dict[str, Any]:
        """Run all pre-execution validation before reaching an upstream server."""
        recommendation = self.recommendations.get(recommendation_id)
        if recommendation is None:
            return self._error("invalid_recommendation_id", "The recommendation_id is invalid.")
        if recommendation.expires_at <= datetime.now(UTC):
            return self._error("recommendation_expired", "The recommendation has expired.")

        # Only capabilities from the active recommendation may be called.
        recommended = next(
            (
                item
                for item in recommendation.recommended_capabilities
                if item.capability_id == capability_id
            ),
            None,
        )
        if recommended is None:
            return self._error(
                "capability_not_recommended",
                "The capability_id is not part of this recommendation.",
            )
        if recommended.route_token != route_token:
            return self._error("invalid_route_token", "The route token is invalid or expired.")

        capability = self.registry.get(capability_id)
        if not capability.enabled:
            return self._error("capability_disabled", "The capability is disabled.")
        if capability.capability_type != CapabilityType.TOOL:
            return self._error("invalid_capability_type", "Only tool capabilities can be called.")
        risk_policy = self._risk_policy_for(capability)
        if risk_policy == RiskPolicy.DISABLED:
            return self._risk_policy_denied(capability, risk_policy)

        argument_errors = validate_arguments(arguments, recommended.input_schema)
        if argument_errors:
            return self._invalid_arguments_error(argument_errors)

        roots_error = self._validate_roots_policy(capability, arguments)
        if roots_error is not None:
            return roots_error

        if capability.risk_level != RiskLevel.READ_ONLY:
            if risk_policy != RiskPolicy.CONFIRM_MUTATIONS:
                return self._risk_policy_denied(capability, risk_policy)
            if pending_action_id:
                # A pending action id names a record; it is not proof of
                # confirmation until the host has explicitly marked it confirmed.
                pending_error = self._validate_pending_action(
                    pending_action_id=pending_action_id,
                    capability=capability,
                    arguments=arguments,
                )
                if pending_error is not None:
                    return pending_error
                pending = self.pending_actions.get(pending_action_id)
                if pending is None or not pending.confirmed:
                    return self._error(
                        "confirmation_not_completed",
                        "The pending action has not been confirmed by the host.",
                    )
                # Confirmed mutation calls are single-use to prevent replay.
                self.pending_actions.remove(pending_action_id)
                return capability

            pending = self.pending_actions.create(
                capability_id=capability.capability_id,
                arguments=arguments,
                risk_level=capability.risk_level,
            )
            return {
                "status": "confirmation_required",
                "pending_action_id": pending.pending_action_id,
                "expires_at": pending.expires_at.isoformat(),
                "capability_id": capability.capability_id,
                "risk_level": capability.risk_level.value,
                "arguments_preview": arguments,
                "message": "User confirmation is required before this action can run.",
            }

        return capability

    def _risk_policy_for(self, capability: Capability) -> RiskPolicy:
        """Return the configured risk policy for the capability's upstream server."""
        server_config = self.config.upstream_servers.get(capability.upstream_server_id)
        if server_config is None:
            return RiskPolicy.CONFIRM_MUTATIONS
        return server_config.risk_policy

    def _can_recommend_capability(self, capability: Capability) -> bool:
        """Decide whether a capability is allowed to appear in recommendations."""
        risk_policy = self._risk_policy_for(capability)
        if risk_policy == RiskPolicy.DISABLED:
            return False
        if capability.risk_level == RiskLevel.READ_ONLY:
            return True
        return risk_policy == RiskPolicy.CONFIRM_MUTATIONS

    def _validate_pending_action(
            self,
            *,
            pending_action_id: str,
            capability: Capability,
            arguments: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Validate that a pending action belongs to this exact risky call."""
        pending = self.pending_actions.get(pending_action_id)
        if pending is None:
            return self._error(
                "pending_action_not_found",
                "The pending_action_id is invalid, expired, or already used.",
            )
        if self.pending_actions.is_expired(pending):
            self.pending_actions.remove(pending_action_id)
            return self._error(
                "pending_action_expired",
                "The pending action has expired.",
            )
        if pending.capability_id != capability.capability_id:
            return self._error(
                "pending_action_capability_mismatch",
                "The pending action does not match this capability.",
            )
        if pending.arguments != arguments:
            return self._error(
                "pending_action_arguments_changed",
                "Arguments must match the original pending action.",
            )
        if pending.risk_level != capability.risk_level:
            return self._error(
                "pending_action_risk_changed",
                "The capability risk level changed after confirmation was requested.",
            )
        return None

    def _validate_roots_policy(
            self,
            capability: Capability,
            arguments: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Validate path-like arguments against configured allowed roots."""
        server_config = self.config.upstream_servers.get(capability.upstream_server_id)
        if server_config is None:
            return None
        if server_config.roots_policy is None and not server_config.allowed_roots:
            return None

        path_values = self._extract_path_argument_values(arguments)
        if not path_values:
            return None
        if not server_config.allowed_roots:
            return self._error(
                "roots_not_configured",
                "This capability uses path arguments but no allowed_roots are configured.",
            )

        disallowed = [
            path
            for path in path_values
            if not is_path_allowed(path, server_config.allowed_roots)
        ]
        if disallowed:
            return {
                "status": "error",
                "error_code": "path_not_allowed",
                "message": "One or more path arguments are outside allowed_roots.",
                "next_step": (
                    "Use a path inside allowed_roots, or update the upstream "
                    "server allowed_roots configuration before retrying."
                ),
                "details": {
                    "paths": disallowed,
                    "allowed_roots": server_config.allowed_roots,
                },
            }
        return None

    def _extract_path_argument_values(self, arguments: dict[str, Any]) -> list[str]:
        """Extract common path-like argument values for roots policy checks."""
        path_keys = {
            "dest",
            "destination",
            "destination_path",
            "destinationPath",
            "path",
            "paths",
            "file",
            "filename",
            "fileName",
            "file_path",
            "filePath",
            "input",
            "input_path",
            "inputPath",
            "output",
            "output_path",
            "outputPath",
            "source",
            "source_path",
            "sourcePath",
            "target",
            "target_path",
            "targetPath",
            "directory",
            "directory_path",
            "dir_path",
            "cwd",
        }
        values: list[str] = []

        def visit(value: Any, key: str | None = None) -> None:
            if isinstance(value, dict):
                for nested_key, nested_value in value.items():
                    visit(nested_value, str(nested_key))
                return
            if isinstance(value, list):
                for item in value:
                    visit(item, key)
                return
            if key in path_keys and isinstance(value, str):
                values.append(value)

        visit(arguments)
        return values

    def _prune_expired_recommendations(self) -> None:
        now = datetime.now(UTC)
        expired_ids = [
            recommendation_id
            for recommendation_id, recommendation in self.recommendations.items()
            if recommendation.expires_at <= now
        ]
        for recommendation_id in expired_ids:
            self.recommendations.pop(recommendation_id, None)

    def _prune_expired_state(self, *, prune_pending_actions: bool = True) -> None:
        self._prune_expired_recommendations()
        if prune_pending_actions:
            self.pending_actions.prune_expired()
        if self.result_manager is not None:
            self.result_manager.cache.prune_expired()

    def _invalid_limit_error(self) -> dict[str, Any]:
        return self._error(
            "invalid_limit",
            "Limit must be an integer between 1 and 200.",
        )

    def _error(self, error_code: str, message: str) -> dict[str, Any]:
        """Build a simple structured error response."""
        error = {
            "status": "error",
            "error_code": error_code,
            "message": message,
        }
        next_step = self._next_step_for_error(error_code)
        if next_step:
            error["next_step"] = next_step
        return error

    def _invalid_arguments_error(self, errors: list[str]) -> dict[str, Any]:
        return {
            "status": "error",
            "error_code": "invalid_arguments",
            "message": "Arguments do not match the input schema.",
            "next_step": (
                "Read the recommended capability input_schema, then retry the "
                "same next_public_tool with corrected arguments."
            ),
            "details": {"errors": errors},
        }

    def _next_step_for_error(self, error_code: str) -> str | None:
        """Return model-facing recovery guidance for common gateway errors."""
        next_steps = {
            "invalid_recommendation_id": (
                "Call analyze_user_task or recommend_capabilities again and use "
                "the new recommendation_id."
            ),
            "recommendation_expired": (
                "Call analyze_user_task or recommend_capabilities again because "
                "route tokens are short-lived."
            ),
            "capability_not_recommended": (
                "Use a capability_id from the current recommended_capabilities "
                "list, or request a new recommendation."
            ),
            "invalid_route_token": (
                "Use the route_token returned for this exact capability_id, or "
                "call analyze_user_task again for a fresh token."
            ),
            "invalid_capability_type": (
                "Use the recommended next_public_tool for this capability_type "
                "instead of the current public tool."
            ),
            "invalid_capability_type_filter": (
                "Use one of: tool, resource, resource_template, prompt."
            ),
            "risk_policy_denied": (
                "Change the upstream risk_policy only if this capability should "
                "be allowed, then request a new recommendation."
            ),
            "confirmation_not_completed": (
                "Confirm the pending action through the host before retrying "
                "with the same pending_action_id."
            ),
            "pending_action_not_found": (
                "Start over with a new tool call; pending actions are short-lived "
                "and single-use."
            ),
            "pending_action_expired": (
                "Start over with a new tool call and complete confirmation before "
                "the pending action expires."
            ),
            "pending_action_arguments_changed": (
                "Retry with the original arguments or create a new pending action."
            ),
            "roots_not_configured": (
                "Configure allowed_roots for this upstream server before using "
                "path-like arguments."
            ),
            "invalid_cursor": "Use the next_cursor returned by the previous page.",
            "invalid_limit": "Use a limit between 1 and 200.",
        }
        return next_steps.get(error_code)

    def _risk_policy_denied(
            self,
            capability: Capability,
            risk_policy: RiskPolicy,
    ) -> dict[str, Any]:
        """Build a structured error for risk policy denials."""
        return {
            "status": "error",
            "error_code": "risk_policy_denied",
            "message": "The upstream risk policy does not allow this action.",
            "next_step": (
                "Change the upstream risk_policy only if this capability should "
                "be allowed, then request a new recommendation."
            ),
            "details": {
                "capability_id": capability.capability_id,
                "upstream_server_id": capability.upstream_server_id,
                "risk_level": capability.risk_level.value,
                "risk_policy": risk_policy.value,
            },
        }

    def _upstream_tool_error(
            self,
            capability: Capability,
            exc: Exception,
    ) -> dict[str, Any]:
        """Wrap upstream tool exceptions so they do not escape to the host."""
        return {
            "status": "error",
            "error_code": "upstream_tool_error",
            "message": "Upstream tool call failed.",
            "details": {
                "capability_id": capability.capability_id,
                "upstream_server_id": capability.upstream_server_id,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        }

    def _upstream_capability_error(
            self,
            capability: Capability,
            exc: Exception,
    ) -> dict[str, Any]:
        """Wrap upstream read/prompt exceptions so they stay structured."""
        return {
            "status": "error",
            "error_code": "upstream_capability_error",
            "message": "Upstream capability access failed.",
            "details": {
                "capability_id": capability.capability_id,
                "upstream_server_id": capability.upstream_server_id,
                "capability_type": capability.capability_type.value,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        }
