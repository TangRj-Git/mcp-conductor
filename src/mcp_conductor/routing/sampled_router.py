"""Conservative boundary for future host-sampled routing."""

from __future__ import annotations


class HostSampledRouter:
    """Reserved integration point for MCP Sampling based routing."""

    def recommend(self) -> dict[str, str]:
        """Return a structured fallback until host-sampled routing is configured."""
        return {
            "status": "unsupported",
            "reason": "host_sampled_routing_not_configured",
        }
