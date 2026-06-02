from __future__ import annotations

from typing import Any

from mcp_conductor.models import RiskLevel

DESTRUCTIVE_KEYWORDS = (
    "delete",
    "remove",
    "destroy",
    "drop",
    "purge",
    "\u5220\u9664",
    "\u79fb\u9664",
    "\u9500\u6bc1",
    "\u6e05\u7a7a",
)

MUTATING_KEYWORDS = (
    "write",
    "send",
    "publish",
    "create",
    "update",
    "payment",
    "\u5199\u5165",
    "\u53d1\u9001",
    "\u53d1\u5e03",
    "\u521b\u5efa",
    "\u66f4\u65b0",
    "\u652f\u4ed8",
    "\u63d0\u4ea4",
)

HARD_MUTATING_KEYWORDS = (
    "write",
    "send",
    "publish",
    "create",
    "payment",
    "\u5199\u5165",
    "\u53d1\u9001",
    "\u53d1\u5e03",
    "\u521b\u5efa",
    "\u652f\u4ed8",
    "\u63d0\u4ea4",
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
    "explain",
    "compare",
    "summarize",
    "diagnose",
    "suggest",
    "recommend",
    "describe",
    "analyze",
    "\u8bfb\u53d6",
    "\u83b7\u53d6",
    "\u8fd4\u56de",
    "\u5217\u51fa",
    "\u67e5\u627e",
    "\u641c\u7d22",
    "\u68c0\u67e5",
    "\u89e3\u91ca",
    "\u5bf9\u6bd4",
    "\u6bd4\u8f83",
    "\u603b\u7ed3",
    "\u8bca\u65ad",
    "\u5efa\u8bae",
    "\u63a8\u8350",
    "\u7ed9\u51fa",
    "\u751f\u6210",
)


def infer_risk_level(
        name: str,
        description: str | None = None,
        annotations: Any | None = None,
) -> RiskLevel:
    read_only_hint = _annotation_value(annotations, "readOnlyHint")
    if _annotation_value(annotations, "destructiveHint") is True:
        return RiskLevel.DESTRUCTIVE

    haystack = f"{name} {description or ''}".lower()
    if any(keyword in haystack for keyword in DESTRUCTIVE_KEYWORDS):
        return RiskLevel.DESTRUCTIVE
    if any(keyword in haystack for keyword in HARD_MUTATING_KEYWORDS):
        return RiskLevel.MUTATING
    if read_only_hint is True:
        return RiskLevel.READ_ONLY
    if any(keyword in haystack for keyword in MUTATING_KEYWORDS):
        return RiskLevel.MUTATING
    if read_only_hint is False:
        return RiskLevel.UNKNOWN
    if any(keyword in haystack for keyword in READ_ONLY_KEYWORDS):
        return RiskLevel.READ_ONLY
    return RiskLevel.UNKNOWN


def _annotation_value(annotations: Any | None, key: str) -> Any:
    if annotations is None:
        return None
    if isinstance(annotations, dict):
        return annotations.get(key)
    return getattr(annotations, key, None)
