from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from integrations.ttl_cache import shared_cache


def put_tool_result(value: Any, ttl_sec: int) -> str:
    """Store a raw tool result and return a reference id."""
    ref_id = uuid.uuid4().hex
    shared_cache.set(ref_id, value, ttl_sec)
    return ref_id


def _project_fields(obj: Any, fields: Optional[List[str]]) -> Any:
    if not fields or not isinstance(obj, dict):
        return obj
    return {k: obj.get(k) for k in fields if k in obj}


def _slice_list(value: Any, start: Optional[int], count: Optional[int]) -> Any:
    if not isinstance(value, list):
        return value
    s = max(start or 0, 0)
    if count is None or count < 0:
        return value[s:]
    return value[s : s + count]


def fetch_cached_result(ref_id: str, *, fields: Optional[List[str]] = None, start: Optional[int] = None, count: Optional[int] = None) -> Dict[str, Any]:
    """Fetch a cached result by reference id with optional projection/slicing."""
    value = shared_cache.get(ref_id)
    if value is None:
        return {"ok": False, "error": "not_found", "ref_id": ref_id}

    projected = _project_fields(value, fields)
    # If the projected value is a dict with a single top-level list, allow slicing it
    if isinstance(projected, dict) and len(projected) == 1:
        k = next(iter(projected))
        projected[k] = _slice_list(projected[k], start, count)
    elif isinstance(projected, list):
        projected = _slice_list(projected, start, count)

    return {"ok": True, "ref_id": ref_id, "value": projected}


def make_fetch_cached_result(_project_root):
    async def impl(args: dict) -> dict:
        ref_id = str(args.get("ref_id", "")).strip()
        if not ref_id:
            return {"ok": False, "error": "ref_id_required"}
        fields = args.get("fields")
        start = args.get("start")
        count = args.get("count")
        return fetch_cached_result(ref_id, fields=fields, start=start, count=count)

    return impl


