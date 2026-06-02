from __future__ import annotations

from mcp_conductor.models import RiskLevel
from mcp_conductor.policy.risk import infer_risk_level


def test_infer_risk_level_treats_explain_tools_as_read_only() -> None:
    result = infer_risk_level(
        name="explain_concept",
        description=(
            "\u6839\u636e\u6982\u5ff5\u540d\u79f0\u89e3\u91ca MCP "
            "\u76f8\u5173\u6982\u5ff5\u3002"
        ),
    )

    assert result == RiskLevel.READ_ONLY


def test_infer_risk_level_treats_learning_plan_generation_as_read_only() -> None:
    result = infer_risk_level(
        name="generate_learning_plan",
        description=(
            "\u6839\u636e\u5b66\u4e60\u6c34\u5e73\u751f\u6210 MCP "
            "\u5b66\u4e60\u8ba1\u5212\u3002"
        ),
    )

    assert result == RiskLevel.READ_ONLY


def test_infer_risk_level_keeps_destructive_terms_higher_priority() -> None:
    result = infer_risk_level(
        name="delete_file",
        description="\u5220\u9664\u672c\u5730\u6587\u4ef6\u3002",
    )

    assert result == RiskLevel.DESTRUCTIVE


def test_infer_risk_level_does_not_trust_read_only_hint_over_destructive_terms() -> None:
    result = infer_risk_level(
        name="delete_file",
        description="Delete a local file.",
        annotations={"readOnlyHint": True},
    )

    assert result == RiskLevel.DESTRUCTIVE


def test_infer_risk_level_respects_negative_read_only_hint() -> None:
    result = infer_risk_level(
        name="get_account_state",
        description="Get account state while refreshing remote metadata.",
        annotations={"readOnlyHint": False},
    )

    assert result == RiskLevel.UNKNOWN
