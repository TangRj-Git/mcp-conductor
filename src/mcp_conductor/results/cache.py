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
    size_bytes: int = 0


@dataclass(slots=True)
class ResultCache:
    ttl_seconds: int = 1800
    max_entries: int = 100
    max_bytes: int = 10 * 1024 * 1024
    values: dict[str, CachedResult] = field(default_factory=dict)

    def put(self, value: Any, *, session_id: str | None = None) -> str:
        self.prune_expired()
        result_id = f"result_{token_urlsafe(24)}"
        self.values[result_id] = CachedResult(
            value=value,
            expires_at=datetime.now(UTC) + timedelta(seconds=self.ttl_seconds),
            session_id=session_id,
            size_bytes=self._size_bytes(value),
        )
        self._enforce_limits()
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

    def prune_expired(self) -> None:
        now = datetime.now(UTC)
        expired_ids = [
            result_id
            for result_id, cached in self.values.items()
            if cached.expires_at <= now
        ]
        for result_id in expired_ids:
            self.values.pop(result_id, None)

    def _enforce_limits(self) -> None:
        while len(self.values) > self.max_entries:
            self.values.pop(next(iter(self.values)), None)

        while self.values and self._total_bytes() > self.max_bytes:
            self.values.pop(next(iter(self.values)), None)

    def _total_bytes(self) -> int:
        return sum(cached.size_bytes for cached in self.values.values())

    def _size_bytes(self, value: Any) -> int:
        return len(repr(value).encode("utf-8"))
