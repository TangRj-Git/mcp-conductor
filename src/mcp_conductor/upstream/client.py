from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Any, Callable

from fastmcp import Client
from fastmcp.client.transports import StdioTransport, StreamableHttpTransport

from mcp_conductor.config.schema import TransportType, UpstreamServerConfig


class UpstreamClientConfigurationError(ValueError):
    """Raised when an upstream client cannot be built from its config."""


class UpstreamClientNotConnected(RuntimeError):
    """Raised when an upstream client is used before a session is attached."""


@dataclass(slots=True)
class UpstreamClient:
    config: UpstreamServerConfig
    session: Any | None = None
    session_factory: Callable[[UpstreamServerConfig], Any] | None = None
    _connected: bool = False

    @property
    def server_id(self) -> str:
        return self.config.server_id

    async def connect(self) -> None:
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
        if not self._connected or self.session is None:
            return
        exit_ = getattr(self.session, "__aexit__", None)
        if exit_ is not None:
            await exit_(None, None, None)
        self._connected = False

    def list_tools(self) -> list[dict[str, Any]]:
        session = self._require_session()
        response = session.list_tools()
        tools = self._extract_list_response(response, "tools")
        return [self._normalize_tool(tool) for tool in tools]

    async def list_tools_async(self) -> list[dict[str, Any]]:
        session = self._require_session()
        response = await self._maybe_await(session.list_tools())
        tools = self._extract_list_response(response, "tools")
        return [self._normalize_tool(tool) for tool in tools]

    def list_resources(self) -> list[dict[str, Any]]:
        session = self._require_session()
        response = session.list_resources()
        resources = self._extract_list_response(response, "resources")
        return [self._normalize_resource(resource) for resource in resources]

    async def list_resources_async(self) -> list[dict[str, Any]]:
        session = self._require_session()
        response = await self._maybe_await(session.list_resources())
        resources = self._extract_list_response(response, "resources")
        return [self._normalize_resource(resource) for resource in resources]

    def list_resource_templates(self) -> list[dict[str, Any]]:
        session = self._require_session()
        response = session.list_resource_templates()
        templates = self._extract_list_response(response, "resourceTemplates")
        return [self._normalize_resource_template(template) for template in templates]

    async def list_resource_templates_async(self) -> list[dict[str, Any]]:
        session = self._require_session()
        response = await self._maybe_await(session.list_resource_templates())
        templates = self._extract_list_response(response, "resourceTemplates")
        return [self._normalize_resource_template(template) for template in templates]

    def list_prompts(self) -> list[dict[str, Any]]:
        session = self._require_session()
        response = session.list_prompts()
        prompts = self._extract_list_response(response, "prompts")
        return [self._normalize_prompt(prompt) for prompt in prompts]

    async def list_prompts_async(self) -> list[dict[str, Any]]:
        session = self._require_session()
        response = await self._maybe_await(session.list_prompts())
        prompts = self._extract_list_response(response, "prompts")
        return [self._normalize_prompt(prompt) for prompt in prompts]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        session = self._require_session()
        return self._normalize_result(session.call_tool(name, arguments))

    async def call_tool_async(self, name: str, arguments: dict[str, Any]) -> Any:
        session = self._require_session()
        response = await self._maybe_await(session.call_tool(name, arguments))
        return self._normalize_result(response)

    def _require_session(self) -> Any:
        if self.session is None:
            raise UpstreamClientNotConnected(
                f"Upstream client {self.server_id!r} is not connected."
            )
        return self.session

    def _normalize_tool(self, tool: Any) -> dict[str, Any]:
        return {
            "name": self._get_value(tool, "name"),
            "description": self._get_value(tool, "description"),
            "input_schema": (
                    self._get_value(tool, "input_schema", default=None)
                    or self._get_value(tool, "inputSchema", default={})
            ),
        }

    def _normalize_resource(self, resource: Any) -> dict[str, Any]:
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
        return {
            "name": self._get_value(prompt, "name"),
            "description": self._get_value(prompt, "description"),
            "arguments": [
                self._normalize_prompt_argument(argument)
                for argument in self._get_value(prompt, "arguments", default=[])
            ],
        }

    def _normalize_prompt_argument(self, argument: Any) -> dict[str, Any]:
        return {
            "name": self._get_value(argument, "name"),
            "description": self._get_value(argument, "description"),
            "required": self._get_value(argument, "required", default=False),
        }

    def _get_value(self, value: Any, key: str, default: Any = None) -> Any:
        if isinstance(value, dict):
            return value.get(key, default)
        return getattr(value, key, default)

    async def _maybe_await(self, value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    def _extract_list_response(self, response: Any, key: str) -> list[Any]:
        if isinstance(response, list):
            return response
        return list(self._get_value(response, key, default=[]))

    def _normalize_result(self, response: Any) -> Any:
        data = self._get_value(response, "data", default=None)
        if data is not None:
            return data
        return response


def create_fastmcp_session(config: UpstreamServerConfig) -> Client:
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
