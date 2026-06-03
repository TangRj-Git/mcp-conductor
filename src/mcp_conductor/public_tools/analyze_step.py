from __future__ import annotations

from typing import Any

from mcp_conductor.runtime import GatewayRuntime


def analyze_agent_step(
        runtime: GatewayRuntime,
        *,
        session_id: str,
        step_index: int,
        step_type: str,
        step_content: str,
        limit: int = 10,
) -> dict[str, Any]:
    """Analyze one agent-loop step and recommend upstream capabilities."""
    return runtime.analyze_agent_step(
        session_id=session_id,
        step_index=step_index,
        step_type=step_type,
        step_content=step_content,
        limit=limit,
    )
