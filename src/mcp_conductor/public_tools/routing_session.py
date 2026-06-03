from __future__ import annotations

from typing import Any

from mcp_conductor.runtime import GatewayRuntime


def start_routing_session(
        runtime: GatewayRuntime,
        *,
        user_task: str,
        context_summary: str | None = None,
        limit: int = 10,
) -> dict[str, Any]:
    """Start a lightweight routing session for one user task."""
    return runtime.start_routing_session(
        user_task=user_task,
        context_summary=context_summary,
        limit=limit,
    )


def list_routing_session_state(
        runtime: GatewayRuntime,
        *,
        session_id: str,
) -> dict[str, Any]:
    """Return compact routing session state for diagnostics."""
    return runtime.list_routing_session_state(session_id=session_id)


def end_routing_session(
        runtime: GatewayRuntime,
        *,
        session_id: str,
) -> dict[str, Any]:
    """End a routing session and release its in-memory state."""
    return runtime.end_routing_session(session_id=session_id)
