from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Any

from mcp_conductor.models import Capability


@dataclass(slots=True)
class GatewayExecutionEngine:
    upstream_manager: Any

    def call_tool(self, capability: Capability, arguments: dict[str, Any]) -> Any:
        client = self.upstream_manager.get_client(capability.upstream_server_id)
        return client.call_tool(capability.original_name_or_uri, arguments)

    async def call_tool_async(
            self,
            capability: Capability,
            arguments: dict[str, Any],
    ) -> Any:
        client = self.upstream_manager.get_client(capability.upstream_server_id)
        call_tool_async = getattr(client, "call_tool_async", None)
        if call_tool_async is not None:
            return await call_tool_async(capability.original_name_or_uri, arguments)

        result = client.call_tool(capability.original_name_or_uri, arguments)
        if inspect.isawaitable(result):
            return await result
        return result
