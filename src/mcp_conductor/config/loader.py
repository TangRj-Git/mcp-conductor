from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .env import resolve_env_mapping
from .schema import (
    GatewayConfig,
    RiskPolicy,
    RootsPolicy,
    TransportType,
    UpstreamServerConfig,
)


def load_config(path: str | Path | None) -> GatewayConfig:
    """
    从 JSON 文件加载 MCP 网关配置。

    这是配置系统的入口函数，负责读取配置文件并解析为 GatewayConfig 对象。
    如果未提供路径，则返回空配置（使用默认值）。配置文件必须是有效的 JSON
    格式，支持 UTF-8 编码。

    参数说明：
        path: 配置文件路径（字符串或 Path 对象），None 表示使用默认空配置

    返回值：
        GatewayConfig 对象，包含所有上游服务器配置和网关设置

    异常：
        FileNotFoundError: 当配置文件不存在时
        json.JSONDecodeError: 当 JSON 格式无效时
        ValueError: 当配置中的环境变量引用缺失时

    使用场景：
        # 场景1：加载指定配置文件
        config = load_config("./mcp-conductor.config.json")

        # 场景2：使用默认空配置
        config = load_config(None)
        # 返回：GatewayConfig(upstream_servers={})

        # 场景3：在 GatewayRuntime 中使用
        runtime = GatewayRuntime(config_path="./config.json")
        runtime.startup()  # 内部会调用 load_config

        # 场景4：处理文件不存在的情况
        try:
            config = load_config("./nonexistent.json")
        except FileNotFoundError:
            print("配置文件不存在，使用默认配置")
            config = load_config(None)

    :param path: 配置文件路径，None 表示使用默认配置
    :return: 解析后的网关配置对象
    """
    if path is None:
        return GatewayConfig()

    config_path = Path(path)
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return parse_config(data)


def parse_config(data: dict[str, Any]) -> GatewayConfig:
    """
    将原始字典数据解析为 GatewayConfig 对象。

    此函数处理配置的合并逻辑，支持两种键名格式：
    - "mcpServers"（标准 MCP 格式）
    - "upstreamServers"（项目自定义格式）

    两者会被合并，upstreamServers 的优先级更高（如果有重复）。

    参数说明：
        data: 从 JSON 文件读取的原始字典数据

    返回值：
        GatewayConfig 对象，包含解析后的所有上游服务器配置

    使用场景：
        # 场景1：解析 mcpServers 格式（标准）
        data = {
            "mcpServers": {
                "github": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-github"]
                }
            }
        }
        config = parse_config(data)

        # 场景2：解析 upstreamServers 格式（自定义）
        data = {
            "upstreamServers": {
                "filesystem": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem"]
                }
            }
        }
        config = parse_config(data)

        # 场景3：混合格式（两者都会合并）
        data = {
            "mcpServers": {
                "github": {...}
            },
            "upstreamServers": {
                "filesystem": {...}
            }
        }
        config = parse_config(data)
        # 结果：config.upstream_servers 包含 github 和 filesystem

        # 场景4：空配置
        config = parse_config({})
        # 返回：GatewayConfig(upstream_servers={})

    :param data: 原始配置字典
    :return: 解析后的网关配置对象
    """
    upstream = {}
    # 合并两种格式的服务器配置，upstreamServers 优先级更高
    raw_servers = {
        **data.get("mcpServers", {}),
        **data.get("upstreamServers", {}),
    }
    for server_id, raw in raw_servers.items():
        upstream[server_id] = parse_upstream_server(server_id, raw)
    return GatewayConfig(upstream_servers=upstream)


def parse_upstream_server(
        server_id: str,
        raw: dict[str, Any],
) -> UpstreamServerConfig:
    """
    解析单个上游服务器的配置数据。

    将原始字典转换为 UpstreamServerConfig 对象，处理所有字段的类型转换、
    默认值设置和环境变量解析。这是配置解析的核心函数，确保每个上游服务
    器的配置都是完整且类型正确的。

    参数说明：
        server_id: 服务器唯一标识符，如 "github"、"filesystem"
        raw: 原始配置字典，包含以下字段：
            - transport: 传输类型（"stdio" 或 "sse"），默认 "stdio"
            - command: 启动命令（如 "npx"、"python"）
            - args: 命令行参数列表
            - url: SSE 传输时的 URL 地址
            - cwd: 工作目录
            - env: 环境变量字典，支持 ${VAR} 格式
            - disabled: 是否禁用该服务器，默认 False
            - risk_policy: 风险策略（"read_only_only"、"confirm_mutations"、"disabled"）
            - roots_policy: 根目录策略
            - allowed_roots: 允许访问的路径白名单

    返回值：
        UpstreamServerConfig 对象，包含完整的服务器配置

    异常：
        ValueError: 当环境变量引用缺失或枚举值无效时

    使用场景：
        # 场景1：解析 stdio 类型的服务器
        raw = {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {
                "GITHUB_TOKEN": "${GITHUB_TOKEN}"
            }
        }
        config = parse_upstream_server("github", raw)
        # env 中的 ${GITHUB_TOKEN} 会被解析为实际值

        # 场景2：解析带风险策略的服务器
        raw = {
            "command": "npx",
            "risk_policy": "confirm_mutations",  # 允许写操作但需确认
            "allowed_roots": ["/home/user/projects"]
        }
        config = parse_upstream_server("filesystem", raw)

        # 场景3：解析禁用的服务器
        raw = {
            "command": "npx",
            "disabled": True  # 启动时会被跳过
        }
        config = parse_upstream_server("disabled-server", raw)

        # 场景4：最小配置（使用默认值）
        raw = {}
        config = parse_upstream_server("minimal", raw)
        # 返回：transport="stdio", risk_policy="read_only_only",
        #       disabled=False, env={}, args=[]

        # 场景5：带根目录策略的配置
        raw = {
            "command": "npx",
            "roots_policy": "strict",
            "allowed_roots": ["/workspace", "/tmp"]
        }
        config = parse_upstream_server("secure-server", raw)

    :param server_id: 服务器唯一标识
    :param raw: 原始配置字典
    :return: 解析后的上游服务器配置对象
    """
    roots_policy = raw.get("roots_policy")
    return UpstreamServerConfig(
        server_id=server_id,
        # 传输类型：默认为 stdio
        transport=TransportType(raw.get("transport", TransportType.STDIO)),
        # 命令和参数
        command=raw.get("command"),
        args=list(raw.get("args", [])),
        # SSE 传输的 URL
        url=raw.get("url"),
        # 工作目录
        cwd=raw.get("cwd"),
        # 环境变量（解析 ${VAR} 引用）
        env=resolve_env_mapping(dict(raw.get("env", {}))),
        # 是否禁用
        disabled=bool(raw.get("disabled", False)),
        # 风险策略：默认只允许只读操作
        risk_policy=RiskPolicy(raw.get("risk_policy", RiskPolicy.READ_ONLY_ONLY)),
        # 根目录策略（可选）
        roots_policy=RootsPolicy(roots_policy) if roots_policy else None,
        # 允许访问的路径白名单
        allowed_roots=list(raw.get("allowed_roots", [])),
    )
