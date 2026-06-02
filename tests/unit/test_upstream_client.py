from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastmcp import Client, FastMCP

from mcp_conductor.config.schema import UpstreamServerConfig
from mcp_conductor.upstream.client import (
    UpstreamClient,
    UpstreamClientConfigurationError,
    UpstreamClientNotConnected,
)


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def list_tools(self):
        return SimpleNamespace(
            tools=[
                SimpleNamespace(
                    name="get_pr_checks",
                    description="Read PR CI checks",
                    inputSchema={
                        "type": "object",
                        "properties": {"pr_number": {"type": "integer"}},
                    },
                    annotations=SimpleNamespace(readOnlyHint=True),
                )
            ]
        )

    def list_resources(self):
        return [
            SimpleNamespace(
                uri="repo://owner/project/README.md",
                name="README.md",
                description="Repository README",
                mimeType="text/markdown",
            )
        ]

    def list_resource_templates(self):
        return [
            SimpleNamespace(
                uriTemplate="repo://owner/project/{path}",
                name="Repository file",
                description="Read a repository file by path",
                mimeType="text/plain",
            )
        ]

    def list_prompts(self):
        return [
            SimpleNamespace(
                name="summarize_pr",
                description="Summarize a PR",
                arguments=[SimpleNamespace(name="pr_number", required=True)],
            )
        ]

    def call_tool(self, name: str, arguments: dict):
        self.calls.append((name, arguments))
        return {"name": name, "arguments": arguments}

    def read_resource(self, uri: str):
        return [
            SimpleNamespace(
                uri=uri,
                mimeType="text/markdown",
                text="# README\nProject notes.",
            )
        ]

    def get_prompt(self, name: str, arguments: dict | None = None):
        return SimpleNamespace(
            description="Summarize a PR",
            messages=[
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": f"Summarize PR {arguments['pr_number']}",
                    },
                }
            ],
        )


def test_upstream_client_normalizes_list_tools_response() -> None:
    client = UpstreamClient(
        UpstreamServerConfig(server_id="github"),
        session=FakeSession(),
    )

    tools = client.list_tools()

    assert tools == [
        {
            "name": "get_pr_checks",
            "description": "Read PR CI checks",
            "input_schema": {
                "type": "object",
                "properties": {"pr_number": {"type": "integer"}},
            },
            "annotations": {"readOnlyHint": True},
        }
    ]


def test_upstream_client_normalizes_non_tool_capability_lists() -> None:
    client = UpstreamClient(
        UpstreamServerConfig(server_id="github"),
        session=FakeSession(),
    )

    resources = client.list_resources()
    templates = client.list_resource_templates()
    prompts = client.list_prompts()

    assert resources[0]["uri"] == "repo://owner/project/README.md"
    assert resources[0]["mime_type"] == "text/markdown"
    assert templates[0]["uri_template"] == "repo://owner/project/{path}"
    assert templates[0]["mime_type"] == "text/plain"
    assert prompts[0]["arguments"][0]["name"] == "pr_number"


def test_upstream_client_calls_session_tool() -> None:
    session = FakeSession()
    client = UpstreamClient(UpstreamServerConfig(server_id="github"), session=session)

    result = client.call_tool("get_pr_checks", {"pr_number": 12})

    assert result == {"name": "get_pr_checks", "arguments": {"pr_number": 12}}
    assert session.calls == [("get_pr_checks", {"pr_number": 12})]


def test_upstream_client_reads_resource() -> None:
    client = UpstreamClient(
        UpstreamServerConfig(server_id="github"),
        session=FakeSession(),
    )

    result = client.read_resource("repo://owner/project/README.md")

    assert result == [
        {
            "uri": "repo://owner/project/README.md",
            "mimeType": "text/markdown",
            "text": "# README\nProject notes.",
        }
    ]


def test_upstream_client_gets_prompt() -> None:
    client = UpstreamClient(
        UpstreamServerConfig(server_id="github"),
        session=FakeSession(),
    )

    result = client.get_prompt("summarize_pr", {"pr_number": 12})

    assert result["description"] == "Summarize a PR"
    assert result["messages"][0]["content"]["text"] == "Summarize PR 12"


def test_upstream_client_requires_session_before_calling() -> None:
    client = UpstreamClient(UpstreamServerConfig(server_id="github"))

    with pytest.raises(UpstreamClientNotConnected):
        client.call_tool("get_pr_checks", {"pr_number": 12})


def test_upstream_client_connects_with_session_factory_when_session_is_missing() -> None:
    class FakeAsyncSession(FakeSession):
        def __init__(self) -> None:
            super().__init__()
            self.entered = False
            self.exited = False

        async def __aenter__(self):
            self.entered = True
            return self

        async def __aexit__(self, exc_type, exc, tb):
            self.exited = True

    created_sessions: list[FakeAsyncSession] = []

    def session_factory(config: UpstreamServerConfig) -> FakeAsyncSession:
        assert config.server_id == "github"
        session = FakeAsyncSession()
        created_sessions.append(session)
        return session

    async def run() -> None:
        client = UpstreamClient(
            UpstreamServerConfig(server_id="github"),
            session_factory=session_factory,
        )

        await client.connect()
        await client.shutdown()

    asyncio.run(run())

    assert created_sessions[0].entered is True
    assert created_sessions[0].exited is True


def test_upstream_client_requires_command_for_stdio_session_creation() -> None:
    client = UpstreamClient(UpstreamServerConfig(server_id="github"))

    with pytest.raises(UpstreamClientConfigurationError):
        asyncio.run(client.connect())


def test_upstream_client_can_use_fastmcp_client_session() -> None:
    async def run() -> None:
        upstream = FastMCP("test-upstream")

        @upstream.tool(name="get_pr_checks")
        def get_pr_checks(pr_number: int) -> dict:
            """Read PR CI checks."""
            return {"pr_number": pr_number, "state": "success"}

        client = UpstreamClient(
            UpstreamServerConfig(server_id="github"),
            session=Client(upstream),
        )

        await client.connect()
        try:
            tools = await client.list_tools_async()
            result = await client.call_tool_async("get_pr_checks", {"pr_number": 12})
        finally:
            await client.shutdown()

        assert tools[0]["name"] == "get_pr_checks"
        assert tools[0]["description"] == "Read PR CI checks."
        assert result == {"pr_number": 12, "state": "success"}

    asyncio.run(run())
