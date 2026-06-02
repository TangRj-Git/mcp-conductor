from __future__ import annotations

import pytest

from mcp_conductor.config.loader import load_config, parse_config
from mcp_conductor.config.schema import ExposureMode, RiskPolicy, TransportType


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


def test_parse_config_defaults_to_router_exposure_mode() -> None:
    config = parse_config({"mcpServers": {}})

    assert config.exposure.mode == ExposureMode.ROUTER
    assert config.exposure.include_capability_types == ["tool"]
    assert config.exposure.max_exposed_tools == 50


def test_parse_config_reads_exposure_settings() -> None:
    config = parse_config(
        {
            "exposure": {
                "mode": "hybrid",
                "include_upstreams": ["github"],
                "exclude_upstreams": ["filesystem"],
                "include_capability_types": ["tool"],
                "exclude_capability_types": ["prompt"],
                "include_capabilities": ["github.tools.get_pr_checks", "read_docs"],
                "exclude_capabilities": ["filesystem.tools.delete_file"],
                "max_exposed_tools": 12,
            },
            "mcpServers": {
                "github": {
                    "command": "npx",
                    "args": ["-y", "github-server"],
                }
            },
        }
    )

    assert config.exposure.mode == ExposureMode.HYBRID
    assert config.exposure.include_upstreams == ["github"]
    assert config.exposure.exclude_upstreams == ["filesystem"]
    assert config.exposure.include_capability_types == ["tool"]
    assert config.exposure.exclude_capability_types == ["prompt"]
    assert config.exposure.include_capabilities == [
        "github.tools.get_pr_checks",
        "read_docs",
    ]
    assert config.exposure.exclude_capabilities == ["filesystem.tools.delete_file"]
    assert config.exposure.max_exposed_tools == 12


def test_parse_config_resolves_env_references_in_connection_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UVX_COMMAND", "uvx")
    monkeypatch.setenv("PACKAGE_VERSION", "1.2.3")
    monkeypatch.setenv("HTTP_HOST", "example.test")
    monkeypatch.setenv("WORKDIR", "E:\\SoftwareProject\\demo")

    config = parse_config(
        {
            "mcpServers": {
                "stdio": {
                    "command": "${UVX_COMMAND}",
                    "args": ["--from", "demo-server==${PACKAGE_VERSION}"],
                    "cwd": "${WORKDIR}",
                    "allowed_roots": ["${WORKDIR}\\workspace"],
                },
                "http": {
                    "transport": "streamable_http",
                    "url": "https://${HTTP_HOST}/mcp",
                },
            }
        }
    )

    stdio = config.upstream_servers["stdio"]
    http = config.upstream_servers["http"]

    assert stdio.command == "uvx"
    assert stdio.args == ["--from", "demo-server==1.2.3"]
    assert stdio.cwd == "E:\\SoftwareProject\\demo"
    assert stdio.allowed_roots == ["E:\\SoftwareProject\\demo\\workspace"]
    assert http.url == "https://example.test/mcp"


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


def test_load_config_treats_empty_file_as_empty_config(tmp_path) -> None:
    config_path = tmp_path / "mcp-conductor.config.json"
    config_path.write_text("", encoding="utf-8")

    config = load_config(config_path)

    assert config.upstream_servers == {}


def test_parse_config_rejects_args_that_are_not_a_list() -> None:
    with pytest.raises(ValueError, match="Invalid gateway config"):
        parse_config(
            {
                "mcpServers": {
                    "github": {
                        "command": "npx",
                        "args": "-y github-server",
                    }
                }
            }
        )


def test_parse_config_rejects_unknown_exposure_capability_type() -> None:
    with pytest.raises(ValueError, match="Invalid gateway config"):
        parse_config(
            {
                "exposure": {
                    "include_capability_types": ["toool"],
                }
            }
        )


def test_parse_config_rejects_null_server_config() -> None:
    with pytest.raises(ValueError, match="Invalid gateway config"):
        parse_config({"mcpServers": {"github": None}})


def test_load_config_resolves_env_references_from_sibling_dotenv(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    config_path = tmp_path / "mcp-conductor.config.json"
    config_path.write_text(
        """
        {
          "mcpServers": {
            "github": {
              "command": "npx",
              "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"}
            }
          }
        }
        """,
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text("GITHUB_TOKEN=dotenv-token\n", encoding="utf-8")

    config = load_config(config_path)

    assert config.upstream_servers["github"].env["GITHUB_TOKEN"] == "dotenv-token"
