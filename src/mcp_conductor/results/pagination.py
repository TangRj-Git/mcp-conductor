from __future__ import annotations

from typing import Any

MAX_PAGE_LIMIT = 200


def parse_cursor(cursor: str | None) -> int | None:
    if cursor is None:
        return 0
    try:
        offset = int(cursor)
    except ValueError:
        return None
    if offset < 0:
        return None
    return offset


def is_valid_limit(limit: int, *, max_limit: int = MAX_PAGE_LIMIT) -> bool:
    return type(limit) is int and 1 <= limit <= max_limit


def paginate_items(items: list[Any], *, offset: int = 0, limit: int = 50) -> dict:
    next_offset = offset + limit
    page = items[offset:next_offset]
    has_more = next_offset < len(items)
    return {
        "items": page,
        "next_cursor": str(next_offset) if has_more else None,
        "has_more": has_more,
    }
