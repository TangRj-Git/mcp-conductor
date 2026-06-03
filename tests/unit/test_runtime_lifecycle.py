from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

from mcp_conductor.config.schema import GatewayConfig, RiskPolicy, UpstreamServerConfig
from mcp_conductor.models import Recommendation, RiskLevel
from mcp_conductor.runtime import GatewayRuntime
from mcp_conductor.upstream.manager import UpstreamClientManager


def test_runtime_startup_loads_config_and_starts_enabled_upstream_clients(tmp_path) -> None:
    config_path = tmp_path / "mcp-conductor.config.json"
    config_path.write_text(
        json.dumps(
            {
                "upstreamServers": {
                    "github": {
                        "transport": "stdio",
                        "command": "npx",
                        "args": ["-y", "github-server"],
                    },
                    "disabled-filesystem": {
                        "transport": "stdio",
                        "command": "npx",
                        "args": ["-y", "filesystem-server"],
                        "disabled": True,
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    runtime = GatewayRuntime(config_path=str(config_path))

    runtime.startup()

    assert "github" in runtime.upstream_manager.clients
    assert "disabled-filesystem" not in runtime.upstream_manager.clients

    runtime.shutdown()

    assert runtime.upstream_manager.clients == {}


def test_upstream_client_manager_skips_risk_policy_disabled_servers() -> None:
    manager = UpstreamClientManager(
        GatewayConfig(
            upstream_servers={
                "github": UpstreamServerConfig(server_id="github"),
                "disabled-risk": UpstreamServerConfig(
                    server_id="disabled-risk",
                    risk_policy=RiskPolicy.DISABLED,
                ),
            }
        )
    )

    manager.startup()

    assert "github" in manager.clients
    assert "disabled-risk" not in manager.clients


def test_upstream_client_manager_startup_rebuilds_client_map() -> None:
    manager = UpstreamClientManager(
        GatewayConfig(
            upstream_servers={
                "github": UpstreamServerConfig(server_id="github"),
            }
        )
    )
    manager.startup()

    manager.config = GatewayConfig(upstream_servers={})
    manager.startup()

    assert manager.clients == {}


def test_runtime_startup_rebinds_default_execution_engine() -> None:
    class FakeManager:
        def __init__(self, config: GatewayConfig) -> None:
            self.config = config
            self.clients = {}

        def startup(self) -> None:
            pass

    managers: list[FakeManager] = []

    def manager_factory(config: GatewayConfig) -> FakeManager:
        manager = FakeManager(config)
        managers.append(manager)
        return manager

    runtime = GatewayRuntime(upstream_manager_factory=manager_factory)

    runtime.startup()
    runtime.startup()

    assert runtime.tool_executor.upstream_manager is managers[-1]


def test_runtime_startup_clears_volatile_session_state() -> None:
    class FakeManager:
        def __init__(self, config: GatewayConfig) -> None:
            self.config = config
            self.clients = {}

        def startup(self) -> None:
            pass

    runtime = GatewayRuntime(upstream_manager_factory=FakeManager)
    routing_session = runtime.start_routing_session(user_task="Check docs")
    runtime.recommendations["rec_old"] = Recommendation(
        recommendation_id="rec_old",
        expires_at=datetime.now(UTC) + timedelta(seconds=300),
        recommended_capabilities=[],
    )
    pending = runtime.pending_actions.create(
        capability_id="filesystem.tools.delete_file",
        arguments={"path": "demo.txt"},
        risk_level=RiskLevel.DESTRUCTIVE,
    )
    assert runtime.result_manager is not None
    result_id = runtime.result_manager.cache.put({"secret": "value"})

    runtime.startup()

    assert runtime.list_routing_session_state(
        session_id=routing_session["session_id"],
    )["error_code"] == "invalid_routing_session"
    assert runtime.recommendations == {}
    assert runtime.pending_actions.get(pending.pending_action_id) is None
    assert runtime.result_manager.cache.get(result_id) is None


def test_runtime_startup_discovers_upstream_capabilities(tmp_path) -> None:
    config_path = tmp_path / "mcp-conductor.config.json"
    config_path.write_text(
        json.dumps({"upstreamServers": {"github": {"transport": "stdio"}}}),
        encoding="utf-8",
    )

    class FakeClient:
        def list_tools(self):
            return [
                {
                    "name": "get_pr_checks",
                    "description": "Read PR CI checks",
                    "input_schema": {"type": "object"},
                }
            ]

    class FakeManager:
        def __init__(self, config: GatewayConfig) -> None:
            self.config = config
            self.clients = {}

        def startup(self) -> None:
            self.clients = {"github": FakeClient()}

    runtime = GatewayRuntime(
        config_path=str(config_path),
        upstream_manager_factory=FakeManager,
    )

    runtime.startup()

    assert runtime.registry.get("github.tools.get_pr_checks").description == (
        "Read PR CI checks"
    )
    assert runtime.discovery_errors == []


def test_runtime_async_startup_rebinds_default_execution_engine() -> None:
    class FakeManager:
        def __init__(self, config: GatewayConfig) -> None:
            self.config = config
            self.clients = {}

        async def astartup(self) -> None:
            pass

        async def ashutdown(self) -> None:
            pass

    managers: list[FakeManager] = []

    def manager_factory(config: GatewayConfig) -> FakeManager:
        manager = FakeManager(config)
        managers.append(manager)
        return manager

    async def run() -> None:
        runtime = GatewayRuntime(upstream_manager_factory=manager_factory)

        await runtime.async_startup()
        await runtime.async_startup()

        assert runtime.tool_executor.upstream_manager is managers[-1]

    asyncio.run(run())


def test_upstream_client_manager_async_lifecycle_connects_and_closes_clients() -> None:
    created_clients = []

    class FakeClient:
        def __init__(self, config: UpstreamServerConfig) -> None:
            self.server_id = config.server_id
            self.connected = False
            self.closed = False
            created_clients.append(self)

        async def connect(self) -> None:
            self.connected = True

        async def shutdown(self) -> None:
            self.closed = True

    async def run() -> None:
        manager = UpstreamClientManager(
            GatewayConfig(
                upstream_servers={
                    "github": UpstreamServerConfig(server_id="github"),
                    "disabled-filesystem": UpstreamServerConfig(
                        server_id="disabled-filesystem",
                        disabled=True,
                    ),
                }
            ),
            client_factory=FakeClient,
        )

        await manager.astartup()

        assert list(manager.clients) == ["github"]
        assert manager.clients["github"].connected is True

        await manager.ashutdown()

        assert manager.clients == {}
        assert created_clients[0].closed is True

    asyncio.run(run())


def test_upstream_client_manager_keeps_running_when_one_client_fails() -> None:
    class FakeClient:
        def __init__(self, config: UpstreamServerConfig) -> None:
            self.server_id = config.server_id
            self.connected = False
            self.closed = False

        async def connect(self) -> None:
            if self.server_id == "broken":
                raise RuntimeError("boom")
            self.connected = True

        async def shutdown(self) -> None:
            self.closed = True

    async def run() -> None:
        manager = UpstreamClientManager(
            GatewayConfig(
                upstream_servers={
                    "github": UpstreamServerConfig(server_id="github"),
                    "broken": UpstreamServerConfig(server_id="broken"),
                }
            ),
            client_factory=FakeClient,
        )

        await manager.astartup()

        assert list(manager.clients) == ["github"]
        assert manager.clients["github"].connected is True
        assert "broken" in manager.startup_errors
        assert "boom" in manager.startup_errors["broken"]

        await manager.ashutdown()

        assert manager.clients == {}

    asyncio.run(run())


def test_upstream_client_manager_closes_remaining_clients_when_shutdown_fails() -> None:
    created_clients = {}

    class FakeClient:
        def __init__(self, config: UpstreamServerConfig) -> None:
            self.server_id = config.server_id
            self.closed = False
            created_clients[self.server_id] = self

        async def shutdown(self) -> None:
            self.closed = True
            if self.server_id == "broken":
                raise RuntimeError("close failed")

    async def run() -> None:
        manager = UpstreamClientManager(
            GatewayConfig(
                upstream_servers={
                    "broken": UpstreamServerConfig(server_id="broken"),
                    "github": UpstreamServerConfig(server_id="github"),
                }
            ),
            client_factory=FakeClient,
        )
        manager.startup()

        await manager.ashutdown()

        assert created_clients["broken"].closed is True
        assert created_clients["github"].closed is True
        assert manager.clients == {}
        assert manager.shutdown_errors == {"broken": "close failed"}

    asyncio.run(run())


def test_runtime_async_startup_discovers_upstream_capabilities(tmp_path) -> None:
    config_path = tmp_path / "mcp-conductor.config.json"
    config_path.write_text(
        json.dumps({"upstreamServers": {"github": {"transport": "stdio"}}}),
        encoding="utf-8",
    )

    class FakeClient:
        async def list_tools_async(self):
            return [
                {
                    "name": "get_pr_checks",
                    "description": "Read PR CI checks",
                    "input_schema": {"type": "object"},
                }
            ]

    class FakeManager:
        def __init__(self, config: GatewayConfig) -> None:
            self.config = config
            self.clients = {"github": FakeClient()}
            self.started = False
            self.stopped = False

        async def astartup(self) -> None:
            self.started = True

        async def ashutdown(self) -> None:
            self.stopped = True
            self.clients = {}

    managers: list[FakeManager] = []

    def manager_factory(config: GatewayConfig) -> FakeManager:
        manager = FakeManager(config)
        managers.append(manager)
        return manager

    async def run() -> None:
        runtime = GatewayRuntime(
            config_path=str(config_path),
            upstream_manager_factory=manager_factory,
        )

        await runtime.async_startup()

        active_manager = managers[-1]
        assert active_manager.started is True
        assert runtime.registry.get("github.tools.get_pr_checks").description == (
            "Read PR CI checks"
        )
        assert runtime.discovery_errors == []

        await runtime.async_shutdown()

        assert active_manager.stopped is True

    asyncio.run(run())
