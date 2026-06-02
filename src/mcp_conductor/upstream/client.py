"""Wrapper for one configured upstream MCP server client."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StdioTransport, StreamableHttpTransport

from mcp_conductor.config.schema import TransportType, UpstreamServerConfig


class UpstreamClientConfigurationError(ValueError):
    """Raised when a configured upstream client cannot be created."""


class UpstreamClientNotConnected(RuntimeError):
    """Raised when a call is attempted before a session exists."""


@dataclass(slots=True)
class UpstreamClient:
    """Internal client wrapper for exactly one upstream MCP server."""

    config: UpstreamServerConfig
    session: Any | None = None
    session_factory: Callable[[UpstreamServerConfig], Any] | None = None
    _connected: bool = False

    @property
    def server_id(self) -> str:
        """Return the stable upstream server id."""
        return self.config.server_id

    async def connect(self) -> None:
        """Create and enter the upstream session if it is not already connected."""
        if self.session is None:
            factory = self.session_factory or create_fastmcp_session
            self.session = factory(self.config)
        session = self._require_session()
        if self._connected:
            return
        enter = getattr(session, "__aenter__", None)
        if enter is not None:
            await enter()
        self._connected = True

    async def shutdown(self) -> None:
        """Exit the upstream session if it has been connected."""
        if not self._connected or self.session is None:
            return
        exit_ = getattr(self.session, "__aexit__", None)
        if exit_ is not None:
            await exit_(None, None, None)
        self._connected = False

    def list_tools(self) -> list[dict[str, Any]]:
        """Synchronously list upstream tools and normalize them to dictionaries."""
        session = self._require_session()
        response = session.list_tools()
        tools = self._extract_list_response(response, "tools")
        return [self._normalize_tool(tool) for tool in tools]

    async def list_tools_async(self) -> list[dict[str, Any]]:
        """Asynchronously list upstream tools and normalize them to dictionaries."""
        session = self._require_session()
        response = await self._maybe_await(session.list_tools())
        tools = self._extract_list_response(response, "tools")
        return [self._normalize_tool(tool) for tool in tools]

    def list_resources(self) -> list[dict[str, Any]]:
        """Synchronously list upstream resources for discovery and display."""
        session = self._require_session()
        response = session.list_resources()
        resources = self._extract_list_response(response, "resources")
        return [self._normalize_resource(resource) for resource in resources]

    async def list_resources_async(self) -> list[dict[str, Any]]:
        """Asynchronously list upstream resources for discovery and display."""
        session = self._require_session()
        response = await self._maybe_await(session.list_resources())
        resources = self._extract_list_response(response, "resources")
        return [self._normalize_resource(resource) for resource in resources]

    def list_resource_templates(self) -> list[dict[str, Any]]:
        """Synchronously list parameterized upstream resource templates."""
        session = self._require_session()
        response = session.list_resource_templates()
        templates = self._extract_list_response(response, "resourceTemplates")
        return [self._normalize_resource_template(template) for template in templates]

    async def list_resource_templates_async(self) -> list[dict[str, Any]]:
        """Asynchronously list parameterized upstream resource templates."""
        session = self._require_session()
        response = await self._maybe_await(session.list_resource_templates())
        templates = self._extract_list_response(response, "resourceTemplates")
        return [self._normalize_resource_template(template) for template in templates]

    def list_prompts(self) -> list[dict[str, Any]]:
        """Synchronously list upstream prompts for discovery and display."""
        session = self._require_session()
        response = session.list_prompts()
        prompts = self._extract_list_response(response, "prompts")
        return [self._normalize_prompt(prompt) for prompt in prompts]

    async def list_prompts_async(self) -> list[dict[str, Any]]:
        """Asynchronously list upstream prompts for discovery and display."""
        session = self._require_session()
        response = await self._maybe_await(session.list_prompts())
        prompts = self._extract_list_response(response, "prompts")
        return [self._normalize_prompt(prompt) for prompt in prompts]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Synchronously forward a validated tool call to the upstream server."""
        session = self._require_session()
        return self._normalize_result(session.call_tool(name, arguments))

    async def call_tool_async(self, name: str, arguments: dict[str, Any]) -> Any:
        """Asynchronously forward a validated tool call to the upstream server."""
        session = self._require_session()
        response = await self._maybe_await(session.call_tool(name, arguments))
        return self._normalize_result(response)

    def read_resource(self, uri: str) -> Any:
        """Synchronously read one upstream resource and normalize the content."""
        session = self._require_session()
        response = session.read_resource(uri)
        return self._to_plain_data(response)

    async def read_resource_async(self, uri: str) -> Any:
        """Asynchronously read one upstream resource and normalize the content."""
        session = self._require_session()
        response = await self._maybe_await(session.read_resource(uri))
        return self._to_plain_data(response)

    def get_prompt(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Synchronously get one upstream prompt with validated arguments."""
        session = self._require_session()
        response = session.get_prompt(name, arguments or {})
        return self._to_plain_data(response)

    async def get_prompt_async(
            self,
            name: str,
            arguments: dict[str, Any] | None = None,
    ) -> Any:
        """Asynchronously get one upstream prompt with validated arguments."""
        session = self._require_session()
        response = await self._maybe_await(session.get_prompt(name, arguments or {}))
        return self._to_plain_data(response)

    def _require_session(self) -> Any:
        """Return the current session or fail with a clear lifecycle error."""
        if self.session is None:
            raise UpstreamClientNotConnected(
                f"Upstream client {self.server_id!r} is not connected."
            )
        return self.session

    def _normalize_tool(self, tool: Any) -> dict[str, Any]:
        """Normalize SDK tool objects and test dictionaries into one shape."""
        return {
            "name": self._get_value(tool, "name"),
            "description": self._get_value(tool, "description"),
            "input_schema": (
                    self._get_value(tool, "input_schema", default=None)
                    or self._get_value(tool, "inputSchema", default={})
            ),
            "annotations": self._normalize_annotations(
                self._get_value(tool, "annotations", default=None)
            ),
        }

    def _normalize_resource(self, resource: Any) -> dict[str, Any]:
        """Normalize resource objects and preserve URI metadata."""
        return {
            "uri": str(self._get_value(resource, "uri")),
            "name": self._get_value(resource, "name"),
            "description": self._get_value(resource, "description"),
            "mime_type": (
                    self._get_value(resource, "mime_type", default=None)
                    or self._get_value(resource, "mimeType")
            ),
        }

    def _normalize_resource_template(self, template: Any) -> dict[str, Any]:
        """Normalize resource template objects and preserve URI template metadata."""
        return {
            "uri_template": (
                    self._get_value(template, "uri_template", default=None)
                    or self._get_value(template, "uriTemplate")
            ),
            "name": self._get_value(template, "name"),
            "description": self._get_value(template, "description"),
            "mime_type": (
                    self._get_value(template, "mime_type", default=None)
                    or self._get_value(template, "mimeType")
            ),
        }

    def _normalize_prompt(self, prompt: Any) -> dict[str, Any]:
        """Normalize prompt metadata and argument definitions."""
        return {
            "name": self._get_value(prompt, "name"),
            "description": self._get_value(prompt, "description"),
            "arguments": [
                self._normalize_prompt_argument(argument)
                for argument in self._get_value(prompt, "arguments", default=[])
            ],
        }

    def _normalize_prompt_argument(self, argument: Any) -> dict[str, Any]:
        """Normalize one prompt argument definition."""
        return {
            "name": self._get_value(argument, "name"),
            "description": self._get_value(argument, "description"),
            "required": self._get_value(argument, "required", default=False),
        }

    def _get_value(self, value: Any, key: str, default: Any = None) -> Any:
        """Read either a dictionary key or an object attribute."""
        if value is None:
            return default
        if isinstance(value, dict):
            return value.get(key, default)
        return getattr(value, key, default)

    def _normalize_annotations(self, annotations: Any | None) -> dict[str, Any]:
        """Normalize common MCP tool annotations into a dictionary."""
        if annotations is None:
            return {}
        if isinstance(annotations, dict):
            return dict(annotations)
        normalized: dict[str, Any] = {}
        for key in (
            "readOnlyHint",
            "destructiveHint",
            "idempotentHint",
            "openWorldHint",
        ):
            value = getattr(annotations, key, None)
            if value is not None:
                normalized[key] = value
        return normalized

    async def _maybe_await(self, value: Any) -> Any:
        """Accept both sync fake sessions and awaitable real session results."""
        if inspect.isawaitable(value):
            return await value
        return value

    def _extract_list_response(self, response: Any, key: str) -> list[Any]:
        """Extract list payloads from either raw lists or MCP response objects."""
        if isinstance(response, list):
            return response
        return list(self._get_value(response, key, default=[]))

    def _normalize_result(self, response: Any) -> Any:
        """Prefer response.data when present, otherwise keep the raw response."""
        data = self._get_value(response, "data", default=None)
        if data is not None:
            return data
        return response

    def _to_plain_data(self, value: Any) -> Any:
        """Convert MCP SDK models and test doubles into JSON-like data."""
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            return model_dump(mode="json", by_alias=True, exclude_none=True)
        if isinstance(value, list):
            return [self._to_plain_data(item) for item in value]
        if isinstance(value, dict):
            return {
                key: self._to_plain_data(item)
                for key, item in value.items()
            }
        if hasattr(value, "__dict__"):
            return {
                key: self._to_plain_data(item)
                for key, item in vars(value).items()
                if not key.startswith("_")
            }
        return value


def create_fastmcp_session(config: UpstreamServerConfig) -> Client:
    """Create a FastMCP client session from an upstream server configuration."""
    if config.transport == TransportType.STDIO:
        if not config.command:
            raise UpstreamClientConfigurationError(
                f"Upstream server {config.server_id!r} requires a stdio command."
            )
        return Client(
            StdioTransport(
                command=config.command,
                args=config.args,
                env=config.env or None,
                cwd=config.cwd,
            )
        )

    if config.transport == TransportType.STREAMABLE_HTTP:
        if not config.url:
            raise UpstreamClientConfigurationError(
                f"Upstream server {config.server_id!r} requires a streamable HTTP URL."
            )
        return Client(StreamableHttpTransport(config.url))

    raise UpstreamClientConfigurationError(
        f"Unsupported upstream transport: {config.transport!s}"
    )
