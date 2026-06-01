from __future__ import annotations

from typing import Any

from mcp_conductor.runtime import GatewayRuntime


def call_upstream_tool(
        runtime: GatewayRuntime,
        *,
        recommendation_id: str,
        route_token: str,
        capability_id: str,
        arguments: dict[str, Any],
        pending_action_id: str | None = None,
) -> dict[str, Any]:
    """
    同步调用上游 MCP 工具的执行接口。

    这是 GatewayRuntime.call_upstream_tool() 的公开包装函数，提供统一的工具调用入口。
    执行完整的验证流程（推荐ID、路由令牌、参数schema、风险策略、路径安全等），
    并根据需要触发用户确认机制。

    参数说明：
        runtime: 网关运行时实例，包含所有服务状态和配置
        recommendation_id: 之前 recommend_capabilities() 返回的推荐ID，用于追溯推荐来源
        route_token: 推荐时生成的路由令牌，用于验证调用权限（防篡改）
        capability_id: 要调用的能力唯一标识，格式如 "github.tools.get_pr_checks"
        arguments: 传给上游工具的参数字典，必须符合该工具的 input_schema
        pending_action_id: 非只读操作的用户确认ID，首次调用时为None，确认后传入

    返回值示例：
        成功: {"status": "ok", "data": {...}, "result_id": "res_xxx"}
        需确认: {"status": "confirmation_required", "pending_action_id": "pend_xxx"}
        错误: {"status": "error", "error_code": "xxx", "message": "..."}

    使用场景：
        # 场景1：直接调用只读工具
        result = call_upstream_tool(runtime, recommendation_id="rec_xxx", ...)

        # 场景2：需要用户确认的写操作（首次调用）
        result = call_upstream_tool(runtime, ...)
        if result["status"] == "confirmation_required":
            # 等待用户确认，获取 pending_action_id
            pass

        # 场景3：用户确认后再次调用
        result = call_upstream_tool(runtime, pending_action_id="pend_xxx", ...)

    :param runtime: 网关运行时实例
    :param recommendation_id: 推荐ID，关联之前的推荐结果
    :param route_token: 路由令牌，验证调用权限
    :param capability_id: 能力ID，指定要调用的工具
    :param arguments: 工具调用参数
    :param pending_action_id: 待确认动作ID（可选），用于二次确认
    :return: 包含执行状态、结果或错误信息的字典
    """
    return runtime.call_upstream_tool(
        recommendation_id=recommendation_id,
        route_token=route_token,
        capability_id=capability_id,
        arguments=arguments,
        pending_action_id=pending_action_id,
    )


async def call_upstream_tool_async(
        runtime: GatewayRuntime,
        *,
        recommendation_id: str,
        route_token: str,
        capability_id: str,
        arguments: dict[str, Any],
        pending_action_id: str | None = None,
) -> dict[str, Any]:
    """
    异步调用上游 MCP 工具的执行接口。

    这是 call_upstream_tool() 的异步版本，支持非阻塞的工具调用，
    适合在高并发场景或异步框架中使用。可以配合 asyncio.gather()
    并发执行多个工具调用，提高整体吞吐量。

    参数说明：
        runtime: 网关运行时实例，包含所有服务状态和配置
        recommendation_id: 之前 recommend_capabilities() 返回的推荐ID，用于追溯推荐来源
        route_token: 推荐时生成的路由令牌，用于验证调用权限（防篡改）
        capability_id: 要调用的能力唯一标识，格式如 "github.tools.get_pr_checks"
        arguments: 传给上游工具的参数字典，必须符合该工具的 input_schema
        pending_action_id: 非只读操作的用户确认ID，首次调用时为None，确认后传入

    返回值示例：
        成功: {"status": "ok", "data": {...}, "result_id": "res_xxx"}
        需确认: {"status": "confirmation_required", "pending_action_id": "pend_xxx"}
        错误: {"status": "error", "error_code": "xxx", "message": "..."}

    使用场景：
        # 场景1：单个异步调用
        result = await call_upstream_tool_async(runtime, recommendation_id="rec_xxx", ...)

        # 场景2：并发调用多个工具（提高效率）
        task1 = call_upstream_tool_async(runtime, recommendation_id="rec_1", ...)
        task2 = call_upstream_tool_async(runtime, recommendation_id="rec_2", ...)
        result1, result2 = await asyncio.gather(task1, task2)

        # 场景3：在 FastAPI 等异步框架中使用
        @app.post("/call-tool")
        async def call_tool_endpoint():
            return await call_upstream_tool_async(runtime, ...)

    :param runtime: 网关运行时实例
    :param recommendation_id: 推荐ID，关联之前的推荐结果
    :param route_token: 路由令牌，验证调用权限
    :param capability_id: 能力ID，指定要调用的工具
    :param arguments: 工具调用参数
    :param pending_action_id: 待确认动作ID（可选），用于二次确认
    :return: 包含执行状态、结果或错误信息的字典（协程）
    """
    return await runtime.call_upstream_tool_async(
        recommendation_id=recommendation_id,
        route_token=route_token,
        capability_id=capability_id,
        arguments=arguments,
        pending_action_id=pending_action_id,
    )
