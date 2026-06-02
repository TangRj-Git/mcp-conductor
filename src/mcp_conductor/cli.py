from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .observability.logging import configure_logging
from .runtime import GatewayRuntime
from .server import create_server

DEFAULT_CONFIG_FILE = "mcp-conductor.config.json"


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for the gateway process."""
    parser = argparse.ArgumentParser(
        prog="mcp-conductor",
        description="Start the mcp-conductor MCP gateway server.",
        add_help=False,
    )
    parser._optionals.title = "options"
    parser.add_argument(
        "-h",
        "--help",
        action="help",
        help="Show this help message and exit.",
    )
    parser.add_argument(
        "--config",
        help="Path to the internal upstream MCP configuration file.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Python logging level.",
    )
    parser.add_argument(
        "--transport",
        default="stdio",
        help="FastMCP transport to serve; stdio is the default for MCP hosts.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print package version and exit.",
    )
    return parser


def resolve_config_path(config_path: str | None) -> str | None:
    """Use the explicit config path or a local default config file when present."""
    if config_path:
        return config_path
    if Path(DEFAULT_CONFIG_FILE).exists():
        return DEFAULT_CONFIG_FILE
    return None


def main(argv: list[str] | None = None) -> int:
    """Parse CLI options, construct the runtime, and start the MCP server."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Version queries should return before creating any runtime state or upstream process.
    if args.version:
        print(f"mcp-conductor {__version__}")
        return 0

    configure_logging(args.log_level)
    runtime = GatewayRuntime(config_path=resolve_config_path(args.config))
    server = create_server(runtime)
    server.run(transport=args.transport)
    return 0
