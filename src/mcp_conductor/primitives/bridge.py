from __future__ import annotations


class UpstreamPrimitiveBridge:
    """Conservative bridge for upstream Server requests to client primitives."""

    def handle_sampling_request(self) -> dict:
        return {"status": "unsupported", "reason": "upstream_sampling_disabled"}

    def handle_elicitation_request(self) -> dict:
        return {"status": "unsupported", "reason": "upstream_elicitation_disabled"}
