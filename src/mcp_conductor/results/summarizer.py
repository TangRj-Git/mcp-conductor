from __future__ import annotations

from typing import Any


def summarize_result(value: Any, *, max_length: int = 500) -> str:
    text = repr(value)
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."
