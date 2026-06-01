from __future__ import annotations

import pytest

from mcp_conductor.config.loader import parse_config
from mcp_conductor.config.schema import RiskPolicy, TransportType


def test_parse_config_resolves_env_references(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")

    config = parse_config(
        {
            "upstreamServers": {
                "github": {
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-github"],
                    "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"},
                    "risk_policy": "read_only_only",
                }
            }
        }
    )

    github = config.upstream_servers["github"]
    assert github.transport == TransportType.STDIO
    assert github.risk_policy == RiskPolicy.READ_ONLY_ONLY
    assert github.env == {"GITHUB_TOKEN": "secret-token"}


def test_parse_config_fails_when_env_reference_is_missing() -> None:
    with pytest.raises(ValueError, match="Missing required environment variable"):
        parse_config(
            {
                "upstreamServers": {
                    "github": {
                        "env": {"GITHUB_TOKEN": "${MISSING_GITHUB_TOKEN}"},
                    }
                }
            }
        )


def test_parse_config_accepts_mcp_servers_alias() -> None:
    config = parse_config(
        {
            "mcpServers": {
                "github": {
                    "command": "npx",
                    "args": ["-y", "github-server"],
                }
            }
        }
    )

    github = config.upstream_servers["github"]

    assert github.command == "npx"
    assert github.args == ["-y", "github-server"]


def test_parse_config_reads_allowed_roots() -> None:
    config = parse_config(
        {
            "upstreamServers": {
                "filesystem": {
                    "command": "npx",
                    "allowed_roots": ["E:\\SoftwareProject\\demo"],
                    "roots_policy": "config_allowlist_only",
                }
            }
        }
    )

    filesystem = config.upstream_servers["filesystem"]

    assert filesystem.allowed_roots == ["E:\\SoftwareProject\\demo"]
