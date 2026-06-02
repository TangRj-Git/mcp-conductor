from __future__ import annotations

from mcp_conductor.routing.sampled_router import HostSampledRouter


def test_host_sampled_router_returns_structured_unsupported_response() -> None:
    result = HostSampledRouter().recommend()

    assert result == {
        "status": "unsupported",
        "reason": "host_sampled_routing_not_configured",
    }
