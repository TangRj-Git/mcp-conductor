from __future__ import annotations

from typing import Any

from .cache import ResultCache
from .pagination import is_valid_limit, paginate_items, parse_cursor
from .summarizer import summarize_result


class ResultManager:
    def __init__(
            self,
            cache: ResultCache | None = None,
            *,
            preview_limit: int = 20,
            max_inline_bytes: int = 8192,
    ) -> None:
        self.cache = cache or ResultCache()
        self.preview_limit = preview_limit
        self.max_inline_bytes = max_inline_bytes

    def prepare_result(
            self,
            value: Any,
            *,
            session_id: str | None = None,
    ) -> dict[str, Any]:
        result_id = None
        truncated = False
        preview = value if isinstance(value, list) else []
        cache_unavailable_reason = None

        if isinstance(value, list) and (
            len(value) > self.preview_limit
            or self._exceeds_inline_limit(value)
        ):
            if session_id is None:
                cache_unavailable_reason = "session_id_unavailable"
            else:
                result_id = self.cache.put(value, session_id=session_id)
            preview = value[: self.preview_limit]
            if self._exceeds_inline_limit(preview):
                preview = summarize_result(preview, max_length=1000)
            truncated = True
        elif self._exceeds_inline_limit(value):
            if session_id is None:
                cache_unavailable_reason = "session_id_unavailable"
            else:
                result_id = self.cache.put(value, session_id=session_id)
            preview = summarize_result(value, max_length=1000)
            truncated = True

        return {
            "status": "ok",
            "summary": summarize_result(value),
            "data": None if truncated else value,
            "preview": preview,
            "truncated": truncated,
            "result_id": result_id,
            "cache_unavailable_reason": cache_unavailable_reason,
        }

    def _exceeds_inline_limit(self, value: Any) -> bool:
        return len(repr(value).encode("utf-8")) > self.max_inline_bytes

    def read_result(
            self,
            result_id: str,
            *,
            cursor: str | None = None,
            limit: int = 50,
            session_id: str | None = None,
    ) -> dict[str, Any]:
        value = self.cache.get(result_id, session_id=session_id)
        if value is None:
            return {
                "status": "not_found",
                "error_code": "result_not_found",
                "message": "The result_id is invalid, expired, or not accessible.",
                "items": [],
                "next_cursor": None,
                "has_more": False,
            }

        items = value if isinstance(value, list) else [value]
        if not is_valid_limit(limit):
            return {
                "status": "error",
                "error_code": "invalid_limit",
                "message": "Limit must be an integer between 1 and 200.",
                "items": [],
                "next_cursor": None,
                "has_more": False,
            }
        offset = parse_cursor(cursor)
        if offset is None:
            return {
                "status": "error",
                "error_code": "invalid_cursor",
                "message": "Cursor must be a non-negative integer.",
                "items": [],
                "next_cursor": None,
                "has_more": False,
            }
        page = paginate_items(items, offset=offset, limit=limit)
        return {"status": "ok", **page}
