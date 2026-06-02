from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "smoke_learn_mcp.py"
spec = importlib.util.spec_from_file_location("smoke_learn_mcp", SCRIPT_PATH)
assert spec is not None
smoke_learn_mcp = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(smoke_learn_mcp)


def test_select_recommended_capability_matches_type_and_name_fragment() -> None:
    recommendation = {
        "recommended_capabilities": [
            {
                "capability_type": "resource",
                "name": "mcp://docs/tools",
                "capability_id": "learn.resources.tools",
            },
            {
                "capability_type": "tool",
                "name": "get_server_info",
                "capability_id": "learn.tools.get_server_info",
            },
        ]
    }

    selected = smoke_learn_mcp.select_recommended_capability(
        recommendation,
        capability_type="tool",
        name_contains="server",
    )

    assert selected["capability_id"] == "learn.tools.get_server_info"


def test_run_access_check_dispatches_to_matching_runtime_method() -> None:
    class FakeRuntime:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, Any]]] = []

        def recommend_capabilities(self, *, user_task: str, limit: int):
            assert user_task == "read docs"
            assert limit == 10
            return {
                "status": "ok",
                "recommendation_id": "rec_1",
                "recommended_capabilities": [
                    {
                        "capability_type": "resource",
                        "name": "mcp://docs/tools",
                        "capability_id": "learn.resources.tools",
                        "route_token": "route_1",
                    }
                ],
            }

        async def read_upstream_resource_async(self, **kwargs):
            self.calls.append(("read_resource", kwargs))
            return {"status": "ok", "summary": "docs"}

    runtime = FakeRuntime()
    scenario = smoke_learn_mcp.SmokeScenario(
        label="resource",
        user_task="read docs",
        capability_type="resource",
        arguments={},
        name_contains="tools",
    )

    result = asyncio.run(smoke_learn_mcp.run_access_check(runtime, scenario))

    assert result["status"] == "ok"
    assert runtime.calls == [
        (
            "read_resource",
            {
                "recommendation_id": "rec_1",
                "route_token": "route_1",
                "capability_id": "learn.resources.tools",
            },
        )
    ]
