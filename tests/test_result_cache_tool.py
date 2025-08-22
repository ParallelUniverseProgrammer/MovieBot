import asyncio
import pytest

from bot.tools.result_cache import put_tool_result, fetch_cached_result


def test_cache_roundtrip_and_projection():
    ref = put_tool_result({"items": [1, 2, 3, 4], "meta": {"a": 1}}, ttl_sec=60)
    out = fetch_cached_result(ref, fields=["items"], start=1, count=2)
    assert out["ok"] is True
    assert out["value"] == {"items": [2, 3]}


def test_cache_miss_returns_error():
    out = fetch_cached_result("nope")
    assert out["ok"] is False and out["error"] == "not_found"
