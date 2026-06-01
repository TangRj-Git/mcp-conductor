from __future__ import annotations

from typing import Any


def paginate_items(items: list[Any], *, offset: int = 0, limit: int = 50) -> dict:
    next_offset = offset + limit
    page = items[offset:next_offset]
    has_more = next_offset < len(items)
    return {
        "items": page,
        "next_cursor": str(next_offset) if has_more else None,
        "has_more": has_more,
    }
