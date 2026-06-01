from __future__ import annotations

import asyncio

from fastmcp import Client

from mcp_conductor.server import create_server


def test_server_exposes_expected_public_tool_names() -> None:
    server = create_server()

    tools = asyncio.run(server.list_tools())
    names = {tool.name for tool in tools}

    assert {
        "list_upstream_capabilities",
        "recommend_capabilities",
        "call_upstream_tool",
        "read_result",
    }.issubset(names)


def test_server_lifespan_starts_and_stops_runtime() -> None:
    class FakeRuntime:
        def __init__(self) -> None:
            self.started = False
            self.stopped = False

        async def async_startup(self) -> None:
            self.started = True

        async def async_shutdown(self) -> None:
            self.stopped = True

        def list_upstream_capabilities(self, *, cursor=None, limit=50):
            return {"status": "ok", "capabilities": []}

        def recommend_capabilities(self, *, user_task, context_summary=None, limit=10):
            return {"status": "ok", "recommended_capabilities": []}

        def call_upstream_tool(
                self,
                *,
                recommendation_id,
                route_token,
                capability_id,
                arguments,
        ):
            return {"status": "ok"}

        def read_result(self, *, result_id, cursor=None, limit=50):
            return {"status": "ok"}

    async def run() -> FakeRuntime:
        runtime = FakeRuntime()
        server = create_server(runtime)
        async with Client(server):
            assert runtime.started is True
        return runtime

    runtime = asyncio.run(run())

    assert runtime.stopped is True


def test_server_call_tool_uses_runtime_async_execution_path() -> None:
    class FakeRuntime:
        def __init__(self) -> None:
            self.async_called = False

        async def async_startup(self) -> None:
            pass

        async def async_shutdown(self) -> None:
            pass

        def list_upstream_capabilities(self, *, cursor=None, limit=50):
            return {"status": "ok", "capabilities": []}

        def recommend_capabilities(self, *, user_task, context_summary=None, limit=10):
            return {"status": "ok", "recommended_capabilities": []}

        def call_upstream_tool(self, **kwargs):
            raise AssertionError("sync call path should not be used by the server")

        async def call_upstream_tool_async(self, **kwargs):
            self.async_called = True
            return {"status": "ok", "data": kwargs}

        def read_result(self, *, result_id, cursor=None, limit=50):
            return {"status": "ok"}

    async def run() -> FakeRuntime:
        runtime = FakeRuntime()
        server = create_server(runtime)

        async with Client(server) as client:
            result = await client.call_tool(
                "call_upstream_tool",
                {
                    "recommendation_id": "rec_1",
                    "route_token": "route_1",
                    "capability_id": "github.tools.get_pr_checks",
                    "arguments": {"pr_number": 12},
                },
            )

        assert result.data["status"] == "ok"
        return runtime

    runtime = asyncio.run(run())

    assert runtime.async_called is True


def test_server_call_tool_forwards_pending_action_id() -> None:
    class FakeRuntime:
        def __init__(self) -> None:
            self.kwargs = None

        async def async_startup(self) -> None:
            pass

        async def async_shutdown(self) -> None:
            pass

        def list_upstream_capabilities(self, *, cursor=None, limit=50):
            return {"status": "ok", "capabilities": []}

        def recommend_capabilities(self, *, user_task, context_summary=None, limit=10):
            return {"status": "ok", "recommended_capabilities": []}

        async def call_upstream_tool_async(self, **kwargs):
            self.kwargs = kwargs
            return {"status": "ok"}

        def read_result(self, *, result_id, cursor=None, limit=50):
            return {"status": "ok"}

    async def run() -> FakeRuntime:
        runtime = FakeRuntime()
        server = create_server(runtime)

        async with Client(server) as client:
            await client.call_tool(
                "call_upstream_tool",
                {
                    "recommendation_id": "rec_1",
                    "route_token": "route_1",
                    "capability_id": "filesystem.tools.delete_file",
                    "arguments": {"path": "demo.txt"},
                    "pending_action_id": "pending_1",
                },
            )

        return runtime

    runtime = asyncio.run(run())

    assert runtime.kwargs["pending_action_id"] == "pending_1"
