from __future__ import annotations

from typing import Any

from mcp_conductor.runtime import GatewayRuntime


def recommend_capabilities(
        runtime: GatewayRuntime,
        *,
        user_task: str,
        context_summary: str | None = None,
        limit: int = 10,
) -> dict[str, Any]:
    """Recommend executable upstream tool capabilities for a user task."""
    return runtime.recommend_capabilities(
        user_task=user_task,
        context_summary=context_summary,
        limit=limit,
    )
