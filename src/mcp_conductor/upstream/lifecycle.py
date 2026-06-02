"""No-op lifecycle boundary for upstream process management."""

from __future__ import annotations


class UpstreamLifecycle:
    """Reserved hook for process, reconnect, and health-check lifecycle concerns."""

    def close(self) -> None:
        """Release lifecycle resources when the class starts owning any."""
