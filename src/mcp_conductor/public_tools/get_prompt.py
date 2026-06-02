from __future__ import annotations

from typing import Any

from mcp_conductor.runtime import GatewayRuntime


async def get_upstream_prompt_async(
        runtime: GatewayRuntime,
        *,
        recommendation_id: str,
        route_token: str,
        capability_id: str,
        arguments: dict[str, Any] | None = None,
        session_id: str | None = None,
) -> dict[str, Any]:
    """Get a recommended upstream prompt through runtime validation."""
    return await runtime.get_upstream_prompt_async(
        recommendation_id=recommendation_id,
        route_token=route_token,
        capability_id=capability_id,
        arguments=arguments,
        session_id=session_id,
    )
