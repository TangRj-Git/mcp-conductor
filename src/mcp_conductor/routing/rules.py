from __future__ import annotations

from mcp_conductor.models import CapabilityCard

"""
routing/rules.py

这个文件负责“第一版规则筛选”。

它不调用上游工具，也不创建推荐凭证，只做一件事：
根据用户任务 user_task，从已经生成好的 CapabilityCard 列表中挑出更相关的候选能力。

当前实现是很朴素的关键词匹配：
1. 把用户任务拆成 terms。
2. 把每张能力卡片的 name / description / tags / input_summary / output_summary 拼成检索文本。
3. 计算用户任务里的词有多少出现在卡片文本中。
4. 分数越高越靠前；分数相同时保持原始顺序，避免排序结果不稳定。

注意：
- 这里是规则筛选，不是语义筛选。
- 这里不会调用模型。
- 这里不会判断 route_token、risk_policy 或真正执行工具。
- 后续如果加入 BM25、向量检索、语义召回，可以在这个模块旁边新增 semantic.py，
  或者把 select_candidate_cards 扩展为组合召回入口。
"""


def select_candidate_cards(
        cards: list[CapabilityCard],
        *,
        user_task: str,
        limit: int,
) -> list[CapabilityCard]:
    """
    从能力卡片中选出和用户任务最相关的候选项。

    参数含义：
    - cards：候选能力卡片列表，通常来自 registry/cards.py。
    - user_task：用户当前想做的事情，例如“查看 PR 检查结果”。
    - limit：最多返回多少个候选能力。

    返回值：
    - 按相关性排序后的 CapabilityCard 列表。

    这个函数只负责“候选召回和排序”，不负责把候选能力变成最终推荐结果。
    最终的 recommendation_id、route_token 会在 routing/recommender.py 里生成。
    """
    # 将用户任务拆成简单关键词。
    # replace("_", " ") 是为了让类似 get_pr_checks 这种写法也能被拆开一部分。
    # len(term.strip()) >= 2 是为了过滤太短、意义不强的词。
    terms = {
        term.lower()
        for term in user_task.replace("_", " ").split()
        if len(term.strip()) >= 2
    }

    def score(card: CapabilityCard) -> int:
        # haystack 是这张能力卡片可被规则检索的文本。
        # 这里故意使用压缩后的 CapabilityCard，而不是完整 capability schema，
        # 这样可以减少上下文膨胀，也降低把上游不可信描述原样喂给模型的风险。
        haystack = " ".join(
            [
                card.name,
                card.description or "",
                " ".join(card.tags),
                card.input_summary or "",
                card.output_summary or "",
            ]
        ).lower()
        # 当前分数很简单：用户任务中有多少关键词出现在卡片文本里。
        # 后续如果需要更准确，可以换成权重打分、BM25 或语义相似度。
        return sum(1 for term in terms if term in haystack)

    # 保留 index 是为了分数相同时保持输入顺序。
    # 这样每次推荐结果更稳定，测试和调试也更容易。
    scored = [(score(card), index, card) for index, card in enumerate(cards)]
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [card for _, _, card in scored[:limit]]
