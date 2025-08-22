from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from integrations.plex_client import PlexClient, ResponseLevel
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
        bits = [str(title) if title is not None else "(no title)"]
        if year:
            bits.append(str(year))
        if rating is not None:
            bits.append(f"rating={rating}")
        if media_type:
            bits.append(f"type={media_type}")
        if rating_key is not None:
            bits.append(f"key={rating_key}")
        print(f"{i:02d}. " + " | ".join(bits))


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

    _print_section("Quick status")
    print(plex.get_quick_status())

    _print_section("Library sections")
    sections = plex.get_library_sections()
    for name, info in sections.items():
        print(f"- {name}: type={info.get('type')} count={info.get('count')} id={info.get('section_id')}")

    _print_section("Search movies: 'inception'")
    movies = plex.search_movies("inception", response_level=ResponseLevel.STANDARD)
    _print_items(movies)

    _print_section("Search shows: 'office'")
    shows = plex.search_shows("office", response_level=ResponseLevel.STANDARD)
    _print_items(shows)

    _print_section("Recently added (Movies)")
    recent_movies = plex.get_recently_added("movie", limit=10, response_level=ResponseLevel.COMPACT)
    _print_items(recent_movies)

    _print_section("Recently added (Shows)")
    recent_shows = plex.get_recently_added("show", limit=10, response_level=ResponseLevel.COMPACT)
    _print_items(recent_shows)

    _print_section("On deck")
    on_deck = plex.get_on_deck(limit=10, response_level=ResponseLevel.COMPACT)
    _print_items(on_deck)

    _print_section("Unwatched (Movies)")
    unwatched_movies = plex.get_unwatched("movie", limit=10, response_level=ResponseLevel.COMPACT)
    _print_items(unwatched_movies)

    _print_section("Unwatched (Shows)")
    unwatched_shows = plex.get_unwatched("show", limit=10, response_level=ResponseLevel.COMPACT)
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
            details = plex.get_item_details(int(rk), response_level=ResponseLevel.DETAILED)
            if details:
                # Print a concise subset
                subset = {k: details.get(k) for k in ("title", "year", "rating", "genres", "summary", "type", "ratingKey")}
                print(subset)

    print("\n✅ Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


