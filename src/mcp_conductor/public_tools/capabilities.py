from __future__ import annotations

from typing import Any

from mcp_conductor.runtime import GatewayRuntime


def list_upstream_capabilities(
        runtime: GatewayRuntime,
        *,
        cursor: str | None = None,
        limit: int = 50,
        capability_type: str | None = None,
        upstream_server_id: str | None = None,
        query: str | None = None,
) -> dict[str, Any]:
    """List discovered upstream capabilities with pagination metadata."""
    return runtime.list_upstream_capabilities(
        cursor=cursor,
        limit=limit,
        capability_type=capability_type,
        upstream_server_id=upstream_server_id,
        query=query,
    )
