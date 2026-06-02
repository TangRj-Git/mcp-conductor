from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema.exceptions import best_match
from jsonschema.validators import Draft202012Validator

from mcp_conductor.models import CapabilityType

from .env import load_env_file, resolve_env_mapping, resolve_env_reference
from .schema import (
    ExposureConfig,
    ExposureMode,
    GatewayConfig,
    RiskPolicy,
    RootsPolicy,
    TransportType,
    UpstreamServerConfig,
)

_SERVER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "transport": {"enum": [item.value for item in TransportType]},
        "command": {"type": "string"},
        "args": {"type": "array", "items": {"type": "string"}},
        "url": {"type": "string"},
        "cwd": {"type": "string"},
        "env": {"type": "object", "additionalProperties": {"type": "string"}},
        "disabled": {"type": "boolean"},
        "risk_policy": {"enum": [item.value for item in RiskPolicy]},
        "roots_policy": {"enum": [item.value for item in RootsPolicy]},
        "allowed_roots": {"type": "array", "items": {"type": "string"}},
    },
}

_CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "exposure": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "mode": {"enum": [item.value for item in ExposureMode]},
                "include_upstreams": {"type": "array", "items": {"type": "string"}},
                "exclude_upstreams": {"type": "array", "items": {"type": "string"}},
                "include_capability_types": {
                    "type": "array",
                    "items": {"enum": [item.value for item in CapabilityType]},
                },
                "exclude_capability_types": {
                    "type": "array",
                    "items": {"enum": [item.value for item in CapabilityType]},
                },
                "include_capabilities": {"type": "array", "items": {"type": "string"}},
                "exclude_capabilities": {"type": "array", "items": {"type": "string"}},
                "max_exposed_tools": {"type": "integer", "minimum": 0},
            },
        },
        "mcpServers": {
            "type": "object",
            "additionalProperties": _SERVER_SCHEMA,
        },
        "upstreamServers": {
            "type": "object",
            "additionalProperties": _SERVER_SCHEMA,
        },
    },
}


def load_config(path: str | Path | None) -> GatewayConfig:
    """Load a gateway configuration file, returning defaults when no path is given."""
    if path is None:
        return GatewayConfig()

    config_path = Path(path)
    load_env_file(config_path.parent / ".env")
    raw_config = config_path.read_text(encoding="utf-8").strip()
    if not raw_config:
        return GatewayConfig()

    data = json.loads(raw_config)
    return parse_config(data)


def parse_config(data: dict[str, Any]) -> GatewayConfig:
    """Parse raw JSON data into the internal gateway configuration model."""
    _validate_config(data)
    upstream = {}
    # Accept the common MCP host shape and the project-specific alias.
    # Explicit upstreamServers entries win when both maps contain the same server id.
    raw_servers = {
        **data.get("mcpServers", {}),
        **data.get("upstreamServers", {}),
    }
    for server_id, raw in raw_servers.items():
        upstream[server_id] = parse_upstream_server(server_id, raw)
    return GatewayConfig(
        upstream_servers=upstream,
        exposure=parse_exposure_config(data.get("exposure", {})),
    )


def _validate_config(data: dict[str, Any]) -> None:
    validator = Draft202012Validator(_CONFIG_SCHEMA)
    errors = sorted(validator.iter_errors(data), key=lambda error: list(error.path))
    if not errors:
        return
    error = best_match(errors)
    path = ".".join(str(part) for part in error.path)
    location = f" at {path}" if path else ""
    raise ValueError(f"Invalid gateway config{location}: {error.message}")


def parse_upstream_server(
        server_id: str,
        raw: dict[str, Any],
) -> UpstreamServerConfig:
    """Parse one upstream MCP server entry and resolve environment references."""
    roots_policy = raw.get("roots_policy")
    return UpstreamServerConfig(
        server_id=server_id,
        transport=TransportType(raw.get("transport", TransportType.STDIO)),
        command=_resolve_optional_string(raw.get("command")),
        args=_resolve_string_list(raw.get("args", [])),
        url=_resolve_optional_string(raw.get("url")),
        cwd=_resolve_optional_string(raw.get("cwd")),
        env=resolve_env_mapping(dict(raw.get("env", {}))),
        disabled=bool(raw.get("disabled", False)),
        risk_policy=RiskPolicy(raw.get("risk_policy", RiskPolicy.READ_ONLY_ONLY)),
        roots_policy=RootsPolicy(roots_policy) if roots_policy else None,
        allowed_roots=_resolve_string_list(raw.get("allowed_roots", [])),
    )


def parse_exposure_config(raw: dict[str, Any]) -> ExposureConfig:
    """Parse the optional gateway exposure configuration."""
    return ExposureConfig(
        mode=ExposureMode(raw.get("mode", ExposureMode.ROUTER)),
        include_upstreams=_resolve_string_list(raw.get("include_upstreams", [])),
        exclude_upstreams=_resolve_string_list(raw.get("exclude_upstreams", [])),
        include_capability_types=_resolve_string_list(
            raw.get("include_capability_types", ["tool"]),
        ),
        exclude_capability_types=_resolve_string_list(
            raw.get("exclude_capability_types", []),
        ),
        include_capabilities=_resolve_string_list(raw.get("include_capabilities", [])),
        exclude_capabilities=_resolve_string_list(raw.get("exclude_capabilities", [])),
        max_exposed_tools=int(raw.get("max_exposed_tools", 50)),
    )


def _resolve_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return resolve_env_reference(str(value))


def _resolve_string_list(values: list[str]) -> list[str]:
    return [resolve_env_reference(value) for value in values]
