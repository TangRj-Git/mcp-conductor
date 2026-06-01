from __future__ import annotations

from typing import Any

from .cache import ResultCache
from .pagination import paginate_items
from .summarizer import summarize_result


class ResultManager:
    def __init__(
            self,
            cache: ResultCache | None = None,
            *,
            preview_limit: int = 20,
    ) -> None:
        self.cache = cache or ResultCache()
        self.preview_limit = preview_limit

    def prepare_result(
            self,
            value: Any,
            *,
            session_id: str | None = None,
    ) -> dict[str, Any]:
        result_id = None
        truncated = False
        preview = value if isinstance(value, list) else []

        if isinstance(value, list) and len(value) > self.preview_limit:
            result_id = self.cache.put(value, session_id=session_id)
            preview = value[: self.preview_limit]
            truncated = True

        return {
            "status": "ok",
            "summary": summarize_result(value),
            "data": None if truncated else value,
            "preview": preview,
            "truncated": truncated,
            "result_id": result_id,
        }

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
        offset = int(cursor) if cursor else 0
        page = paginate_items(items, offset=offset, limit=limit)
        return {"status": "ok", **page}
