from __future__ import annotations

from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe

from mcp_conductor.models import Recommendation, RecommendedCapability

"""
routing/recommender.py

这个文件负责“推荐凭证”的生成。

它和 routing/rules.py 的区别：
- rules.py 负责从能力卡片里筛出候选项。
- recommender.py 负责把候选项包装成可执行链路需要的推荐结果。

为什么需要 recommendation_id 和 route_token：
外部模型不能随便编一个 capability_id 就让 mcp-conductor 执行。
必须先经过 recommend_capabilities，拿到一次有过期时间的推荐结果。
后续 call_upstream_tool 必须携带：
- recommendation_id
- route_token
- capability_id

这样 execution 层才能确认：
1. 这个工具确实是刚才推荐过的。
2. 调用方没有把推荐结果篡改成另一个工具。
3. 推荐结果没有过期。

这个模块不负责：
- 连接上游 Server。
- 发现能力。
- 判断 risk_policy。
- 执行工具。
"""


def create_empty_recommendation(ttl_seconds: int = 300) -> Recommendation:
    """
    创建一个空的推荐结果容器。

    ttl_seconds 默认是 300 秒，也就是推荐结果 5 分钟后过期。
    这样做是为了避免模型或 Host 之后拿很久以前的推荐凭证继续调用工具。

    这里先创建空列表，后续 runtime.recommend_capabilities 会把
    RecommendedCapability 一个个追加进去。
    """
    return Recommendation(
        recommendation_id=f"rec_{token_urlsafe(16)}",
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        recommended_capabilities=[],
    )


def create_route_token() -> str:
    """
    创建单个推荐能力对应的 route_token。

    route_token 是每个能力自己的调用令牌。
    即使同一个 recommendation_id 里推荐了多个工具，每个工具也应该有不同的 route_token。

    后续执行时，capability_id 和 route_token 必须匹配，才能继续调用。
    """
    return f"route_{token_urlsafe(24)}"


def build_recommended_capability(
        *,
        capability_id: str,
        reason: str,
        input_schema: dict,
) -> RecommendedCapability:
    """
    把一个候选 capability 包装成推荐结果中的一项。

    参数含义：
    - capability_id：能力唯一 ID，例如 github.tools.get_pr_checks。
    - reason：为什么推荐它，给外部模型和调试使用。
    - input_schema：调用这个工具需要的参数 schema。

    返回值里的 route_token 会在这里创建。
    外部 Host / 模型后续调用 call_upstream_tool 时必须把这个 route_token 带回来。
    """
    return RecommendedCapability(
        capability_id=capability_id,
        route_token=create_route_token(),
        reason=reason,
        input_schema=input_schema,
    )
