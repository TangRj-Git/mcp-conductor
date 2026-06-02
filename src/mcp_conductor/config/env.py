from __future__ import annotations

import os
import re
from pathlib import Path

# Match environment references such as ${GITHUB_TOKEN}.
_ENV_PATTERN = re.compile(r"\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)\}")


def resolve_env_reference(value: str) -> str:
    """Resolve ${NAME} references against the process environment."""
    if not _ENV_PATTERN.search(value):
        return value

    def replace(match: re.Match[str]) -> str:
        name = match.group("name")
        try:
            return os.environ[name]
        except KeyError as exc:
            raise ValueError(f"Missing required environment variable: {name}") from exc

    return _ENV_PATTERN.sub(replace, value)


def resolve_env_mapping(values: dict[str, str]) -> dict[str, str]:
    """Resolve every env value in a config mapping while preserving env names."""
    return {key: resolve_env_reference(value) for key, value in values.items()}


def load_env_file(path: str | Path) -> None:
    """Load simple KEY=VALUE pairs into os.environ without overriding existing values."""
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = _strip_optional_quotes(value.strip())


def _strip_optional_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
