from __future__ import annotations

from datetime import UTC, datetime, timedelta

from mcp_conductor.results.cache import ResultCache
from mcp_conductor.results.manager import ResultManager


def test_result_cache_isolates_values_by_session() -> None:
    cache = ResultCache()
    result_id = cache.put({"secret": "value"}, session_id="session-a")

    assert cache.get(result_id, session_id="session-a") == {"secret": "value"}
    assert cache.get(result_id, session_id="session-b") is None


def test_result_cache_prunes_expired_values_when_writing() -> None:
    cache = ResultCache()
    result_id = cache.put({"old": True})
    cache.values[result_id].expires_at = datetime.now(UTC) - timedelta(seconds=1)

    cache.put({"new": True})

    assert result_id not in cache.values


def test_result_cache_evicts_oldest_values_when_max_entries_is_reached() -> None:
    cache = ResultCache(max_entries=2)
    first_id = cache.put({"index": 1})
    second_id = cache.put({"index": 2})
    third_id = cache.put({"index": 3})

    assert first_id not in cache.values
    assert second_id in cache.values
    assert third_id in cache.values


def test_result_cache_evicts_oldest_values_when_max_bytes_is_reached() -> None:
    cache = ResultCache(max_bytes=80)
    first_id = cache.put({"content": "x" * 60})
    second_id = cache.put({"content": "y" * 60})

    assert first_id not in cache.values
    assert second_id in cache.values


def test_result_manager_caches_large_non_list_results_with_session() -> None:
    manager = ResultManager(max_inline_bytes=100)

    result = manager.prepare_result({"content": "x" * 500}, session_id="session-a")

    assert result["status"] == "ok"
    assert result["truncated"] is True
    assert result["data"] is None
    assert isinstance(result["preview"], str)
    assert result["result_id"].startswith("result_")


def test_result_manager_caches_lists_that_exceed_inline_byte_limit_with_session() -> None:
    manager = ResultManager(max_inline_bytes=100)

    result = manager.prepare_result(["x" * 500], session_id="session-a")

    assert result["status"] == "ok"
    assert result["truncated"] is True
    assert result["data"] is None
    assert result["result_id"].startswith("result_")


def test_result_manager_does_not_cache_large_results_without_session() -> None:
    manager = ResultManager(max_inline_bytes=100)

    result = manager.prepare_result({"content": "x" * 500}, session_id=None)

    assert result["status"] == "ok"
    assert result["truncated"] is True
    assert result["data"] is None
    assert result["result_id"] is None
    assert result["cache_unavailable_reason"] == "session_id_unavailable"
