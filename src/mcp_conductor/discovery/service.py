from __future__ import annotations

from dataclasses import dataclass, field
import inspect
from typing import Any
from urllib.parse import quote

from mcp_conductor.models import Capability, CapabilityType, RiskLevel
from mcp_conductor.policy.risk import infer_risk_level

"""
discovery/service.py

这个文件负责“能力发现”。

能力发现发生在 mcp-conductor 启动并连接上游 MCP Server 之后。
它会遍历 upstream_manager 中已经连接成功的上游 Client，然后分别询问上游：

- 你有哪些 tools？
- 你有哪些 resources？
- 你有哪些 resource templates？
- 你有哪些 prompts？

上游返回的数据格式可能来自 FastMCP / MCP SDK 的对象，也可能是测试里构造的 dict。
所以本文件会把这些不同形态的数据统一转换成 mcp-conductor 内部的 Capability。

Capability 是后续所有流程的统一基础：
- list_upstream_capabilities 用它展示能力摘要。
- routing/cards.py 用它生成能力卡片。
- recommend_capabilities 用它筛选和推荐能力。
- call_upstream_tool 用它找到真正的上游 Server 和工具名。

注意：
- 第一版只有 tool 会进入完整调用链路。
- resource / resource template / prompt 当前只做发现和展示。
- 单个上游或单类能力发现失败时，不应该拖垮整个网关。
  因此这里采用“尽力发现”的策略，并把错误记录到 errors 中。
"""


@dataclass(slots=True)
class CapabilityDiscoveryService:
    """
    上游能力发现服务。

    upstream_manager:
        保存所有已经连接成功的上游 Client。
        这里不负责启动上游，也不负责连接上游，只使用已经准备好的 Client。

    errors:
        记录能力发现过程中的局部错误。
        例如某个上游 Server 的 tools/list 失败，但 resources/list 成功，
        那么 tools/list 的失败会记录在这里，而不是直接抛出中断整个启动流程。
    """

    upstream_manager: Any
    errors: list[dict[str, str]] = field(default_factory=list)

    def discover(self) -> list[Capability]:
        """
        同步版本的能力发现入口。

        这个方法主要用于同步测试或同步运行路径。
        它会遍历每个上游 Client，并依次发现四类能力：
        tool、resource、resource template、prompt。

        返回值是统一的 Capability 列表，而不是原始上游返回值。
        """
        self.errors.clear()
        capabilities: list[Capability] = []
        for server_id, client in self.upstream_manager.clients.items():
            # 每一类能力分别发现。这样某一类失败时，只会记录错误并返回空列表，
            # 不会影响同一个上游的其他能力类型，也不会影响其他上游 Server。
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
        """
        异步版本的能力发现入口。

        FastMCP Client 的 list_tools/list_resources 等方法通常是异步使用，
        因此 mcp-conductor 正常启动时主要走这个方法。

        这里仍然是顺序遍历每个上游和每类能力。
        第一版先保证清晰和可控；后续如果上游很多，可以再考虑并发发现。
        """
        self.errors.clear()
        capabilities: list[Capability] = []
        for server_id, client in self.upstream_manager.clients.items():
            # tools 是第一版唯一会进入完整执行链路的能力类型。
            # 这里先发现并转换成 CapabilityType.TOOL。
            capabilities.extend(
                [
                    self._tool_to_capability(server_id=server_id, tool=tool)
                    for tool in await self._call_optional_list_async(
                    client,
                    "list_tools",
                    server_id,
                    "tool",
                )
                ]
            )
            # resources 当前只发现和展示，不进入 call_upstream_tool 执行链路。
            capabilities.extend(
                [
                    self._resource_to_capability(server_id=server_id, resource=resource)
                    for resource in await self._call_optional_list_async(
                    client,
                    "list_resources",
                    server_id,
                    "resource",
                )
                ]
            )
            # resource templates 当前只发现和展示。
            # 后续如果要支持模板读取，需要新增专门的调用工具或资源读取链路。
            capabilities.extend(
                [
                    self._resource_template_to_capability(
                        server_id=server_id,
                        resource_template=resource_template,
                    )
                    for resource_template in await self._call_optional_list_async(
                    client,
                    "list_resource_templates",
                    server_id,
                    "resource_template",
                )
                ]
            )
            # prompts 当前只发现和展示。
            # 后续如果要支持 get_prompt，也应该单独设计，不要混进 call_upstream_tool。
            capabilities.extend(
                [
                    self._prompt_to_capability(server_id=server_id, prompt=prompt)
                    for prompt in await self._call_optional_list_async(
                    client,
                    "list_prompts",
                    server_id,
                    "prompt",
                )
                ]
            )
        return capabilities

    def _discover_tools(self, server_id: str, client: Any) -> list[Capability]:
        """同步发现单个上游 Server 的 tools，并转换成内部 Capability。"""
        return [
            self._tool_to_capability(server_id=server_id, tool=tool)
            for tool in self._call_optional_list(
                server_id,
                client,
                "list_tools",
                "tool",
            )
        ]

    def _discover_resources(self, server_id: str, client: Any) -> list[Capability]:
        """同步发现单个上游 Server 的 resources，并转换成内部 Capability。"""
        return [
            self._resource_to_capability(server_id=server_id, resource=resource)
            for resource in self._call_optional_list(
                server_id,
                client,
                "list_resources",
                "resource",
            )
        ]

    def _discover_resource_templates(
            self,
            server_id: str,
            client: Any,
    ) -> list[Capability]:
        """同步发现单个上游 Server 的 resource templates，并转换成内部 Capability。"""
        return [
            self._resource_template_to_capability(
                server_id=server_id,
                resource_template=resource_template,
            )
            for resource_template in self._call_optional_list(
                server_id,
                client,
                "list_resource_templates",
                "resource_template",
            )
        ]

    def _discover_prompts(self, server_id: str, client: Any) -> list[Capability]:
        """同步发现单个上游 Server 的 prompts，并转换成内部 Capability。"""
        return [
            self._prompt_to_capability(server_id=server_id, prompt=prompt)
            for prompt in self._call_optional_list(
                server_id,
                client,
                "list_prompts",
                "prompt",
            )
        ]

    def _tool_to_capability(self, server_id: str, tool: dict[str, Any]) -> Capability:
        """
        把上游 tool 转换成内部 Capability。

        上游 tool 的关键字段是：
        - name：真实调用上游 tools/call 时使用的工具名。
        - description：工具说明，后续会进入能力卡片和规则筛选。
        - input_schema / inputSchema：工具参数结构。

        capability_id 使用 `{server_id}.tools.{name}`，避免不同上游 Server
        中出现同名工具时互相冲突。
        """
        name = self._get_value(tool, "name")
        description = self._get_value(tool, "description")
        # tool 的风险等级需要根据工具名和描述推断。
        # 例如 delete/write/create/send 这类词通常会被判为更高风险。
        risk_level = infer_risk_level(name=name, description=description)
        return Capability(
            capability_id=f"{server_id}.tools.{name}",
            capability_type=CapabilityType.TOOL,
            upstream_server_id=server_id,
            upstream_client_id=server_id,
            # original_name_or_uri 对 tool 来说就是上游真实工具名。
            # 执行时 GatewayExecutionEngine 会用它调用 client.call_tool(...)。
            original_name_or_uri=name,
            description=description,
            schema_or_metadata=(
                    self._get_value(tool, "input_schema", default=None)
                    or self._get_value(tool, "inputSchema", default={})
            ),
            tags=[server_id],
            risk_level=risk_level,
            # read_only_hint 是提示，不是最终安全依据。
            # 执行时还会经过 risk_policy、Roots/allowlist 等校验。
            read_only_hint=risk_level == RiskLevel.READ_ONLY,
        )

    def _resource_to_capability(self, server_id: str, resource: Any) -> Capability:
        """
        把上游 resource 转换成内部 Capability。

        resource 通常代表一个可读取的 URI。
        第一版只把它放进能力注册表用于展示，不通过 call_upstream_tool 读取。
        """
        uri = self._get_value(resource, "uri")
        description = self._get_value(resource, "description")
        return Capability(
            capability_id=self._capability_id(server_id, "resources", uri),
            capability_type=CapabilityType.RESOURCE,
            upstream_server_id=server_id,
            upstream_client_id=server_id,
            # 对 resource 来说，原始标识是 URI。
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
            # MCP resource 通常是读取型能力，所以这里按只读处理。
            risk_level=RiskLevel.READ_ONLY,
            read_only_hint=True,
        )

    def _resource_template_to_capability(
            self,
            server_id: str,
            resource_template: Any,
    ) -> Capability:
        """
        把上游 resource template 转换成内部 Capability。

        resource template 是带参数的资源 URI 模板，例如：
        repo://owner/project/{path}

        第一版只发现和展示模板本身，不负责根据模板参数去读取资源。
        """
        uri_template = (
                self._get_value(resource_template, "uri_template", default=None)
                or self._get_value(resource_template, "uriTemplate")
        )
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
            # 对 resource template 来说，原始标识是 uri_template。
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
            # 模板本身不是写操作，按只读能力记录。
            risk_level=RiskLevel.READ_ONLY,
            read_only_hint=True,
        )

    def _prompt_to_capability(self, server_id: str, prompt: Any) -> Capability:
        """
        把上游 prompt 转换成内部 Capability。

        prompt 通常代表一个可获取的提示词模板。
        第一版只发现 prompt 的名称和参数信息，不直接执行 get_prompt。
        """
        name = self._get_value(prompt, "name")
        description = self._get_value(prompt, "description")
        return Capability(
            capability_id=f"{server_id}.prompts.{name}",
            capability_type=CapabilityType.PROMPT,
            upstream_server_id=server_id,
            upstream_client_id=server_id,
            # 对 prompt 来说，原始标识是 prompt name。
            original_name_or_uri=name,
            description=description,
            schema_or_metadata={
                "name": name,
                "arguments": self._get_value(prompt, "arguments", default=[]),
            },
            tags=[server_id],
            # prompt 获取本身按只读能力记录。
            risk_level=RiskLevel.READ_ONLY,
            read_only_hint=True,
        )

    def _capability_id(self, server_id: str, collection: str, raw_id: str) -> str:
        """
        为 resource / resource template 这类可能包含特殊字符的能力生成 ID。

        URI 里可能包含 `/`、`:`、`?` 等字符，直接拼进 capability_id 会很乱。
        所以这里用 quote 做 URL 编码，让 capability_id 更适合作为稳定 ID 使用。
        """
        return f"{server_id}.{collection}.{quote(raw_id, safe='')}"

    def _call_optional_list(
            self,
            server_id: str,
            client: Any,
            method_name: str,
            capability_type: str,
    ) -> list[Any]:
        """
        同步调用上游 Client 的某个 list 方法。

        为什么叫 optional：
        不同上游 Client 或测试替身不一定实现全部 list 方法。
        如果没有这个方法，就认为该类能力为空，而不是报错。

        如果方法存在但调用失败，会记录到 errors，并返回空列表。
        这就是“发现容错”的核心。
        """
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

    async def _call_optional_list_async(
            self,
            client: Any,
            method_name: str,
            server_id: str | None = None,
            capability_type: str | None = None,
    ) -> list[Any]:
        """
        异步调用上游 Client 的某个 list 方法。

        优先查找 `{method_name}_async`，例如 list_tools_async。
        如果没有异步方法，再退回同步方法。

        这样做是为了兼容：
        - 真实 FastMCP Client 的异步调用。
        - 单元测试里的同步 fake client。
        """
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
            # 发现失败只记录，不抛出。
            # 这样一个上游的 prompts/list 失败，不会影响 tools/list 或其他上游。
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
        """
        记录一次能力发现错误。

        这些错误最终会通过 list_upstream_capabilities 的 discovery_errors 返回，
        方便 Host 或用户知道“哪些上游能力没发现成功”。
        """
        self.errors.append(
            {
                "upstream_server_id": server_id,
                "capability_type": capability_type,
                "operation": operation,
                "error": str(exc),
            }
        )

    def _get_value(self, value: Any, key: str, default: Any = None) -> Any:
        """
        兼容 dict 和对象两种数据形态的取值工具。

        真实 MCP/FastMCP 返回值可能是对象，测试里也经常使用 dict。
        统一通过这个方法取字段，可以让转换逻辑不用关心具体返回类型。
        """
        if isinstance(value, dict):
            return value.get(key, default)
        return getattr(value, key, default)
