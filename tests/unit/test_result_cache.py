from __future__ import annotations

from mcp_conductor.results.cache import ResultCache


def test_result_cache_isolates_values_by_session() -> None:
    cache = ResultCache()
    result_id = cache.put({"secret": "value"}, session_id="session-a")

    assert cache.get(result_id, session_id="session-a") == {"secret": "value"}
    assert cache.get(result_id, session_id="session-b") is None
