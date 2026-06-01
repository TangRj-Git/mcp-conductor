from __future__ import annotations

from mcp_conductor.models import RiskLevel

MUTATING_KEYWORDS = (
    "write",
    "delete",
    "remove",
    "send",
    "publish",
    "create",
    "update",
    "payment",
)

READ_ONLY_KEYWORDS = (
    "read",
    "get",
    "list",
    "show",
    "search",
    "fetch",
    "find",
    "check",
)


def infer_risk_level(name: str, description: str | None = None) -> RiskLevel:
    haystack = f"{name} {description or ''}".lower()
    if any(keyword in haystack for keyword in MUTATING_KEYWORDS):
        return RiskLevel.MUTATING
    if any(keyword in haystack for keyword in READ_ONLY_KEYWORDS):
        return RiskLevel.READ_ONLY
    return RiskLevel.UNKNOWN
