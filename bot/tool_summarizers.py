from __future__ import annotations

from typing import Any, Dict, List


def _truncate_list(items: List[Any], max_items: int) -> List[Any]:
    if not isinstance(items, list):
        return items  # type: ignore[return-value]
    if max_items <= 0 or len(items) <= max_items:
        return items
    return items[:max_items]


def _keep_fields(obj: Dict[str, Any], fields: List[str]) -> Dict[str, Any]:
    return {k: obj.get(k) for k in fields if k in obj}


def _summarize_items_list(items: List[Dict[str, Any]], fields: List[str], max_items: int) -> List[Dict[str, Any]]:
    items = _truncate_list(items, max_items)
    summarized: List[Dict[str, Any]] = []
    for it in items:
        if isinstance(it, dict):
            summarized.append(_keep_fields(it, fields))
    return summarized


def summarize_tool_result(name: str, result: Dict[str, Any], *, max_items: int = 5) -> Dict[str, Any]:
    """
    Deterministic, schema-light summarization to reduce tokens while preserving utility.
    Keeps top-N items and essential fields per tool family.
    """
    if not isinstance(result, dict):
        return {"value": result}

    out: Dict[str, Any] = {}

    # Plex families
    if name in {
        "search_plex", "get_plex_recently_added", "get_plex_on_deck", "get_plex_continue_watching",
        "get_plex_unwatched", "get_plex_similar_items", "get_plex_movies_4k_or_hdr"
    }:
        items = result.get("items") or []
        resp_level = str(result.get("response_level", "compact")).lower()
        if resp_level == "minimal":
            fields = ["title", "ratingKey", "type"]
            out["items"] = _summarize_items_list(items, fields, max_items)
        elif resp_level == "compact":
            fields = ["title", "year", "rating", "ratingKey", "type"]
            out["items"] = _summarize_items_list(items, fields, max_items)
        elif resp_level == "standard":
            fields = ["title", "year", "rating", "contentRating", "duration", "genres", "summary", "ratingKey", "type"]
            out["items"] = _summarize_items_list(items, fields, max_items)
        else:  # detailed: keep all fields, only truncate count
            out["items"] = _truncate_list(items, max_items)
        if "total_found" in result:
            out["total_found"] = result.get("total_found")
        if name == "get_plex_movies_4k_or_hdr":
            # Keep useful debugging info minimal
            attempts = result.get("attempts") or []
            out["attempts"] = _truncate_list(attempts, 3)
        if "section_type" in result:
            out["section_type"] = result.get("section_type")
        return out

    if name in {"get_plex_collections"}:
        cols = result.get("collections") or []
        resp_level = str(result.get("response_level", "compact")).lower()
        fields = ["title", "collection_id", "count"]
        if resp_level in ("standard", "detailed"):
            fields = ["title", "collection_id", "count", "summary"]
        out["collections"] = _summarize_items_list(cols, fields, max_items)
        if "total_found" in result:
            out["total_found"] = result.get("total_found")
        return out

    if name in {"get_plex_playlists"}:
        pls = result.get("playlists") or []
        resp_level = str(result.get("response_level", "compact")).lower()
        fields = ["title", "playlist_id", "count"]
        if resp_level in ("standard", "detailed"):
            fields = ["title", "playlist_id", "count", "summary", "duration"]
        out["playlists"] = _summarize_items_list(pls, fields, max_items)
        if "total_found" in result:
            out["total_found"] = result.get("total_found")
        return out

    if name in {"get_plex_item_details"}:
        item = result.get("item") or {}
        if isinstance(item, dict):
            out["item"] = _keep_fields(item, ["title", "year", "ratingKey", "type", "rating", "genres", "summary"])
        return out

    # TMDb families
    if name.startswith("tmdb_"):
        # Common paged list shape
        if "results" in result:
            out["page"] = result.get("page")
            out["total_pages"] = result.get("total_pages")
            out["total_results"] = result.get("total_results")
            results = result.get("results") or []
            # Preserve whatever fields TMDb client produced for each item; only truncate count
            out["results"] = _truncate_list(results, max_items)
            return out
        # Details shape: return as-is to respect chosen response level
        return result

    # Sonarr/Radarr common patterns
    if name in {"radarr_get_movies"}:
        movies = result.get("movies") or []
        out["movies"] = _summarize_items_list(movies, ["id", "title", "tmdbId", "year", "hasFile"], max_items)
        return out

    if name in {"sonarr_get_series"}:
        series = result.get("series") or []
        out["series"] = _summarize_items_list(series, ["id", "title", "tvdbId", "status", "monitored"], max_items)
        return out

    if name in {"sonarr_get_episodes"}:
        eps = result.get("episodes") or []
        out["episodes"] = _summarize_items_list(eps, ["id", "seasonNumber", "episodeNumber", "hasFile", "airDateUtc"], max_items)
        return out

    # Preferences compact
    if name in {"read_household_preferences"}:
        if "compact" in result:
            out["compact"] = result.get("compact")
            return out
        # fall-through minimal projection for safety
        keys = [k for k in ("likes", "dislikes", "constraints", "anchors") if k in result]
        for k in keys:
            out[k] = result.get(k)
        return out

    # Default: if a top-level list exists, cap it; otherwise return as-is
    for k, v in result.items():
        if isinstance(v, list):
            out[k] = _truncate_list(v, max_items)
        else:
            out[k] = v
    return out


