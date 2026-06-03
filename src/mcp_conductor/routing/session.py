from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe


def create_routing_round_id() -> str:
    """Create an opaque id for one step-routing pass."""
    return f"round_{token_urlsafe(16)}"


@dataclass(slots=True)
class RoutingStep:
    """One compact agent-loop step recorded for routing diagnostics."""

    step_index: int
    step_type: str
    step_content_preview: str

    def to_payload(self) -> dict[str, object]:
        """Return a public, compact representation of the step."""
        return {
            "step_index": self.step_index,
            "step_type": self.step_type,
            "step_content_preview": self.step_content_preview,
        }


@dataclass(slots=True)
class RoutingSession:
    """Lightweight routing state for one user task."""

    session_id: str
    created_at: datetime
    expires_at: datetime
    original_task_summary: str
    recent_steps: list[RoutingStep] = field(default_factory=list)
    recommended_capability_ids: list[str] = field(default_factory=list)
    called_capability_ids: list[str] = field(default_factory=list)
    failed_capability_ids: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, object]:
        """Return safe routing state for diagnostics."""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "original_task_summary": self.original_task_summary,
            "recent_steps": [step.to_payload() for step in self.recent_steps],
            "recommended_capability_ids": list(self.recommended_capability_ids),
            "called_capability_ids": list(self.called_capability_ids),
            "failed_capability_ids": list(self.failed_capability_ids),
        }


@dataclass(slots=True)
class RoutingSessionStore:
    """In-memory store for lightweight routing sessions."""

    ttl_seconds: int = 1800
    max_sessions: int = 100
    max_recent_steps: int = 10
    preview_chars: int = 240
    values: dict[str, RoutingSession] = field(default_factory=dict)

    def create(self, *, original_task_summary: str) -> RoutingSession:
        """Create a new routing session and evict old state if needed."""
        self.prune_expired()
        now = datetime.now(UTC)
        session = RoutingSession(
            session_id=f"session_{token_urlsafe(16)}",
            created_at=now,
            expires_at=now + timedelta(seconds=self.ttl_seconds),
            original_task_summary=self._preview(original_task_summary),
        )
        self.values[session.session_id] = session
        self._enforce_limits()
        return session

    def get(self, session_id: str) -> RoutingSession | None:
        """Return a live session or remove it if expired."""
        session = self.values.get(session_id)
        if session is None:
            return None
        if self.is_expired(session):
            self.values.pop(session_id, None)
            return None
        return session

    def end(self, session_id: str) -> bool:
        """Remove one routing session."""
        return self.values.pop(session_id, None) is not None

    def clear(self) -> None:
        """Remove all sessions."""
        self.values.clear()

    def record_step(
            self,
            session_id: str,
            *,
            step_index: int,
            step_type: str,
            step_content: str,
    ) -> bool:
        """Record a compact preview of one agent-loop step."""
        session = self.get(session_id)
        if session is None:
            return False
        session.recent_steps.append(
            RoutingStep(
                step_index=step_index,
                step_type=step_type,
                step_content_preview=self._preview(step_content),
            )
        )
        if len(session.recent_steps) > self.max_recent_steps:
            session.recent_steps = session.recent_steps[-self.max_recent_steps:]
        return True

    def record_recommendation(
            self,
            session_id: str,
            capability_ids: list[str],
    ) -> bool:
        """Record capability ids returned by a routing recommendation."""
        session = self.get(session_id)
        if session is None:
            return False
        for capability_id in capability_ids:
            self._append_unique(session.recommended_capability_ids, capability_id)
        return True

    def record_call(
            self,
            session_id: str,
            capability_id: str,
    ) -> bool:
        """Record one successfully accessed capability for diagnostics."""
        session = self.get(session_id)
        if session is None:
            return False
        self._append_unique(session.called_capability_ids, capability_id)
        return True

    def record_failure(
            self,
            session_id: str,
            capability_id: str,
    ) -> bool:
        """Record one failed capability access for diagnostics."""
        session = self.get(session_id)
        if session is None:
            return False
        self._append_unique(session.failed_capability_ids, capability_id)
        return True

    def to_payload(self, session_id: str) -> dict[str, object] | None:
        """Return one live session payload, removing expired state first."""
        session = self.get(session_id)
        if session is None:
            return None
        return session.to_payload()

    def is_expired(self, session: RoutingSession) -> bool:
        """Return whether a routing session is expired."""
        return session.expires_at <= datetime.now(UTC)

    def prune_expired(self) -> None:
        """Drop expired sessions."""
        expired_ids = [
            session_id
            for session_id, session in self.values.items()
            if self.is_expired(session)
        ]
        for session_id in expired_ids:
            self.values.pop(session_id, None)

    def _enforce_limits(self) -> None:
        while len(self.values) > self.max_sessions:
            self.values.pop(next(iter(self.values)), None)

    def _append_unique(self, values: list[str], value: str) -> None:
        if value not in values:
            values.append(value)

    def _preview(self, value: str) -> str:
        compact = " ".join(str(value).split())
        if len(compact) <= self.preview_chars:
            return compact
        return compact[: self.preview_chars - 3] + "..."
