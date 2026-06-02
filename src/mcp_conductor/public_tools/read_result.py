from __future__ import annotations

from typing import Any

from mcp_conductor.runtime import GatewayRuntime


def read_result(
        runtime: GatewayRuntime,
        *,
        result_id: str,
        cursor: str | None = None,
        limit: int = 50,
        session_id: str | None = None,
) -> dict[str, Any]:
    """Read a paginated page from a cached large upstream result."""
    return runtime.read_result(
        result_id=result_id,
        cursor=cursor,
        limit=limit,
        session_id=session_id,
    )
