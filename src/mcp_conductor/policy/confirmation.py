from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from typing import Any

from mcp_conductor.models import PendingAction, RiskLevel


def create_pending_action(
        *,
        capability_id: str,
        arguments: dict[str, Any],
        risk_level: RiskLevel,
        ttl_seconds: int = 300,
) -> PendingAction:
    return PendingAction(
        pending_action_id=f"pending_{token_urlsafe(16)}",
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        capability_id=capability_id,
        arguments=arguments,
        risk_level=risk_level,
    )


@dataclass(slots=True)
class PendingActionStore:
    values: dict[str, PendingAction] = field(default_factory=dict)

    def create(
            self,
            *,
            capability_id: str,
            arguments: dict[str, Any],
            risk_level: RiskLevel,
            ttl_seconds: int = 300,
    ) -> PendingAction:
        pending = create_pending_action(
            capability_id=capability_id,
            arguments=arguments,
            risk_level=risk_level,
            ttl_seconds=ttl_seconds,
        )
        self.values[pending.pending_action_id] = pending
        return pending

    def get(self, pending_action_id: str) -> PendingAction | None:
        return self.values.get(pending_action_id)

    def remove(self, pending_action_id: str) -> None:
        self.values.pop(pending_action_id, None)

    def is_expired(self, pending: PendingAction) -> bool:
        return pending.expires_at <= datetime.now(UTC)
