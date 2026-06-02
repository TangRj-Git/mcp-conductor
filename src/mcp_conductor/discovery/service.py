"""Capability discovery for connected upstream MCP servers."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from mcp_conductor.models import Capability, CapabilityType, RiskLevel
from mcp_conductor.policy.risk import infer_risk_level


@dataclass(slots=True)
class CapabilityDiscoveryService:
    """Discover tools, resources, templates, and prompts from connected clients."""

    upstream_manager: Any
    errors: list[dict[str, str]] = field(default_factory=list)

    def discover(self) -> list[Capability]:
        """Synchronous discovery entry point used by tests and sync callers."""
        self.errors.clear()
        capabilities: list[Capability] = []
        for server_id, client in self.upstream_manager.clients.items():
            # Discover each capability type independently so one failed list call
            # does not hide other capabilities from the same server.
            capabilities.extend(
                self._discover_tools(server_id=server_id, client=client)
            )
            capabilities.extend(
                self._discover_resources(server_id=server_id, client=client)
            )
            capabilities.extend(
                self._discover_resource_templates(server_id=server_id, client=client)
            )
            capabilities.extend(
                self._discover_prompts(server_id=server_id, client=client)
            )
        return capabilities

    async def discover_async(self) -> list[Capability]:
        """Async discovery entry point used by the normal FastMCP lifecycle."""
        self.errors.clear()
        capabilities: list[Capability] = []
        for server_id, client in self.upstream_manager.clients.items():
            capabilities.extend(
                self._convert_items(
                    server_id=server_id,
                    capability_type="tool",
                    items=await self._call_optional_list_async(
                        client,
                        "list_tools",
                        server_id,
                        "tool",
                    ),
                    converter=lambda tool, server_id=server_id: self._tool_to_capability(
                        server_id=server_id,
                        tool=tool,
                    ),
                )
            )
            capabilities.extend(
                self._convert_items(
                    server_id=server_id,
                    capability_type="resource",
                    items=await self._call_optional_list_async(
                        client,
                        "list_resources",
                        server_id,
                        "resource",
                    ),
                    converter=lambda resource, server_id=server_id: self._resource_to_capability(
                        server_id=server_id,
                        resource=resource,
                    ),
                )
            )
            capabilities.extend(
                self._convert_items(
                    server_id=server_id,
                    capability_type="resource_template",
                    items=await self._call_optional_list_async(
                        client,
                        "list_resource_templates",
                        server_id,
                        "resource_template",
                    ),
                    converter=lambda resource_template, server_id=server_id: (
                        self._resource_template_to_capability(
                            server_id=server_id,
                            resource_template=resource_template,
                        )
                    ),
                )
            )
            capabilities.extend(
                self._convert_items(
                    server_id=server_id,
                    capability_type="prompt",
                    items=await self._call_optional_list_async(
                        client,
                        "list_prompts",
                        server_id,
                        "prompt",
                    ),
                    converter=lambda prompt, server_id=server_id: self._prompt_to_capability(
                        server_id=server_id,
                        prompt=prompt,
                    ),
                )
            )
        return capabilities

    def _discover_tools(self, server_id: str, client: Any) -> list[Capability]:
        """Discover and convert tools from one upstream server."""
        return self._convert_items(
            server_id=server_id,
            capability_type="tool",
            items=self._call_optional_list(
                server_id,
                client,
                "list_tools",
                "tool",
            ),
            converter=lambda tool: self._tool_to_capability(
                server_id=server_id,
                tool=tool,
            ),
        )

    def _discover_resources(self, server_id: str, client: Any) -> list[Capability]:
        """Discover and convert resources from one upstream server."""
        return self._convert_items(
            server_id=server_id,
            capability_type="resource",
            items=self._call_optional_list(
                server_id,
                client,
                "list_resources",
                "resource",
            ),
            converter=lambda resource: self._resource_to_capability(
                server_id=server_id,
                resource=resource,
            ),
        )

    def _discover_resource_templates(
            self,
            server_id: str,
            client: Any,
    ) -> list[Capability]:
        """Discover and convert resource templates from one upstream server."""
        return self._convert_items(
            server_id=server_id,
            capability_type="resource_template",
            items=self._call_optional_list(
                server_id,
                client,
                "list_resource_templates",
                "resource_template",
            ),
            converter=lambda resource_template: self._resource_template_to_capability(
                server_id=server_id,
                resource_template=resource_template,
            ),
        )

    def _discover_prompts(self, server_id: str, client: Any) -> list[Capability]:
        """Discover and convert prompts from one upstream server."""
        return self._convert_items(
            server_id=server_id,
            capability_type="prompt",
            items=self._call_optional_list(
                server_id,
                client,
                "list_prompts",
                "prompt",
            ),
            converter=lambda prompt: self._prompt_to_capability(
                server_id=server_id,
                prompt=prompt,
            ),
        )

    def _tool_to_capability(self, server_id: str, tool: Any) -> Capability:
        """Convert one upstream tool listing into an executable capability."""
        name = self._get_value(tool, "name")
        if not name:
            raise ValueError("tool missing required identifier")
        description = self._get_value(tool, "description")
        annotations = self._get_value(tool, "annotations")
        risk_level = infer_risk_level(
            name=name,
            description=description,
            annotations=annotations,
        )
        return Capability(
            capability_id=f"{server_id}.tools.{name}",
            capability_type=CapabilityType.TOOL,
            upstream_server_id=server_id,
            upstream_client_id=server_id,
            original_name_or_uri=name,
            description=description,
            schema_or_metadata=(
                    self._get_value(tool, "input_schema", default=None)
                    or self._get_value(tool, "inputSchema", default={})
            ),
            tags=[server_id],
            risk_level=risk_level,
            # This is only a hint; runtime policy checks still decide execution.
            read_only_hint=self._read_only_hint(annotations, risk_level),
        )

    def _resource_to_capability(self, server_id: str, resource: Any) -> Capability:
        """Convert one upstream resource listing into a display capability."""
        uri = self._get_value(resource, "uri")
        if not uri:
            raise ValueError("resource missing required identifier")
        description = self._get_value(resource, "description")
        return Capability(
            capability_id=self._capability_id(server_id, "resources", uri),
            capability_type=CapabilityType.RESOURCE,
            upstream_server_id=server_id,
            upstream_client_id=server_id,
            original_name_or_uri=uri,
            description=description,
            schema_or_metadata={
                "uri": uri,
                "name": self._get_value(resource, "name"),
                "mime_type": (
                        self._get_value(resource, "mime_type", default=None)
                        or self._get_value(resource, "mimeType")
                ),
            },
            tags=[server_id],
            risk_level=RiskLevel.READ_ONLY,
            read_only_hint=True,
        )

    def _resource_template_to_capability(
            self,
            server_id: str,
            resource_template: Any,
    ) -> Capability:
        """Convert one parameterized resource template into a display capability."""
        uri_template = (
                self._get_value(resource_template, "uri_template", default=None)
                or self._get_value(resource_template, "uriTemplate")
        )
        if not uri_template:
            raise ValueError("resource_template missing required identifier")
        description = self._get_value(resource_template, "description")
        return Capability(
            capability_id=self._capability_id(
                server_id,
                "resource_templates",
                uri_template,
            ),
            capability_type=CapabilityType.RESOURCE_TEMPLATE,
            upstream_server_id=server_id,
            upstream_client_id=server_id,
            original_name_or_uri=uri_template,
            description=description,
            schema_or_metadata={
                "uri_template": uri_template,
                "name": self._get_value(resource_template, "name"),
                "mime_type": (
                        self._get_value(resource_template, "mime_type", default=None)
                        or self._get_value(resource_template, "mimeType")
                ),
            },
            tags=[server_id],
            risk_level=RiskLevel.READ_ONLY,
            read_only_hint=True,
        )

    def _prompt_to_capability(self, server_id: str, prompt: Any) -> Capability:
        """Convert one upstream prompt listing into a display capability."""
        name = self._get_value(prompt, "name")
        if not name:
            raise ValueError("prompt missing required identifier")
        description = self._get_value(prompt, "description")
        return Capability(
            capability_id=f"{server_id}.prompts.{name}",
            capability_type=CapabilityType.PROMPT,
            upstream_server_id=server_id,
            upstream_client_id=server_id,
            original_name_or_uri=name,
            description=description,
            schema_or_metadata={
                "name": name,
                "arguments": self._get_value(prompt, "arguments", default=[]),
            },
            tags=[server_id],
            risk_level=RiskLevel.READ_ONLY,
            read_only_hint=True,
        )

    def _capability_id(self, server_id: str, collection: str, raw_id: str) -> str:
        """Build stable capability ids for URI-like identifiers."""
        return f"{server_id}.{collection}.{quote(raw_id, safe='')}"

    def _call_optional_list(
            self,
            server_id: str,
            client: Any,
            method_name: str,
            capability_type: str,
    ) -> list[Any]:
        """Call an optional synchronous list method and record local failures."""
        method = getattr(client, method_name, None)
        if method is None:
            return []
        try:
            return list(method())
        except Exception as exc:
            self._record_error(
                server_id=server_id,
                operation=method_name,
                capability_type=capability_type,
                exc=exc,
            )
            return []

    def _convert_items(
            self,
            *,
            server_id: str,
            capability_type: str,
            items: list[Any],
            converter: Callable[[Any], Capability],
    ) -> list[Capability]:
        """Convert discovered items while isolating malformed upstream entries."""
        capabilities: list[Capability] = []
        for item in items:
            try:
                capabilities.append(converter(item))
            except Exception as exc:
                self._record_error(
                    server_id=server_id,
                    operation="convert",
                    capability_type=capability_type,
                    exc=exc,
                )
        return capabilities

    async def _call_optional_list_async(
            self,
            client: Any,
            method_name: str,
            server_id: str | None = None,
            capability_type: str | None = None,
    ) -> list[Any]:
        """Call an optional async list method, falling back to sync clients."""
        method = getattr(client, f"{method_name}_async", None)
        if method is None:
            method = getattr(client, method_name, None)
        if method is None:
            return []
        try:
            value = method()
            if inspect.isawaitable(value):
                value = await value
            return list(value)
        except Exception as exc:
            if server_id is not None and capability_type is not None:
                self._record_error(
                    server_id=server_id,
                    operation=method_name,
                    capability_type=capability_type,
                    exc=exc,
                )
            return []

    def _record_error(
            self,
            *,
            server_id: str,
            operation: str,
            capability_type: str,
            exc: Exception,
    ) -> None:
        """Store a discovery error for later diagnostics."""
        self.errors.append(
            {
                "upstream_server_id": server_id,
                "capability_type": capability_type,
                "operation": operation,
                "error": str(exc),
            }
        )

    def _read_only_hint(
            self,
            annotations: Any | None,
            risk_level: RiskLevel,
    ) -> bool:
        read_only_hint = self._get_value(annotations, "readOnlyHint", default=None)
        if read_only_hint is not None:
            return bool(read_only_hint) and risk_level == RiskLevel.READ_ONLY
        return risk_level == RiskLevel.READ_ONLY

    def _get_value(self, value: Any, key: str, default: Any = None) -> Any:
        """Read either dict keys or object attributes from MCP SDK results."""
        if isinstance(value, dict):
            return value.get(key, default)
        return getattr(value, key, default)
