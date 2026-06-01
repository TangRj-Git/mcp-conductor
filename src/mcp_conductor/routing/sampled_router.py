from __future__ import annotations

"""
routing/sampled_router.py

这个文件是“后续模型筛选能力”的边界占位。

项目前面讨论过：
mcp-conductor 不能自己私自配置模型 API key，也不能绕过外部 Host 自己调用模型。
如果后续需要让模型帮忙做工具筛选，应该走 MCP Sampling：

外部 Host
  -> 管理模型和用户确认
  -> mcp-conductor 通过 Sampling 请求 Host 做一次受控路由判断
  -> Host 可以拒绝、降级或返回模型判断结果

所以这个模块现在不真正实现模型筛选，只保留一个清晰的扩展位置。

当前第一版真实在用的是：
- routing/rules.py：规则筛选。
- routing/recommender.py：生成 recommendation_id 和 route_token。

后续如果接入 Host Sampling，建议在这里补：
1. 构造 Sampling prompt。
2. 把上游能力卡片标记为“不可信上下文”。
3. 调用 primitives/adapter.py 请求 Host Sampling。
4. 解析 Host 返回的候选能力。
5. 失败时回退到 rules.py 的规则筛选。
"""


class HostSampledRouter:
    """
    Host Sampling 路由器占位类。

    这个类表示“可以存在一个由 Host 采样模型辅助的路由器”，
    但第一版还没有真正接通 Host Sampling。

    保留这个类的意义：
    - 让代码结构提前给第二阶段留位置。
    - 明确模型筛选不能在 mcp-conductor 内部私自完成。
    - 防止后续把模型 API key 或模型调用逻辑散落到其他模块里。
    """

    def recommend(self) -> None:
        """
        后续用于返回模型辅助筛选的推荐结果。

        当前直接抛 NotImplementedError，表示：
        - 这个功能还没有进入第一版执行链路。
        - 当前 recommend_capabilities 仍然使用 rules.py 的规则筛选。
        """
        raise NotImplementedError("Host-Sampled Router is a second-stage feature.")
