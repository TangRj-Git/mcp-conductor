"""Helpers that turn selected capabilities into executable recommendations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe

from mcp_conductor.models import Recommendation, RecommendedCapability


def create_empty_recommendation(ttl_seconds: int = 300) -> Recommendation:
    """Create a recommendation container with a short-lived id."""
    return Recommendation(
        recommendation_id=f"rec_{token_urlsafe(16)}",
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        recommended_capabilities=[],
    )


def create_route_token() -> str:
    """Create a per-capability token that must be returned during execution."""
    return f"route_{token_urlsafe(24)}"


def build_recommended_capability(
        *,
        capability_id: str,
        reason: str,
        input_schema: dict,
        example_arguments: dict | None = None,
) -> RecommendedCapability:
    """Wrap one selected capability with the execution credential metadata."""
    return RecommendedCapability(
        capability_id=capability_id,
        route_token=create_route_token(),
        reason=reason,
        input_schema=input_schema,
        example_arguments=example_arguments or {},
    )
