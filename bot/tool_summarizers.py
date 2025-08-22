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
        out["items"] = _summarize_items_list(items, ["title", "year", "rating", "ratingKey", "type"], max_items)
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
        out["collections"] = _summarize_items_list(cols, ["title", "collection_id", "count"], max_items)
        if "total_found" in result:
            out["total_found"] = result.get("total_found")
        return out

    if name in {"get_plex_playlists"}:
        pls = result.get("playlists") or []
        out["playlists"] = _summarize_items_list(pls, ["title", "playlist_id", "count"], max_items)
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
            out["results"] = _summarize_items_list(results, ["id", "title", "overview", "vote_average", "release_date", "media_type", "poster_path"], max_items)
            return out
        # Details shape
        fields = ["id", "title", "overview", "vote_average", "release_date", "genres", "runtime", "poster_path"]
        out = _keep_fields(result, fields)
        return out

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


