from __future__ import annotations

import asyncio

from fastmcp import Client

from mcp_conductor.server import create_server


def test_server_exposes_expected_public_tool_names() -> None:
    server = create_server()

    tools = asyncio.run(server.list_tools())
    names = {tool.name for tool in tools}

    assert {
        "analyze_user_task",
        "start_routing_session",
        "analyze_agent_step",
        "list_routing_session_state",
        "end_routing_session",
        "list_upstream_capabilities",
        "recommend_capabilities",
        "call_upstream_tool",
        "read_upstream_resource",
        "read_upstream_resource_template",
        "get_upstream_prompt",
        "read_result",
        "list_exposed_capabilities",
    }.issubset(names)


def test_server_analyze_user_task_delegates_to_runtime_recommendation() -> None:
    class FakeRuntime:
        def __init__(self) -> None:
            self.recommend_kwargs = None

        async def async_startup(self) -> None:
            pass

        async def async_shutdown(self) -> None:
            pass

        def recommend_capabilities(self, **kwargs):
            self.recommend_kwargs = kwargs
            return {
                "status": "ok",
                "recommendation_id": "rec_1",
                "recommended_capabilities": [],
            }

    async def run() -> FakeRuntime:
        runtime = FakeRuntime()
        server = create_server(runtime)

        async with Client(server) as client:
            result = await client.call_tool(
                "analyze_user_task",
                {
                    "user_task": "find MCP docs",
                    "context_summary": "Need upstream documentation",
                    "limit": 5,
                },
            )

        assert result.data["status"] == "ok"
        return runtime

    runtime = asyncio.run(run())

    assert runtime.recommend_kwargs == {
        "user_task": "find MCP docs",
        "context_summary": "Need upstream documentation",
        "limit": 5,
    }


def test_server_list_exposed_capabilities_delegates_to_runtime() -> None:
    class FakeRuntime:
        def __init__(self) -> None:
            self.called = False

        async def async_startup(self) -> None:
            pass

        async def async_shutdown(self) -> None:
            pass

        def list_exposed_capabilities(self, **kwargs):
            self.called = True
            self.kwargs = kwargs
            return {
                "status": "ok",
                "mode": "hybrid",
                "dynamic_registration_enabled": False,
                "exposed_capabilities": [],
            }

    async def run() -> FakeRuntime:
        runtime = FakeRuntime()
        server = create_server(runtime)

        async with Client(server) as client:
            result = await client.call_tool(
                "list_exposed_capabilities",
                {
                    "cursor": "2",
                    "limit": 5,
                    "include_skipped": True,
                },
            )

        assert result.data["status"] == "ok"
        return runtime

    runtime = asyncio.run(run())

    assert runtime.called is True
    assert runtime.kwargs == {
        "cursor": "2",
        "limit": 5,
        "include_skipped": True,
    }


def test_server_analyze_agent_step_delegates_to_runtime() -> None:
    class FakeRuntime:
        def __init__(self) -> None:
            self.kwargs = None

        async def async_startup(self) -> None:
            pass

        async def async_shutdown(self) -> None:
            pass

        def analyze_agent_step(self, **kwargs):
            self.kwargs = kwargs
            return {
                "status": "ok",
                "routing_round_id": "round_1",
                "recommended_capabilities": [],
            }

    async def run() -> FakeRuntime:
        runtime = FakeRuntime()
        server = create_server(runtime)

        async with Client(server) as client:
            result = await client.call_tool(
                "analyze_agent_step",
                {
                    "session_id": "session_1",
                    "step_index": 2,
                    "step_type": "tool_result",
                    "step_content": "Need docs next",
                    "limit": 3,
                },
            )

        assert result.data["status"] == "ok"
        return runtime

    runtime = asyncio.run(run())

    assert runtime.kwargs == {
        "session_id": "session_1",
        "step_index": 2,
        "step_type": "tool_result",
        "step_content": "Need docs next",
        "limit": 3,
    }


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

        def read_result(self, *, result_id, cursor=None, limit=50, session_id=None):
            return {"status": "ok"}

        async def read_upstream_resource_async(self, **kwargs):
            return {"status": "ok", "data": kwargs}

        async def read_upstream_resource_template_async(self, **kwargs):
            return {"status": "ok", "data": kwargs}

        async def get_upstream_prompt_async(self, **kwargs):
            return {"status": "ok", "data": kwargs}

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

        def read_result(self, *, result_id, cursor=None, limit=50, session_id=None):
            return {"status": "ok"}

        async def read_upstream_resource_async(self, **kwargs):
            return {"status": "ok", "data": kwargs}

        async def read_upstream_resource_template_async(self, **kwargs):
            return {"status": "ok", "data": kwargs}

        async def get_upstream_prompt_async(self, **kwargs):
            return {"status": "ok", "data": kwargs}

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

        def read_result(self, *, result_id, cursor=None, limit=50, session_id=None):
            return {"status": "ok"}

        async def read_upstream_resource_async(self, **kwargs):
            return {"status": "ok", "data": kwargs}

        async def read_upstream_resource_template_async(self, **kwargs):
            return {"status": "ok", "data": kwargs}

        async def get_upstream_prompt_async(self, **kwargs):
            return {"status": "ok", "data": kwargs}

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


def test_server_call_tool_forwards_routing_session_id() -> None:
    class FakeRuntime:
        def __init__(self) -> None:
            self.kwargs = None

        async def async_startup(self) -> None:
            pass

        async def async_shutdown(self) -> None:
            pass

        async def call_upstream_tool_async(self, **kwargs):
            self.kwargs = kwargs
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
                    "capability_id": "github.tools.get_pr_checks",
                    "arguments": {"pr_number": 12},
                    "routing_session_id": "session_1",
                },
            )

        return runtime

    runtime = asyncio.run(run())

    assert runtime.kwargs["routing_session_id"] == "session_1"


def test_server_passes_context_session_id_to_runtime_calls() -> None:
    class FakeRuntime:
        def __init__(self) -> None:
            self.call_kwargs = None
            self.read_kwargs = None

        async def async_startup(self) -> None:
            pass

        async def async_shutdown(self) -> None:
            pass

        def list_upstream_capabilities(self, *, cursor=None, limit=50):
            return {"status": "ok", "capabilities": []}

        def recommend_capabilities(self, *, user_task, context_summary=None, limit=10):
            return {"status": "ok", "recommended_capabilities": []}

        async def call_upstream_tool_async(self, **kwargs):
            self.call_kwargs = kwargs
            return {"status": "ok", "result_id": None}

        def read_result(self, **kwargs):
            self.read_kwargs = kwargs
            return {"status": "ok", "items": []}

        async def read_upstream_resource_async(self, **kwargs):
            return {"status": "ok", "data": kwargs}

        async def read_upstream_resource_template_async(self, **kwargs):
            return {"status": "ok", "data": kwargs}

        async def get_upstream_prompt_async(self, **kwargs):
            return {"status": "ok", "data": kwargs}

    async def run() -> FakeRuntime:
        runtime = FakeRuntime()
        server = create_server(runtime)

        async with Client(server) as client:
            await client.call_tool(
                "call_upstream_tool",
                {
                    "recommendation_id": "rec_1",
                    "route_token": "route_1",
                    "capability_id": "github.tools.get_pr_checks",
                    "arguments": {"pr_number": 12},
                },
            )
            await client.call_tool("read_result", {"result_id": "result_1"})

        return runtime

    runtime = asyncio.run(run())

    assert runtime.call_kwargs["session_id"]
    assert runtime.read_kwargs["session_id"] == runtime.call_kwargs["session_id"]


def test_server_uses_elicitation_to_confirm_pending_actions() -> None:
    class FakeRuntime:
        def __init__(self) -> None:
            self.calls = []
            self.confirmed_pending_action_id = None

        async def async_startup(self) -> None:
            pass

        async def async_shutdown(self) -> None:
            pass

        def list_upstream_capabilities(self, *, cursor=None, limit=50):
            return {"status": "ok", "capabilities": []}

        def recommend_capabilities(self, *, user_task, context_summary=None, limit=10):
            return {"status": "ok", "recommended_capabilities": []}

        async def call_upstream_tool_async(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs.get("pending_action_id") == "pending_1":
                return {"status": "ok", "data": {"deleted": True}}
            return {
                "status": "confirmation_required",
                "pending_action_id": "pending_1",
                "expires_at": "2026-06-02T00:00:00+00:00",
                "capability_id": kwargs["capability_id"],
                "risk_level": "destructive",
                "arguments_preview": kwargs["arguments"],
                "message": "User confirmation is required before this action can run.",
            }

        def confirm_pending_action(self, *, pending_action_id):
            self.confirmed_pending_action_id = pending_action_id
            return {"status": "ok", "pending_action_id": pending_action_id}

        def read_result(self, *, result_id, cursor=None, limit=50, session_id=None):
            return {"status": "ok"}

        async def read_upstream_resource_async(self, **kwargs):
            return {"status": "ok", "data": kwargs}

        async def read_upstream_resource_template_async(self, **kwargs):
            return {"status": "ok", "data": kwargs}

        async def get_upstream_prompt_async(self, **kwargs):
            return {"status": "ok", "data": kwargs}

    async def confirm_handler(message, response_type, params, context):
        return True

    async def run() -> FakeRuntime:
        runtime = FakeRuntime()
        server = create_server(runtime)

        async with Client(server, elicitation_handler=confirm_handler) as client:
            result = await client.call_tool(
                "call_upstream_tool",
                {
                    "recommendation_id": "rec_1",
                    "route_token": "route_1",
                    "capability_id": "filesystem.tools.delete_file",
                    "arguments": {"path": "demo.txt"},
                },
            )

        assert result.data["status"] == "ok"
        return runtime

    runtime = asyncio.run(run())

    assert runtime.confirmed_pending_action_id == "pending_1"
    assert runtime.calls[1]["pending_action_id"] == "pending_1"
