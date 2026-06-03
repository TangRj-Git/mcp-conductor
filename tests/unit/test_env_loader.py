from __future__ import annotations

import os

from mcp_conductor.config.env import load_env_file


def test_load_env_file_strips_utf8_bom_from_first_key(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\ufeffEXAMPLE_API_KEY=secret\nEXAMPLE_MODEL=demo-model\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("EXAMPLE_API_KEY", raising=False)
    monkeypatch.delenv("EXAMPLE_MODEL", raising=False)

    load_env_file(env_file)

    assert os.environ["EXAMPLE_API_KEY"] == "secret"
    assert os.environ["EXAMPLE_MODEL"] == "demo-model"
