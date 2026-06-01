from __future__ import annotations

from typing import Any

from mcp_conductor.runtime import GatewayRuntime


def read_result(
        runtime: GatewayRuntime,
        *,
        result_id: str,
        cursor: str | None = None,
        limit: int = 50,
) -> dict[str, Any]:
    """
    读取之前缓存的上游工具调用结果。

    这是 GatewayRuntime.read_result() 的公开包装函数，用于分页获取
    大型工具调用的完整结果。当 call_upstream_tool() 返回的结果过大时，
    系统会将结果裁剪并缓存，返回一个 result_id。使用此函数可以通过
    result_id 分批读取完整的缓存结果。

    参数说明：
        runtime: 网关运行时实例，包含结果管理器
        result_id: 之前工具调用返回的结果ID，用于定位缓存的结果
        cursor: 分页游标，首次查询传 None，后续查询使用上次返回的 next_cursor
        limit: 每页返回的最大数据项数量，默认 50

    返回值结构：
        {
            "status": "ok",
            "result_id": "res_xxx",         # 结果ID
            "data": [...],                   # 当前页的数据（分页）
            "total_items": 1000,             # 总数据项数
            "current_page": {
                "offset": 0,                 # 当前页起始位置
                "limit": 50,                 # 当前页大小
                "count": 50                  # 当前页实际返回数量
            },
            "next_cursor": "50",             # 下一页游标，无更多则为 None
            "has_more": True                 # 是否还有更多数据
        }

    使用场景：
        # 场景1：首次读取大型结果
        result = call_upstream_tool(runtime, ...)
        if "result_id" in result:
            # 结果被缓存了，需要分页读取
            cached_result = read_result(
                runtime,
                result_id=result["result_id"]
            )

        # 场景2：自定义每页数量
        page = read_result(runtime, result_id="res_xxx", limit=100)

        # 场景3：翻页读取所有数据
        all_data = []
        cursor = None
        while True:
            page = read_result(runtime, result_id="res_xxx", cursor=cursor, limit=100)
            all_data.extend(page["data"])
            if not page["has_more"]:
                break
            cursor = page["next_cursor"]

        # 场景4：在异步环境中使用
        @app.get("/results/{result_id}")
        async def get_result(result_id: str, cursor: str = None):
            return read_result(runtime, result_id=result_id, cursor=cursor)

    :param runtime: 网关运行时实例
    :param result_id: 缓存结果的唯一标识符
    :param cursor: 分页游标，用于续查（可选）
    :param limit: 每页最大返回数量，默认 50
    :return: 包含分页数据和结果元信息的字典
    """
    return runtime.read_result(result_id=result_id, cursor=cursor, limit=limit)
