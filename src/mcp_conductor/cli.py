from __future__ import annotations

import argparse

from . import __version__
from .observability.logging import configure_logging
from .runtime import GatewayRuntime
from .server import create_server

"""
✅ 为什么不冲突：
--version 是一个查询命令，不是配置参数
一旦设置，表示用户只想看版本，不需要其他功能
通过 return 0 提前退出，避免执行后续代码
✅ 设计合理性：
优先级明确：版本查询 > 正常启动
符合用户预期：--version 应该快速返回
简单清晰：不需要复杂的互斥逻辑
❌ 不会有问题：
正常使用中，用户不会同时需要 --version 和其他参数
即使同时传了，也不会报错，只是忽略其他参数
"""


def build_parser() -> argparse.ArgumentParser:
    """
    这段代码定义了一个命令行参数解析器构建函数，用于配置 mcp-conductor MCP 网关服务器的启动参数。
    主要功能：
    创建 argparse 解析器，设置程序名和描述
    添加4个参数：--config（配置文件路径）、--log-level（日志级别，默认INFO）、--transport（传输方式，默认stdio）、--version（版本标志）
    返回配置好的解析器对象
    :return:
    """
    parser = argparse.ArgumentParser(
        prog="mcp-conductor",
        description="启动 mcp-conductor MCP 网关服务。",
        add_help=False,
    )
    parser._optionals.title = "选项"
    parser.add_argument(
        "-h",
        "--help",
        action="help",
        help="显示帮助信息并退出。",
    )
    parser.add_argument(
        "--config",
        help="内部上游 MCP 配置文件路径。",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Python 日志级别。",
    )
    parser.add_argument(
        "--transport",
        default="stdio",
        help="FastMCP 传输方式，默认使用适合 MCP Host 的 stdio。",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="打印包版本并退出。",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """
    这是 CLI 的主入口函数，负责解析命令行参数并启动服务器。
    主要流程：
    解析参数，若指定 --version 则打印版本号并退出
    配置日志级别
    创建网关运行时和服务器实例
    启动服务器（默认 stdio 传输）
    返回 0 表示成功
    :param argv:
    :return:
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"mcp-conductor {__version__}")
        return 0

    configure_logging(args.log_level)
    runtime = GatewayRuntime(config_path=args.config)
    server = create_server(runtime)
    server.run(transport=args.transport)
    return 0
