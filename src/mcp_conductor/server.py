from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastmcp import Context, FastMCP

from .public_tools.analyze import analyze_user_task
from .public_tools.call_tool import call_upstream_tool_async
from .public_tools.capabilities import list_upstream_capabilities
from .public_tools.exposure import list_exposed_capabilities
from .public_tools.get_prompt import get_upstream_prompt_async
from .public_tools.read_resource import read_upstream_resource_async
from .public_tools.read_resource_template import read_upstream_resource_template_async
from .public_tools.read_result import read_result
from .public_tools.recommend import recommend_capabilities
from .runtime import GatewayRuntime


def _context_session_id(ctx: Context) -> str | None:
    """Return the FastMCP session id when the current transport exposes one."""
    try:
        return ctx.session_id
    except RuntimeError:
        return None


async def _request_pending_action_confirmation(
        runtime: GatewayRuntime,
        ctx: Context,
        pending_result: dict[str, Any],
        *,
        recommendation_id: str,
        route_token: str,
        capability_id: str,
        arguments: dict[str, Any],
        session_id: str | None,
) -> dict[str, Any]:
    """Ask the host for confirmation and retry the pending action if accepted."""
    pending_action_id = pending_result.get("pending_action_id")
    if not isinstance(pending_action_id, str):
        return pending_result

    try:
        elicitation = await ctx.elicit(
            (
                "Confirm execution of an upstream MCP action. "
                f"Capability: {capability_id}. "
                f"Risk: {pending_result.get('risk_level', 'unknown')}."
            ),
            bool,
            response_title="Confirm action",
            response_description="Return true only after the user approves this action.",
        )
    except Exception:
        return pending_result

    action_accepted = getattr(elicitation, "action", None) == "accept"
    data_accepted = getattr(elicitation, "data", False) is True
    if not action_accepted or not data_accepted:
        return {
            "status": "error",
            "error_code": "confirmation_declined",
            "message": "The host did not confirm the pending action.",
            "pending_action_id": pending_action_id,
        }

    confirmation = runtime.confirm_pending_action(pending_action_id=pending_action_id)
    if confirmation.get("status") != "ok":
        return confirmation

    return await call_upstream_tool_async(
        runtime,
        recommendation_id=recommendation_id,
        route_token=route_token,
        capability_id=capability_id,
        arguments=arguments,
        pending_action_id=pending_action_id,
        session_id=session_id,
    )


def create_server(runtime: GatewayRuntime | None = None) -> FastMCP:
    gateway = runtime or GatewayRuntime()

    @asynccontextmanager
    async def lifespan(_: FastMCP):
        await gateway.async_startup()
        try:
            yield
        finally:
            await gateway.async_shutdown()

    server = FastMCP(
        name="mcp-conductor",
        instructions=(
            "mcp-conductor is a gateway to many configured upstream MCP servers. "
            "When a user task may need external MCP tools, resources, prompts, "
            "documentation, browser, repository, database, filesystem, or other "
            "configured capabilities, call analyze_user_task first. Use each "
            "recommendation's next_public_tool and ready_to_call_arguments to "
            "access the selected upstream capability safely."
        ),
        lifespan=lifespan,
    )

    @server.tool(name="analyze_user_task")
    def analyze_user_task_tool(
            user_task: str,
            context_summary: str | None = None,
            limit: int = 10,
    ) -> dict[str, Any]:
        """Analyze a task and recommend relevant upstream MCP capabilities."""
        return analyze_user_task(
            gateway,
            user_task=user_task,
            context_summary=context_summary,
            limit=limit,
        )

    @server.tool(name="list_upstream_capabilities")
    def list_upstream_capabilities_tool(
            cursor: str | None = None,
            limit: int = 50,
            capability_type: str | None = None,
            upstream_server_id: str | None = None,
            query: str | None = None,
    ) -> dict[str, Any]:
        """List, filter, and count discovered upstream capabilities."""
        return list_upstream_capabilities(
            gateway,
            cursor=cursor,
            limit=limit,
            capability_type=capability_type,
            upstream_server_id=upstream_server_id,
            query=query,
        )

    @server.tool(name="list_exposed_capabilities")
    def list_exposed_capabilities_tool(
            cursor: str | None = None,
            limit: int = 50,
            include_skipped: bool = False,
    ) -> dict[str, Any]:
        """List upstream tools selected by the current exposure plan."""
        return list_exposed_capabilities(
            gateway,
            cursor=cursor,
            limit=limit,
            include_skipped=include_skipped,
        )

    @server.tool(name="recommend_capabilities")
    def recommend_capabilities_tool(
            user_task: str,
            context_summary: str | None = None,
            limit: int = 10,
    ) -> dict[str, Any]:
        """Recommend upstream capabilities and return route-gated next steps."""
        return recommend_capabilities(
            gateway,
            user_task=user_task,
            context_summary=context_summary,
            limit=limit,
        )

    @server.tool(name="call_upstream_tool")
    async def call_upstream_tool_tool(
            recommendation_id: str,
            route_token: str,
            capability_id: str,
            arguments: dict[str, Any],
            ctx: Context,
            pending_action_id: str | None = None,
    ) -> dict[str, Any]:
        """Call a recommended upstream tool after route and policy validation."""
        session_id = _context_session_id(ctx)
        result = await call_upstream_tool_async(
            gateway,
            recommendation_id=recommendation_id,
            route_token=route_token,
            capability_id=capability_id,
            arguments=arguments,
            pending_action_id=pending_action_id,
            session_id=session_id,
        )
        if result.get("status") != "confirmation_required" or pending_action_id is not None:
            return result
        return await _request_pending_action_confirmation(
            gateway,
            ctx,
            result,
            recommendation_id=recommendation_id,
            route_token=route_token,
            capability_id=capability_id,
            arguments=arguments,
            session_id=session_id,
        )

    @server.tool(name="read_upstream_resource")
    async def read_upstream_resource_tool(
            recommendation_id: str,
            route_token: str,
            capability_id: str,
            ctx: Context,
    ) -> dict[str, Any]:
        """Read a recommended upstream resource after route validation."""
        return await read_upstream_resource_async(
            gateway,
            recommendation_id=recommendation_id,
            route_token=route_token,
            capability_id=capability_id,
            session_id=_context_session_id(ctx),
        )

    @server.tool(name="read_upstream_resource_template")
    async def read_upstream_resource_template_tool(
            recommendation_id: str,
            route_token: str,
            capability_id: str,
            arguments: dict[str, Any],
            ctx: Context,
    ) -> dict[str, Any]:
        """Safely expand and read a recommended upstream resource template."""
        return await read_upstream_resource_template_async(
            gateway,
            recommendation_id=recommendation_id,
            route_token=route_token,
            capability_id=capability_id,
            arguments=arguments,
            session_id=_context_session_id(ctx),
        )

    @server.tool(name="get_upstream_prompt")
    async def get_upstream_prompt_tool(
            recommendation_id: str,
            route_token: str,
            capability_id: str,
            ctx: Context,
            arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Get a recommended upstream prompt after route validation."""
        return await get_upstream_prompt_async(
            gateway,
            recommendation_id=recommendation_id,
            route_token=route_token,
            capability_id=capability_id,
            arguments=arguments,
            session_id=_context_session_id(ctx),
        )

    @server.tool(name="read_result")
    def read_result_tool(
            result_id: str,
            ctx: Context,
            cursor: str | None = None,
            limit: int = 50,
    ) -> dict[str, Any]:
        """Read a cached large result through an opaque result_id."""
        return read_result(
            gateway,
            result_id=result_id,
            cursor=cursor,
            limit=limit,
            session_id=_context_session_id(ctx),
        )

    return server
