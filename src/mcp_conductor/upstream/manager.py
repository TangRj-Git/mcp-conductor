"""Manage the set of configured upstream MCP clients."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field

from mcp_conductor.config.schema import GatewayConfig, RiskPolicy

from .client import UpstreamClient


@dataclass(slots=True)
class UpstreamClientManager:
    """Create, connect, and shut down all enabled upstream clients."""

    config: GatewayConfig
    clients: dict[str, UpstreamClient] = field(default_factory=dict)
    startup_errors: dict[str, str] = field(default_factory=dict)
    shutdown_errors: dict[str, str] = field(default_factory=dict)
    client_factory: Callable[..., UpstreamClient] = UpstreamClient

    def startup(self) -> None:
        """Create client wrappers without opening async upstream sessions."""
        self.startup_errors.clear()
        self.shutdown_errors.clear()
        self.clients.clear()
        for server_id, server_config in self.config.upstream_servers.items():
            if server_config.disabled or server_config.risk_policy == RiskPolicy.DISABLED:
                continue
            self.clients[server_id] = self.client_factory(server_config)

    async def astartup(self) -> None:
        """Create clients and connect to each enabled upstream server."""
        self.startup()
        for server_id, client in list(self.clients.items()):
            try:
                await client.connect()
            except Exception as exc:
                self.startup_errors[server_id] = str(exc)
                self.clients.pop(server_id, None)
                await self._shutdown_failed_client(client)

    def shutdown(self) -> None:
        """Clear local client state for the synchronous lifecycle path."""
        self.clients.clear()

    async def ashutdown(self) -> None:
        """Close all connected upstream clients and clear manager state."""
        self.shutdown_errors.clear()
        try:
            for server_id, client in list(self.clients.items()):
                try:
                    await client.shutdown()
                except Exception as exc:
                    self.shutdown_errors[server_id] = str(exc)
        finally:
            self.shutdown()

    def get_client(self, server_id: str) -> UpstreamClient:
        """Return the client wrapper used to execute calls for one server."""
        return self.clients[server_id]

    async def _shutdown_failed_client(self, client: UpstreamClient) -> None:
        """Best-effort cleanup for a client that failed during startup."""
        with suppress(Exception):
            await client.shutdown()
