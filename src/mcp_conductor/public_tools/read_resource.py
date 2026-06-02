from __future__ import annotations

from typing import Any

from mcp_conductor.runtime import GatewayRuntime


async def read_upstream_resource_async(
        runtime: GatewayRuntime,
        *,
        recommendation_id: str,
        route_token: str,
        capability_id: str,
        session_id: str | None = None,
) -> dict[str, Any]:
    """Read a recommended upstream resource through runtime validation."""
    return await runtime.read_upstream_resource_async(
        recommendation_id=recommendation_id,
        route_token=route_token,
        capability_id=capability_id,
        session_id=session_id,
    )
