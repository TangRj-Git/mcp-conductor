from __future__ import annotations

from mcp_conductor.models import CapabilityCard, RiskLevel
from mcp_conductor.routing.rules import select_candidate_cards


def make_card(capability_id: str, name: str, description: str = "") -> CapabilityCard:
    return CapabilityCard(
        capability_id=capability_id,
        name=name,
        description=description,
        tags=[],
        risk_level=RiskLevel.READ_ONLY,
        read_only_hint=True,
    )


def test_select_candidate_cards_tokenizes_names_without_substring_false_matches() -> None:
    cards = [
        make_card("profile.tools.profile_checks", "profile_checks"),
        make_card("github.tools.get_pr_checks", "get_pr_checks"),
    ]

    selected = select_candidate_cards(cards, user_task="pr checks", limit=1)

    assert selected[0].capability_id == "github.tools.get_pr_checks"


def test_select_candidate_cards_uses_description_and_tags_for_ranking() -> None:
    cards = [
        make_card("generic.tools.status", "status", "Show generic status"),
        CapabilityCard(
            capability_id="github.tools.get_pr_checks",
            name="get_pr_checks",
            description="Read pull request continuous integration checks",
            tags=["github", "pull-request", "ci"],
            risk_level=RiskLevel.READ_ONLY,
            read_only_hint=True,
        ),
    ]

    selected = select_candidate_cards(cards, user_task="pull request ci checks", limit=1)

    assert selected[0].capability_id == "github.tools.get_pr_checks"


def test_select_candidate_cards_supports_cjk_query_terms() -> None:
    cards = [
        make_card(
            "generic.tools.mcp_reference",
            "mcp_reference",
            "General MCP reference.",
        ),
        make_card(
            "learn.tools.explain_concept",
            "concept_helper",
            "\u6839\u636e\u6982\u5ff5\u540d\u79f0\u89e3\u91ca MCP "
            "\u76f8\u5173\u6982\u5ff5\u3002",
        ),
    ]

    selected = select_candidate_cards(
        cards,
        user_task="\u89e3\u91ca MCP \u6982\u5ff5",
        limit=1,
    )

    assert selected[0].capability_id == "learn.tools.explain_concept"
