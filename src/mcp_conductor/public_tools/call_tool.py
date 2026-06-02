from __future__ import annotations

from typing import Any

from mcp_conductor.runtime import GatewayRuntime


def call_upstream_tool(
        runtime: GatewayRuntime,
        *,
        recommendation_id: str,
        route_token: str,
        capability_id: str,
        arguments: dict[str, Any],
        pending_action_id: str | None = None,
        session_id: str | None = None,
) -> dict[str, Any]:
    """Synchronously call an upstream tool through the runtime validation flow."""
    return runtime.call_upstream_tool(
        recommendation_id=recommendation_id,
        route_token=route_token,
        capability_id=capability_id,
        arguments=arguments,
        pending_action_id=pending_action_id,
        session_id=session_id,
    )


async def call_upstream_tool_async(
        runtime: GatewayRuntime,
        *,
        recommendation_id: str,
        route_token: str,
        capability_id: str,
        arguments: dict[str, Any],
        pending_action_id: str | None = None,
        session_id: str | None = None,
) -> dict[str, Any]:
    """Asynchronously call an upstream tool through the runtime validation flow."""
    return await runtime.call_upstream_tool_async(
        recommendation_id=recommendation_id,
        route_token=route_token,
        capability_id=capability_id,
        arguments=arguments,
        pending_action_id=pending_action_id,
        session_id=session_id,
    )
