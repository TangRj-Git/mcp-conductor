from __future__ import annotations

from typing import Any

from mcp_conductor.runtime import GatewayRuntime


def list_upstream_capabilities(
        runtime: GatewayRuntime,
        *,
        cursor: str | None = None,
        limit: int = 50,
) -> dict[str, Any]:
    """
    列出所有已发现的上游 MCP 服务器能力（工具、资源、模板等）。

    这是 GatewayRuntime.list_upstream_capabilities() 的公开包装函数，
    提供分页查询功能，用于浏览网关发现的所有上游能力。返回的能力信息
    包括能力ID、类型、风险等级、只读标记等元数据，可用于后续的能力
    推荐和调用。

    参数说明：
        runtime: 网关运行时实例，包含已发现的能力注册表
        cursor: 分页游标，首次查询传 None，后续查询使用上次返回的 next_cursor
        limit: 每页返回的最大能力数量，默认 50，可根据需要调整

    返回值结构：
        {
            "status": "ok",
            "capabilities": [              # 能力列表（分页）
                {
                    "capability_id": "github.tools.get_pr_checks",
                    "capability_type": "tool",
                    "upstream_server_id": "github",
                    "name": "get_pr_checks",
                    "description": "Read PR CI checks",
                    "tags": ["pr", "ci"],
                    "risk_level": "read_only",
                    "read_only_hint": True,
                    "enabled": True
                },
                ...
            ],
            "next_cursor": "50",           # 下一页游标，无更多则为 None
            "has_more": True,              # 是否还有更多数据
            "unavailable_upstreams": [],   # 启动失败的上游服务器列表
            "discovery_errors": []         # 能力发现过程中的错误
        }

    使用场景：
        # 场景1：首次查询，获取第一页
        result = list_upstream_capabilities(runtime)

        # 场景2：自定义每页数量
        result = list_upstream_capabilities(runtime, limit=20)

        # 场景3：翻页查询
        if result["has_more"]:
            next_result = list_upstream_capabilities(
                runtime,
                cursor=result["next_cursor"]
            )

        # 场景4：遍历所有能力
        all_capabilities = []
        cursor = None
        while True:
            result = list_upstream_capabilities(runtime, cursor=cursor, limit=100)
            all_capabilities.extend(result["capabilities"])
            if not result["has_more"]:
                break
            cursor = result["next_cursor"]

    :param runtime: 网关运行时实例
    :param cursor: 分页游标，用于续查（可选）
    :param limit: 每页最大返回数量，默认 50
    :return: 包含能力列表、分页信息和错误状态的字典
    """
    return runtime.list_upstream_capabilities(cursor=cursor, limit=limit)
