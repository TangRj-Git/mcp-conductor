from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from typing import Any


@dataclass(slots=True)
class CachedResult:
    value: Any
    expires_at: datetime
    session_id: str | None = None


@dataclass(slots=True)
class ResultCache:
    ttl_seconds: int = 1800
    values: dict[str, CachedResult] = field(default_factory=dict)

    def put(self, value: Any, *, session_id: str | None = None) -> str:
        result_id = f"result_{token_urlsafe(24)}"
        self.values[result_id] = CachedResult(
            value=value,
            expires_at=datetime.now(UTC) + timedelta(seconds=self.ttl_seconds),
            session_id=session_id,
        )
        return result_id

    def get(self, result_id: str, *, session_id: str | None = None) -> Any | None:
        cached = self.values.get(result_id)
        if cached is None:
            return None
        if cached.expires_at <= datetime.now(UTC):
            self.values.pop(result_id, None)
            return None
        if cached.session_id is not None and cached.session_id != session_id:
            return None
        return cached.value
