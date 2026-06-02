from __future__ import annotations

import argparse
import asyncio
from typing import Any, NamedTuple

from mcp_conductor.runtime import GatewayRuntime


class SmokeScenario(NamedTuple):
    label: str
    user_task: str
    capability_type: str
    arguments: dict[str, Any] | None = None
    name_contains: str | None = None


SMOKE_SCENARIOS: tuple[SmokeScenario, ...] = (
    SmokeScenario(
        label="tool",
        user_task="server info",
        capability_type="tool",
        arguments={},
        name_contains="server_info",
    ),
    SmokeScenario(
        label="resource",
        user_task="read MCP tools documentation resource",
        capability_type="resource",
        arguments={},
        name_contains="docs/tools",
    ),
    SmokeScenario(
        label="resource_template",
        user_task="read concept by name resource template",
        capability_type="resource_template",
        arguments={"name": "basic-tool"},
        name_contains="examples/{name}",
    ),
    SmokeScenario(
        label="prompt",
        user_task="explain mcp topic prompt",
        capability_type="prompt",
        arguments={"topic": "tools", "level": "beginner"},
        name_contains="explain_mcp_topic",
    ),
)


def select_recommended_capability(
        recommendation: dict[str, Any],
        *,
        capability_type: str,
        name_contains: str | None = None,
) -> dict[str, Any]:
    expected_fragment = name_contains.lower() if name_contains else None
    for candidate in recommendation.get("recommended_capabilities", []):
        if candidate.get("capability_type") != capability_type:
            continue
        if expected_fragment is None:
            return candidate
        searchable = " ".join(
            str(candidate.get(key, ""))
            for key in ("name", "capability_id")
        ).lower()
        if expected_fragment in searchable:
            return candidate
    raise RuntimeError(
        f"No recommended {capability_type!r} capability matched {name_contains!r}."
    )


async def run_access_check(runtime: Any, scenario: SmokeScenario) -> dict[str, Any]:
    recommendation = runtime.recommend_capabilities(
        user_task=scenario.user_task,
        limit=10,
    )
    if recommendation.get("status") != "ok":
        return {
            "status": "error",
            "label": scenario.label,
            "error_code": "recommendation_failed",
            "message": str(recommendation),
        }

    selected = select_recommended_capability(
        recommendation,
        capability_type=scenario.capability_type,
        name_contains=scenario.name_contains,
    )
    request = dict(
        selected.get("ready_to_call_arguments")
        or {
            "recommendation_id": recommendation["recommendation_id"],
            "route_token": selected["route_token"],
            "capability_id": selected["capability_id"],
        }
    )
    arguments = scenario.arguments
    if arguments is None:
        arguments = request.pop("arguments", {})
    else:
        request.pop("arguments", None)

    if scenario.capability_type == "tool":
        result = await runtime.call_upstream_tool_async(arguments=arguments, **request)
    elif scenario.capability_type == "resource":
        result = await runtime.read_upstream_resource_async(**request)
    elif scenario.capability_type == "resource_template":
        result = await runtime.read_upstream_resource_template_async(
            arguments=arguments,
            **request,
        )
    elif scenario.capability_type == "prompt":
        result = await runtime.get_upstream_prompt_async(arguments=arguments, **request)
    else:
        return {
            "status": "error",
            "label": scenario.label,
            "error_code": "unsupported_smoke_capability_type",
            "message": scenario.capability_type,
        }

    return {
        "label": scenario.label,
        "capability_type": scenario.capability_type,
        "capability_id": selected["capability_id"],
        **result,
    }


async def run_smoke(config_path: str, limit: int, *, discovery_only: bool = False) -> int:
    runtime = GatewayRuntime(config_path=config_path)
    await runtime.async_startup()
    try:
        result = runtime.list_upstream_capabilities(limit=limit)
        print(f"status={result['status']}")
        print(f"capability_count={result['total_count']}")
        print(f"type_counts={result['type_counts']}")
        print(f"upstream_counts={result['upstream_counts']}")
        print(f"unavailable_upstreams={result['unavailable_upstreams']}")
        print(f"discovery_errors={result['discovery_errors']}")
        if (
                result["status"] != "ok"
                or result["unavailable_upstreams"]
                or result["discovery_errors"]
        ):
            return 1
        if discovery_only:
            return 0

        all_access_checks_ok = True
        for scenario in SMOKE_SCENARIOS:
            access_result = await run_access_check(runtime, scenario)
            print(
                f"{scenario.label}_status={access_result['status']} "
                f"capability_id={access_result.get('capability_id')} "
                f"summary={_one_line(access_result.get('summary', ''))}"
            )
            if access_result["status"] != "ok":
                all_access_checks_ok = False
        return 0 if all_access_checks_ok else 1
    finally:
        await runtime.async_shutdown()


def _one_line(value: Any, *, max_length: int = 120) -> str:
    text = " ".join(str(value).split())
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test real learn-mcp-server discovery and access.",
    )
    parser.add_argument(
        "--config",
        default="mcp-conductor.config.json",
        help="Path to the mcp-conductor upstream config file.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Maximum capabilities to fetch from the gateway listing.",
    )
    parser.add_argument(
        "--discovery-only",
        action="store_true",
        help="Only verify capability discovery; skip route-token-gated access checks.",
    )
    args = parser.parse_args()
    return asyncio.run(
        run_smoke(
            args.config,
            args.limit,
            discovery_only=args.discovery_only,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
