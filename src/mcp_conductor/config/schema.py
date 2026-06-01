from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class TransportType(StrEnum):
    """
    MCP 服务器的传输协议类型。

    定义上游 MCP 服务器与网关之间的通信方式。

    枚举值：
        STDIO: 标准输入输出传输，适用于本地进程启动的 MCP 服务器
               （如通过 npx、python 等命令启动的子进程）

        STREAMABLE_HTTP: HTTP 流式传输，适用于远程或独立的 MCP 服务器
                        （通过 HTTP/SSE 协议通信）

    使用示例：
        transport = TransportType.STDIO
        print(transport.value)  # "stdio"
    """
    STDIO = "stdio"
    STREAMABLE_HTTP = "streamable_http"


class RiskPolicy(StrEnum):
    """
    上游服务器的风险管控策略。

    定义网关对上游工具执行的风险控制级别，确保操作安全性。

    枚举值：
        READ_ONLY_ONLY: 仅允许只读操作
                       - 允许：查询、读取类工具
                       - 禁止：修改、删除、创建类工具
                       - 适用场景：不可信的上游服务器

        CONFIRM_MUTATIONS: 允许写操作但需要用户确认
                          - 只读操作：直接执行
                          - 写操作：返回 confirmation_required，等待用户确认
                          - 适用场景：可信但需要审计的上游服务器

        DISABLED: 完全禁用该服务器
                 - 所有操作都被拒绝
                 - 不会在推荐中出现
                 - 适用场景：临时禁用或测试中的服务器

    使用示例：
        # 配置文件中：
        {
          "risk_policy": "confirm_mutations"  # 写操作需要确认
        }

        # 代码中：
        if server_config.risk_policy == RiskPolicy.CONFIRM_MUTATIONS:
            # 检查是否需要用户确认
            pass
    """
    READ_ONLY_ONLY = "read_only_only"
    CONFIRM_MUTATIONS = "confirm_mutations"
    DISABLED = "disabled"


class RootsPolicy(StrEnum):
    """
    文件系统根目录访问策略。

    定义对文件路径类参数的安全限制策略，防止任意文件访问。

    枚举值：
        HOST_ROOTS_OR_CONFIG_ALLOWLIST: 主机根目录或配置白名单
                                       - 允许 Host 提供的根目录
                                       - 或 allowed_roots 中配置的目录
                                       - 较宽松的策略

        CONFIG_ALLOWLIST_ONLY: 仅允许配置白名单中的目录
                              - 只允许 allowed_roots 中明确列出的目录
                              - 更严格的安全策略
                              - 推荐用于生产环境

    使用示例：
        # 配置文件中：
        {
          "roots_policy": "config_allowlist_only",
          "allowed_roots": ["/workspace", "/tmp"]
        }

        # 效果：只能访问 /workspace 和 /tmp 及其子目录
    """
    HOST_ROOTS_OR_CONFIG_ALLOWLIST = "host_roots_or_config_allowlist"
    CONFIG_ALLOWLIST_ONLY = "config_allowlist_only"


@dataclass(slots=True)
class UpstreamServerConfig:
    """
    单个上游 MCP 服务器的完整配置。

    包含启动、连接和管理上游 MCP 服务器所需的所有配置信息。
    使用 slots=True 优化内存使用和性能。

    字段说明：
        server_id: 服务器唯一标识符，如 "github"、"filesystem"
                   用于在日志、错误信息和路由中标识服务器

        transport: 传输协议类型，默认 STDIO
                   决定如何与上游服务器通信

        command: 启动命令（仅 stdio 传输需要）
                 如 "npx"、"python"、"node"
                 None 表示使用 URL 连接（HTTP 传输）

        args: 命令行参数列表，默认空列表
              如 ["-y", "@modelcontextprotocol/server-github"]
              与 command 组合成完整命令

        url: 服务器 URL（仅 HTTP 传输需要）
             如 "http://localhost:8080/mcp"
             stdio 传输时通常为 None

        cwd: 工作目录，默认当前目录
             启动命令时切换到此目录
             影响相对路径解析

        env: 环境变量字典，默认空字典
             启动时注入到子进程环境
             支持 ${VAR_NAME} 格式的环境变量引用

        disabled: 是否禁用此服务器，默认 False
                  True 时启动时被跳过，不会出现在推荐中
                  用于临时禁用而不删除配置

        risk_policy: 风险管控策略，默认 READ_ONLY_ONLY
                     决定哪些类型的操作被允许
                     见 RiskPolicy 枚举说明

        roots_policy: 根目录访问策略，可选
                      决定如何验证文件路径参数
                      见 RootsPolicy 枚举说明

        allowed_roots: 允许访问的路径白名单，默认空列表
                       如 ["/workspace", "/home/user/projects"]
                       配合 roots_policy 使用，限制文件访问范围

    使用示例：
        # 示例 1：stdio 类型的 GitHub MCP 服务器
        github_config = UpstreamServerConfig(
            server_id="github",
            transport=TransportType.STDIO,
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            env={"GITHUB_TOKEN": "${GITHUB_TOKEN}"},
            risk_policy=RiskPolicy.READ_ONLY_ONLY
        )

        # 示例 2：HTTP 类型的远程服务器
        remote_config = UpstreamServerConfig(
            server_id="remote-mcp",
            transport=TransportType.STREAMABLE_HTTP,
            url="http://mcp-server.example.com/sse",
            risk_policy=RiskPolicy.CONFIRM_MUTATIONS
        )

        # 示例 3：带路径限制的 filesystem 服务器
        fs_config = UpstreamServerConfig(
            server_id="filesystem",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "./data"],
            risk_policy=RiskPolicy.CONFIRM_MUTATIONS,
            roots_policy=RootsPolicy.CONFIG_ALLOWLIST_ONLY,
            allowed_roots=["/workspace", "/tmp"]
        )

        # 示例 4：禁用的服务器（保留配置但不启用）
        disabled_config = UpstreamServerConfig(
            server_id="experimental",
            command="python",
            args=["server.py"],
            disabled=True  # 启动时会被跳过
        )
    """
    server_id: str
    transport: TransportType = TransportType.STDIO
    command: str | None = None
    args: list[str] = field(default_factory=list)
    url: str | None = None
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    disabled: bool = False
    risk_policy: RiskPolicy = RiskPolicy.READ_ONLY_ONLY
    roots_policy: RootsPolicy | None = None
    allowed_roots: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GatewayConfig:
    """
    MCP 网关的全局配置。

    包含所有上游服务器的配置集合，是配置系统的顶层对象。
    使用 slots=True 优化内存使用和性能。

    字段说明：
        upstream_servers: 上游服务器配置字典
                         键为 server_id，值为 UpstreamServerConfig 对象
                         空字典表示没有配置任何上游服务器

    使用示例：
        # 示例 1：创建空配置
        empty_config = GatewayConfig()
        # upstream_servers = {}

        # 示例 2：创建包含多个服务器的配置
        config = GatewayConfig(
            upstream_servers={
                "github": UpstreamServerConfig(
                    server_id="github",
                    command="npx",
                    args=["-y", "@modelcontextprotocol/server-github"]
                ),
                "filesystem": UpstreamServerConfig(
                    server_id="filesystem",
                    command="npx",
                    args=["-y", "@modelcontextprotocol/server-filesystem"]
                )
            }
        )

        # 示例 3：访问配置
        github_config = config.upstream_servers["github"]
        print(github_config.command)  # "npx"

        # 示例 4：遍历所有服务器
        for server_id, server_config in config.upstream_servers.items():
            if not server_config.disabled:
                print(f"启用服务器: {server_id}")

        # 示例 5：从 JSON 配置文件加载
        # mcp-conductor.config.json:
        # {
        #   "mcpServers": {
        #     "github": {...},
        #     "filesystem": {...}
        #   }
        # }
        #
        # 通过 load_config() 函数解析为 GatewayConfig 对象
    """
    upstream_servers: dict[str, UpstreamServerConfig] = field(default_factory=dict)
