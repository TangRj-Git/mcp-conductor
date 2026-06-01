from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from mcp_conductor.config.schema import GatewayConfig, RiskPolicy

from .client import UpstreamClient


@dataclass(slots=True)
class UpstreamClientManager:
    config: GatewayConfig
    clients: dict[str, UpstreamClient] = field(default_factory=dict)
    startup_errors: dict[str, str] = field(default_factory=dict)
    client_factory: Callable[..., UpstreamClient] = UpstreamClient

    def startup(self) -> None:
        self.startup_errors.clear()
        for server_id, server_config in self.config.upstream_servers.items():
            if server_config.disabled or server_config.risk_policy == RiskPolicy.DISABLED:
                continue
            self.clients[server_id] = self.client_factory(server_config)

    async def astartup(self) -> None:
        self.startup()
        for server_id, client in list(self.clients.items()):
            try:
                await client.connect()
            except Exception as exc:
                self.startup_errors[server_id] = str(exc)
                self.clients.pop(server_id, None)
                await self._shutdown_failed_client(client)

    def shutdown(self) -> None:
        self.clients.clear()

    async def ashutdown(self) -> None:
        try:
            for client in list(self.clients.values()):
                await client.shutdown()
        finally:
            self.shutdown()

    def get_client(self, server_id: str) -> UpstreamClient:
        return self.clients[server_id]

    async def _shutdown_failed_client(self, client: UpstreamClient) -> None:
        try:
            await client.shutdown()
        except Exception:
            pass
