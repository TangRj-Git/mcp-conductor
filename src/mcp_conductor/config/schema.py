from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class TransportType(StrEnum):
    """Transport options used to connect to upstream MCP servers."""

    STDIO = "stdio"
    STREAMABLE_HTTP = "streamable_http"


class RiskPolicy(StrEnum):
    """Configured safety policy for one upstream server."""

    READ_ONLY_ONLY = "read_only_only"
    CONFIRM_MUTATIONS = "confirm_mutations"
    DISABLED = "disabled"


class RootsPolicy(StrEnum):
    """Path allowlist strategy for tools that accept filesystem arguments."""

    HOST_ROOTS_OR_CONFIG_ALLOWLIST = "host_roots_or_config_allowlist"
    CONFIG_ALLOWLIST_ONLY = "config_allowlist_only"


class ExposureMode(StrEnum):
    """How upstream capabilities should be surfaced to the MCP host."""

    ROUTER = "router"
    PROXY = "proxy"
    HYBRID = "hybrid"


@dataclass(slots=True)
class ExposureConfig:
    """Controls which upstream capabilities may be exposed as direct proxies."""

    mode: ExposureMode = ExposureMode.ROUTER
    include_upstreams: list[str] = field(default_factory=list)
    exclude_upstreams: list[str] = field(default_factory=list)
    include_capability_types: list[str] = field(default_factory=lambda: ["tool"])
    exclude_capability_types: list[str] = field(default_factory=list)
    include_capabilities: list[str] = field(default_factory=list)
    exclude_capabilities: list[str] = field(default_factory=list)
    max_exposed_tools: int = 50


@dataclass(slots=True)
class UpstreamServerConfig:
    """Connection and policy settings for one upstream MCP server."""

    server_id: str
    transport: TransportType = TransportType.STDIO
    command: str | None = None
    args: list[str] = field(default_factory=list)
    url: str | None = None
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    disabled: bool = False
    risk_policy: RiskPolicy = RiskPolicy.READ_ONLY_ONLY
    roots_policy: RootsPolicy | None = None
    allowed_roots: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GatewayConfig:
    """Top-level configuration for all upstream MCP servers."""

    upstream_servers: dict[str, UpstreamServerConfig] = field(default_factory=dict)
    exposure: ExposureConfig = field(default_factory=ExposureConfig)
