from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastmcp import FastMCP

from .public_tools.call_tool import call_upstream_tool_async
from .public_tools.capabilities import list_upstream_capabilities
from .public_tools.read_result import read_result
from .public_tools.recommend import recommend_capabilities
from .runtime import GatewayRuntime


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
            "mcp-conductor 是一个 MCP 网关服务。它对外暴露少量高级工具，"
            "并把通过校验的调用路由到已配置的上游 MCP Server。"
        ),
        lifespan=lifespan,
    )

    @server.tool(name="list_upstream_capabilities")
    def list_upstream_capabilities_tool(
            cursor: str | None = None,
            limit: int = 50,
    ) -> dict[str, Any]:
        """以紧凑摘要形式列出已发现的上游能力。"""
        return list_upstream_capabilities(gateway, cursor=cursor, limit=limit)

    @server.tool(name="recommend_capabilities")
    def recommend_capabilities_tool(
            user_task: str,
            context_summary: str | None = None,
            limit: int = 10,
    ) -> dict[str, Any]:
        """根据用户任务推荐合适的上游能力。"""
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
            pending_action_id: str | None = None,
    ) -> dict[str, Any]:
        """调用已经推荐并通过校验的上游工具。"""
        return await call_upstream_tool_async(
            gateway,
            recommendation_id=recommendation_id,
            route_token=route_token,
            capability_id=capability_id,
            arguments=arguments,
            pending_action_id=pending_action_id,
        )

    @server.tool(name="read_result")
    def read_result_tool(
            result_id: str,
            cursor: str | None = None,
            limit: int = 50,
    ) -> dict[str, Any]:
        """通过不透明 result_id 读取缓存的大结果。"""
        return read_result(gateway, result_id=result_id, cursor=cursor, limit=limit)

    return server
