from __future__ import annotations

from typing import Any

from mcp_conductor.runtime import GatewayRuntime


def list_exposed_capabilities(
        runtime: GatewayRuntime,
        *,
        cursor: str | None = None,
        limit: int = 50,
        include_skipped: bool = False,
) -> dict[str, Any]:
    """List upstream tools selected by the current exposure plan."""
    return runtime.list_exposed_capabilities(
        cursor=cursor,
        limit=limit,
        include_skipped=include_skipped,
    )
