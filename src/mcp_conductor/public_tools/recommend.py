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
    """
    根据用户任务描述智能推荐匹配的 MCP 能力（工具、资源等）。

    这是 GatewayRuntime.recommend_capabilities() 的公开包装函数，是 MCP 网关
    的核心智能功能。它通过分析用户任务的语义，从已发现的所有上游能力中筛选出
    最相关的候选，并生成带有路由令牌的推荐结果。推荐的 capability 可以直接
    用于后续的 call_upstream_tool() 调用。

    参数说明：
        runtime: 网关运行时实例，包含能力注册表和配置
        user_task: 用户的任务描述文本，如 "检查 PR 的 CI 状态" 或 "列出仓库文件"
        context_summary: 可选的上下文摘要，用于提供更精确的推荐（当前版本未使用）
        limit: 最大返回推荐数量，默认 10，可根据需要调整

    返回值结构：
        {
            "status": "ok",
            "recommendation_id": "rec_abc123",      # 推荐会话ID，调用工具时必须传入
            "expires_at": "2025-01-15T12:00:00Z",   # 推荐过期时间（ISO 格式）
            "recommended_capabilities": [            # 推荐的能力列表（按相关性排序）
                {
                    "capability_id": "github.tools.get_pr_checks",
                    "upstream_server_id": "github",
                    "capability_type": "tool",
                    "name": "get_pr_checks",
                    "reason": "Matched task terms, capability metadata, or tags.",
                    "confidence": 0.95,              # 置信度（0-1）
                    "risk_level": "read_only",       # 风险等级：read_only / destructive / unknown
                    "requires_confirmation": False,  # 是否需要用户确认
                    "input_schema": {...},           # 参数 schema
                    "example_arguments": {...},      # 示例参数
                    "route_token": "tok_xyz789"      # 路由令牌，调用工具时必须传入
                },
                ...
            ]
        }

    使用场景：
        # 场景1：基础推荐 - 根据任务描述获取推荐
        recommendation = recommend_capabilities(
            runtime,
            user_task="检查 PR #42 的 CI 状态"
        )

        # 提取第一个推荐
        first_rec = recommendation["recommended_capabilities"][0]

        # 场景2：限制推荐数量
        top3 = recommend_capabilities(runtime, user_task="...", limit=3)

        # 场景3：完整的推荐 → 调用流程
        # 步骤1：获取推荐
        rec_result = recommend_capabilities(
            runtime,
            user_task="创建一个新的 GitHub Issue"
        )

        # 步骤2：选择推荐的能力
        selected = rec_result["recommended_capabilities"][0]

        # 步骤3：调用工具（使用 recommendation_id 和 route_token）
        call_result = call_upstream_tool(
            runtime=runtime,
            recommendation_id=rec_result["recommendation_id"],  # ← 必须传入
            route_token=selected["route_token"],                # ← 必须传入
            capability_id=selected["capability_id"],
            arguments={"title": "Bug report", "body": "..."}
        )

        # 场景4：处理需要确认的操作
        if selected["requires_confirmation"]:
            print("此操作需要用户确认")
            # 等待用户确认...
            # 首次调用会返回 confirmation_required 和 pending_action_id

        # 场景5：在 AI Agent 中使用
        def agent_execute_task(task_description: str):
            # AI 描述任务 → 获取推荐
            recs = recommend_capabilities(runtime, user_task=task_description)

            # AI 选择合适的工具
            best_tool = recs["recommended_capabilities"][0]

            # AI 生成参数
            args = ai_generate_arguments(best_tool["input_schema"])

            # 执行工具调用
            return call_upstream_tool(
                runtime,
                recommendation_id=recs["recommendation_id"],
                route_token=best_tool["route_token"],
                capability_id=best_tool["capability_id"],
                arguments=args
            )

    :param runtime: 网关运行时实例
    :param user_task: 用户的任务描述文本
    :param context_summary: 上下文摘要（可选，当前未使用）
    :param limit: 最大推荐数量，默认 10
    :return: 包含推荐ID、过期时间和推荐能力列表的字典
    """
    return runtime.recommend_capabilities(
        user_task=user_task,
        context_summary=context_summary,
        limit=limit,
    )
