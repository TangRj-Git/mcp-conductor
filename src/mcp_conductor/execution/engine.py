from __future__ import annotations

import inspect
from dataclasses import dataclass
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

    def read_resource(self, capability: Capability) -> Any:
        client = self.upstream_manager.get_client(capability.upstream_server_id)
        return client.read_resource(capability.original_name_or_uri)

    async def read_resource_async(self, capability: Capability) -> Any:
        client = self.upstream_manager.get_client(capability.upstream_server_id)
        read_resource_async = getattr(client, "read_resource_async", None)
        if read_resource_async is not None:
            return await read_resource_async(capability.original_name_or_uri)

        result = client.read_resource(capability.original_name_or_uri)
        if inspect.isawaitable(result):
            return await result
        return result

    def read_resource_uri(self, capability: Capability, uri: str) -> Any:
        client = self.upstream_manager.get_client(capability.upstream_server_id)
        return client.read_resource(uri)

    async def read_resource_uri_async(self, capability: Capability, uri: str) -> Any:
        client = self.upstream_manager.get_client(capability.upstream_server_id)
        read_resource_async = getattr(client, "read_resource_async", None)
        if read_resource_async is not None:
            return await read_resource_async(uri)

        result = client.read_resource(uri)
        if inspect.isawaitable(result):
            return await result
        return result

    def get_prompt(self, capability: Capability, arguments: dict[str, Any]) -> Any:
        client = self.upstream_manager.get_client(capability.upstream_server_id)
        return client.get_prompt(capability.original_name_or_uri, arguments)

    async def get_prompt_async(
            self,
            capability: Capability,
            arguments: dict[str, Any],
    ) -> Any:
        client = self.upstream_manager.get_client(capability.upstream_server_id)
        get_prompt_async = getattr(client, "get_prompt_async", None)
        if get_prompt_async is not None:
            return await get_prompt_async(capability.original_name_or_uri, arguments)

        result = client.get_prompt(capability.original_name_or_uri, arguments)
        if inspect.isawaitable(result):
            return await result
        return result
