from __future__ import annotations

import os
from pathlib import Path
import asyncio
from typing import Any

from dotenv import load_dotenv

from integrations.plex_client import PlexClient, ResponseLevel
from bot.tools.tool_impl import (
    make_get_plex_library_sections,
    make_get_plex_recently_added,
    make_get_plex_unwatched,
    make_get_plex_on_deck,
    make_search_plex,
    make_get_plex_item_details,
)
from config.loader import load_settings


def _print_section(title: str) -> None:
    print(f"\n=== {title} ===")


def _print_items(items: list[dict[str, Any]], limit: int = 10) -> None:
    for i, it in enumerate(items[:limit], start=1):
        title = it.get("title")
        year = it.get("year")
        rating = it.get("rating")
        rating_key = it.get("ratingKey")
        media_type = it.get("type")
        vres = it.get("videoResolution") or it.get("resolution")
        vcodec = it.get("videoCodec")
        acodec = it.get("audioCodec")
        bits = [str(title) if title is not None else "(no title)"]
        if year:
            bits.append(str(year))
        if rating is not None:
            bits.append(f"rating={rating}")
        if media_type:
            bits.append(f"type={media_type}")
        if rating_key is not None:
            bits.append(f"key={rating_key}")
        codecs_bits = []
        if vres:
            codecs_bits.append(str(vres))
        if vcodec:
            codecs_bits.append(str(vcodec))
        if acodec:
            codecs_bits.append(str(acodec))
        if codecs_bits:
            bits.append("/".join(codecs_bits))
        print(f"{i:02d}. " + " | ".join(bits))


def _print_likely_matches(items: list[dict[str, Any]], needle: str, *, limit: int = 10) -> None:
    """Highlight items whose title contains the given substring (case-insensitive)."""
    n = needle.lower().strip()
    if not n:
        return
    matches = [it for it in items if n in str(it.get("title") or "").lower()]
    if matches:
        print(f"\nLIKELY MATCHES for '{needle}':")
        _print_items(matches, limit=limit)


def _filter_items(
    items: list[dict[str, Any]],
    *,
    year_min: int | None = None,
    year_max: int | None = None,
    genres: list[str] | None = None,
    actors: list[str] | None = None,
    directors: list[str] | None = None,
    content_rating: str | None = None,
    rating_min: float | None = None,
    rating_max: float | None = None,
) -> list[dict[str, Any]]:
    def has_any_case_insensitive(needles: list[str], haystack: list[str]) -> bool:
        hs = {h.lower() for h in haystack}
        return any(n.lower() in hs for n in needles)

    out: list[dict[str, Any]] = []
    for m in items:
        y = int(m.get("year") or 0)
        if year_min is not None and y < year_min:
            continue
        if year_max is not None and y > year_max:
            continue

        if genres:
            g = [str(x) for x in (m.get("genres") or [])]
            if not has_any_case_insensitive(genres, g):
                continue

        if actors:
            a = [str(x) for x in (m.get("actors") or [])]
            if not has_any_case_insensitive(actors, a):
                continue

        if directors:
            d = [str(x) for x in (m.get("directors") or [])]
            if not has_any_case_insensitive(directors, d):
                continue

        if content_rating and (m.get("contentRating") or "") != content_rating:
            continue

        r = float(m.get("rating") or 0.0)
        if rating_min is not None and r < rating_min:
            continue
        if rating_max is not None and r > rating_max:
            continue

        out.append(m)
    return out


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / ".env")

    settings = load_settings(project_root)
    plex_url = settings.plex_base_url
    plex_token = settings.plex_token or ""

    if not plex_token:
        print("❌ PLEX_TOKEN missing; set it in .env")
        return 2

    print(f"Connecting to Plex at {plex_url}...")
    plex = PlexClient(plex_url, plex_token, default_response_level=ResponseLevel.COMPACT)

    # Build tool callables exactly like the agent uses
    tool_get_sections = make_get_plex_library_sections(project_root)
    tool_recent = make_get_plex_recently_added(project_root)
    tool_unwatched = make_get_plex_unwatched(project_root)
    tool_on_deck = make_get_plex_on_deck(project_root)
    tool_search = make_search_plex(project_root)
    tool_details = make_get_plex_item_details(project_root)

    _print_section("Quick status")
    print(plex.get_quick_status())

    _print_section("Library sections")
    sections_res = asyncio.run(tool_get_sections({}))
    sections = sections_res.get("sections", {})
    for name, info in sections.items():
        print(f"- {name}: type={info.get('type')} count={info.get('count')} id={info.get('section_id')}")

    _print_section("Search movies: 'inception'")
    movies_res = asyncio.run(tool_search({
        "query": "inception",
        "limit": 10,
        "response_level": "standard",
        "filters": {
            "sort_by": "title",
            "sort_order": "asc"
        }
    }))
    movies = movies_res.get("items", [])
    _print_items(movies)

    _print_section("Search shows: 'office'")
    shows = []  # search_shows not exposed as a tool; keep as PlexClient direct call if needed
    _print_items(shows)

    # Targeted checks for user's known titles
    _print_section("Search movies: 'Pirates of the Caribbean' (+ common misspelling)")
    pirates_movies = asyncio.run(tool_search({
        "query": "pirates of the caribbean",
        "limit": 10,
        "response_level": "standard"
    })).get("items", [])
    pirates_movies_misspell = asyncio.run(tool_search({
        "query": "pirates of the carribean",
        "limit": 10,
        "response_level": "standard"
    })).get("items", [])
    _print_items(pirates_movies or [])
    _print_items(pirates_movies_misspell or [])
    # Broader sweep to catch partial titles
    pirates_all = plex.search_all("pirates", response_level=ResponseLevel.COMPACT)
    _print_likely_matches(pirates_all, "pirates")

    _print_section("Search shows: 'Samurai Flamenco'")
    samurai_shows = plex.search_shows("samurai flamenco", response_level=ResponseLevel.STANDARD)
    _print_items(samurai_shows or [])
    # Broader sweep across all media
    samurai_all = plex.search_all("samurai flamenco", response_level=ResponseLevel.COMPACT)
    _print_likely_matches(samurai_all, "samurai flamenco")

    _print_section("Recently added (Movies)")
    recent_movies = asyncio.run(tool_recent({
        "section_type": "movie",
        "limit": 10,
        "response_level": "compact"
    })).get("items", [])
    _print_items(recent_movies)

    _print_section("Recently added (Shows)")
    recent_shows = asyncio.run(tool_recent({
        "section_type": "show",
        "limit": 10,
        "response_level": "compact"
    })).get("items", [])
    _print_items(recent_shows)

    _print_section("On deck")
    on_deck = asyncio.run(tool_on_deck({
        "limit": 10,
        "response_level": "compact"
    })).get("items", [])
    _print_items(on_deck)

    _print_section("Unwatched (Movies)")
    unwatched_movies = asyncio.run(tool_unwatched({
        "section_type": "movie",
        "limit": 10,
        "response_level": "compact"
    })).get("items", [])
    _print_items(unwatched_movies)

    _print_section("Unwatched (Shows)")
    unwatched_shows = asyncio.run(tool_unwatched({
        "section_type": "show",
        "limit": 10,
        "response_level": "compact"
    })).get("items", [])
    _print_items(unwatched_shows)

    # Filtered examples using full library listings (to avoid relying on Plex search)
    _print_section("Filtered Movies: year>=2000, genres includes 'Action', rating>=7.0")
    try:
        movie_lib = plex.get_movie_library()
        all_movies = movie_lib.all()
        movies_detailed = plex._serialize_items(all_movies, ResponseLevel.DETAILED)
        filtered_movies = _filter_items(
            movies_detailed,
            year_min=2000,
            genres=["Action"],
            rating_min=7.0,
        )
        _print_items(filtered_movies)
        print(f"Total filtered movies: {len(filtered_movies)}")
    except Exception as e:
        print(f"(movies filter failed: {e})")

    _print_section("Filtered Shows: contentRating=TV-14 or TV-MA, year>=1990")
    try:
        tv_lib = plex.get_tv_library()
        all_shows = tv_lib.all()
        shows_detailed = plex._serialize_items(all_shows, ResponseLevel.DETAILED)
        # Combine two content ratings by running twice and merging results
        tv14 = _filter_items(shows_detailed, content_rating="TV-14", year_min=1990)
        tvma = _filter_items(shows_detailed, content_rating="TV-MA", year_min=1990)
        combined = {m.get("ratingKey"): m for m in (tv14 + tvma)}
        _print_items(list(combined.values()))
        print(f"Total filtered shows: {len(combined)}")
    except Exception as e:
        print(f"(shows filter failed: {e})")

    # Try fetching item details if any result exists
    first = (
        movies
        or recent_movies
        or on_deck
        or unwatched_movies
        or shows
        or recent_shows
        or unwatched_shows
    )
    if first:
        rk = first[0].get("ratingKey")
        if rk:
            _print_section(f"Item details for ratingKey={rk}")
            details_res = asyncio.run(tool_details({
                "rating_key": int(rk),
                "response_level": "detailed"
            }))
            details = details_res.get("item")
            if details:
                # Print a concise subset
                subset = {k: details.get(k) for k in ("title", "year", "rating", "genres", "summary", "type", "ratingKey", "videoResolution", "videoCodec", "audioCodec")}
                print(subset)

    print("\n✅ Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


