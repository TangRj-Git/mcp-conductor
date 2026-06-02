from __future__ import annotations

from mcp_conductor.cli import resolve_config_path


def test_resolve_config_path_uses_explicit_config_path() -> None:
    assert resolve_config_path("custom.json") == "custom.json"


def test_resolve_config_path_uses_local_default_config(tmp_path, monkeypatch) -> None:
    (tmp_path / "mcp-conductor.config.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert resolve_config_path(None) == "mcp-conductor.config.json"


def test_resolve_config_path_returns_none_without_local_default(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert resolve_config_path(None) is None
