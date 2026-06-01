from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import inspect
from typing import Callable, Protocol
from typing import Any

from .config.loader import load_config
from .config.schema import GatewayConfig, RiskPolicy
from .discovery.service import CapabilityDiscoveryService
from .execution.engine import GatewayExecutionEngine
from .execution.validation import (
    ToolCallValidationInput,
    validate_arguments,
    validate_tool_call,
)
from .models import Capability, CapabilityType, Recommendation, RiskLevel
from .policy.confirmation import PendingActionStore
from .policy.roots import is_path_allowed
from .registry.cards import build_capability_card
from .registry.store import CapabilityRegistry
from .results.manager import ResultManager
from .routing.recommender import build_recommended_capability, create_empty_recommendation
from .routing.rules import select_candidate_cards
from .upstream.manager import UpstreamClientManager


class ToolExecutor(Protocol):
    def call_tool(self, capability: Capability, arguments: dict[str, Any]) -> Any:
        """Call an upstream tool and return its raw result."""


@dataclass(slots=True)
class GatewayRuntime:
    """Coordinates public tools and internal gateway services.

    This class is intentionally thin for the initial project skeleton. Real
    upstream connection, discovery, routing, execution, and result management
    will be wired into this boundary in later implementation steps.
    """

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

    def __post_init__(self) -> None:
        if self.result_manager is None:
            self.result_manager = ResultManager(preview_limit=self.result_preview_limit)

    def startup(self) -> None:
        """Initialize gateway services."""
        self.config = load_config(self.config_path)
        self.upstream_manager = self.upstream_manager_factory(self.config)
        self.upstream_manager.startup()
        if self.tool_executor is None:
            self.tool_executor = GatewayExecutionEngine(self.upstream_manager)

    async def async_startup(self) -> None:
        """Initialize gateway services and discover upstream capabilities."""
        self.config = load_config(self.config_path)
        self.upstream_manager = self.upstream_manager_factory(self.config)
        await self.upstream_manager.astartup()
        self.registry = CapabilityRegistry()
        discovery = CapabilityDiscoveryService(self.upstream_manager)
        for capability in await discovery.discover_async():
            self.registry.add(capability)
        self.discovery_errors = list(discovery.errors)
        if self.tool_executor is None:
            self.tool_executor = GatewayExecutionEngine(self.upstream_manager)

    def shutdown(self) -> None:
        """Release gateway resources."""
        if self.upstream_manager is not None:
            self.upstream_manager.shutdown()

    async def async_shutdown(self) -> None:
        """Release gateway resources created by async_startup."""
        if self.upstream_manager is not None:
            await self.upstream_manager.ashutdown()

    def list_upstream_capabilities(
            self,
            *,
            cursor: str | None = None,
            limit: int = 50,
    ) -> dict[str, Any]:
        capabilities = [
            self._capability_summary(capability)
            for capability in self.registry.list()
            if capability.enabled
        ]
        offset = int(cursor) if cursor else 0
        next_offset = offset + limit
        page = capabilities[offset:next_offset]
        has_more = next_offset < len(capabilities)
        return {
            "status": "ok",
            "capabilities": page,
            "next_cursor": str(next_offset) if has_more else None,
            "has_more": has_more,
            "unavailable_upstreams": self._unavailable_upstream_payload(),
            "discovery_errors": self.discovery_errors,
        }

    def recommend_capabilities(
            self,
            *,
            user_task: str,
            context_summary: str | None = None,
            limit: int = 10,
    ) -> dict[str, Any]:
        del context_summary
        cards = [
            build_capability_card(capability)
            for capability in self.registry.list()
            if capability.enabled
        ]
        selected_cards = select_candidate_cards(cards, user_task=user_task, limit=limit)
        recommendation = create_empty_recommendation()

        for card in selected_cards:
            capability = self.registry.get(card.capability_id)
            if capability.capability_type != CapabilityType.TOOL:
                continue
            if not self._can_recommend_capability(capability):
                continue
            recommendation.recommended_capabilities.append(
                build_recommended_capability(
                    capability_id=capability.capability_id,
                    reason="Matched task terms, capability metadata, or tags.",
                    input_schema=capability.schema_or_metadata,
                )
            )

        self.recommendations[recommendation.recommendation_id] = recommendation
        return {
            "status": "ok",
            "recommendation_id": recommendation.recommendation_id,
            "expires_at": recommendation.expires_at.isoformat(),
            "recommended_capabilities": [
                self._recommended_capability_payload(item)
                for item in recommendation.recommended_capabilities
            ],
        }

    def call_upstream_tool(
            self,
            *,
            recommendation_id: str,
            route_token: str,
            capability_id: str,
            arguments: dict[str, Any],
            pending_action_id: str | None = None,
    ) -> dict[str, Any]:
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
        return self.result_manager.prepare_result(raw_result)

    async def call_upstream_tool_async(
            self,
            *,
            recommendation_id: str,
            route_token: str,
            capability_id: str,
            arguments: dict[str, Any],
            pending_action_id: str | None = None,
    ) -> dict[str, Any]:
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
        return self.result_manager.prepare_result(raw_result)

    def read_result(
            self,
            *,
            result_id: str,
            cursor: str | None = None,
            limit: int = 50,
    ) -> dict[str, Any]:
        assert self.result_manager is not None
        return self.result_manager.read_result(result_id, cursor=cursor, limit=limit)

    def _not_implemented_meta(self, detail: str) -> dict[str, Any]:
        return {
            "implemented": False,
            "detail": detail,
            "config_path": self.config_path,
        }

    def _capability_summary(self, capability: Capability) -> dict[str, Any]:
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

    def _recommended_capability_payload(self, item: Any) -> dict[str, Any]:
        capability = self.registry.get(item.capability_id)
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
            "route_token": item.route_token,
        }

    def _unavailable_upstream_payload(self) -> list[dict[str, str]]:
        if self.upstream_manager is None:
            return []
        startup_errors = getattr(self.upstream_manager, "startup_errors", {})
        return [
            {"upstream_server_id": server_id, "error": error}
            for server_id, error in startup_errors.items()
        ]

    def _prepare_upstream_tool_call(
            self,
            *,
            recommendation_id: str,
            route_token: str,
            capability_id: str,
            arguments: dict[str, Any],
            pending_action_id: str | None = None,
    ) -> Capability | dict[str, Any]:
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
        if capability.capability_type != CapabilityType.TOOL:
            return self._error("invalid_capability_type", "Only tool capabilities can be called.")
        risk_policy = self._risk_policy_for(capability)
        if risk_policy == RiskPolicy.DISABLED:
            return self._risk_policy_denied(capability, risk_policy)

        argument_errors = validate_arguments(arguments, recommended.input_schema)
        if argument_errors:
            return {
                "status": "error",
                "error_code": "invalid_arguments",
                "message": "Arguments do not match the input schema.",
                "details": {"errors": argument_errors},
            }

        roots_error = self._validate_roots_policy(capability, arguments)
        if roots_error is not None:
            return roots_error

        if capability.risk_level != RiskLevel.READ_ONLY:
            if risk_policy != RiskPolicy.CONFIRM_MUTATIONS:
                return self._risk_policy_denied(capability, risk_policy)
            if pending_action_id:
                pending_error = self._validate_pending_action(
                    pending_action_id=pending_action_id,
                    capability=capability,
                    arguments=arguments,
                )
                if pending_error is not None:
                    return pending_error
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
        server_config = self.config.upstream_servers.get(capability.upstream_server_id)
        if server_config is None:
            return RiskPolicy.CONFIRM_MUTATIONS
        return server_config.risk_policy

    def _can_recommend_capability(self, capability: Capability) -> bool:
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
                "details": {
                    "paths": disallowed,
                    "allowed_roots": server_config.allowed_roots,
                },
            }
        return None

    def _extract_path_argument_values(self, arguments: dict[str, Any]) -> list[str]:
        path_keys = {
            "path",
            "paths",
            "file_path",
            "filePath",
            "directory",
            "directory_path",
            "dir_path",
            "cwd",
        }
        values: list[str] = []
        for key, value in arguments.items():
            if key not in path_keys:
                continue
            if isinstance(value, str):
                values.append(value)
            elif isinstance(value, list):
                values.extend(item for item in value if isinstance(item, str))
        return values

    def _error(self, error_code: str, message: str) -> dict[str, Any]:
        return {
            "status": "error",
            "error_code": error_code,
            "message": message,
        }

    def _risk_policy_denied(
            self,
            capability: Capability,
            risk_policy: RiskPolicy,
    ) -> dict[str, Any]:
        return {
            "status": "error",
            "error_code": "risk_policy_denied",
            "message": "The upstream risk policy does not allow this action.",
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
