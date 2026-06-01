from __future__ import annotations

from pathlib import Path


def is_path_allowed(path: str, allowed_roots: list[str]) -> bool:
    target = Path(path).resolve()
    for root in allowed_roots:
        root_path = Path(root).resolve()
        if target == root_path or root_path in target.parents:
            return True
    return False
