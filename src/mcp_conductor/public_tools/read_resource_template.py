from __future__ import annotations

from typing import Any

from mcp_conductor.runtime import GatewayRuntime


async def read_upstream_resource_template_async(
        runtime: GatewayRuntime,
        *,
        recommendation_id: str,
        route_token: str,
        capability_id: str,
        arguments: dict[str, Any],
        session_id: str | None = None,
) -> dict[str, Any]:
    """Read a recommended upstream resource template after safe expansion."""
    return await runtime.read_upstream_resource_template_async(
        recommendation_id=recommendation_id,
        route_token=route_token,
        capability_id=capability_id,
        arguments=arguments,
        session_id=session_id,
    )
