from __future__ import annotations

import json
import asyncio
import os
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Tuple, Union

try:
    import orjson  # type: ignore
except Exception:  # pragma: no cover
    orjson = None

from config.loader import load_settings, load_runtime_config
from integrations.plex_client import PlexClient, ResponseLevel
from integrations.tmdb_client import TMDbClient, TMDbResponseLevel
from integrations.radarr_client import RadarrClient
from integrations.sonarr_client import SonarrClient
import xml.etree.ElementTree as ET
import httpx


def make_search_plex(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        query = str(args.get("query", "")).strip()
        
        # Advanced filtering options
        filters = args.get("filters", {})
        year_min = filters.get("year_min")
        year_max = filters.get("year_max")
        genres = filters.get("genres", [])
        actors = filters.get("actors", [])
        directors = filters.get("directors", [])
        content_rating = filters.get("content_rating")
        rating_min = filters.get("rating_min")
        rating_max = filters.get("rating_max")
        sort_by = filters.get("sort_by", "title")
        sort_order = filters.get("sort_order", "asc")
        limit = args.get("limit", 20)
        response_level = ResponseLevel(args.get("response_level", "compact")) if args.get("response_level") else None
        
        settings = load_settings(project_root)
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        
        # Always perform server-side filtered search via section.search where possible
        results = await asyncio.to_thread(
            plex.search_movies_filtered,
            query or None,
            year_min=year_min,
            year_max=year_max,
            genres=genres,
            actors=actors,
            directors=directors,
            content_rating=content_rating,
            rating_min=rating_min,
            rating_max=rating_max,
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit,
            response_level=response_level,
        )
        
        return {
            "items": results,
            "total_found": len(results),
            "filters_applied": filters,
            "query": query,
            "response_level": response_level.value if response_level else "compact"
        }

    return impl


def _parse_plex_xml_videos(xml_text: str, response_level: ResponseLevel | None) -> List[Dict[str, Any]]:
    root = ET.fromstring(xml_text)
    items: List[Dict[str, Any]] = []
    for v in root.findall('.//Video'):
        title = v.get('title')
        year = v.get('year')
        rating_key = v.get('ratingKey')
        media_type = v.get('type')

        # Try to infer resolution/HDR from attributes across nodes
        video_resolution = v.get('videoResolution') or v.get('resolution')
        has_hdr = False

        # Helper to coerce numeric values safely
        def _as_int(val: str | None) -> int | None:
            if val and str(val).isdigit():
                try:
                    return int(val)
                except Exception:
                    return None
            return None

        # Inspect Media and nested Stream nodes for richer attributes
        for m in v.findall('Media'):
            if not video_resolution:
                video_resolution = m.get('videoResolution') or m.get('resolution')
            # Infer from width/height if needed
            if not video_resolution:
                width = _as_int(m.get('width'))
                height = _as_int(m.get('height'))
                if width and height:
                    if width >= 3800 or height >= 2000:
                        video_resolution = '4k'
                    elif height >= 1000 or width >= 1700:
                        video_resolution = '1080'
                    elif height and height >= 700:
                        video_resolution = '720'
            # Newer PMS exposes videoDynamicRange
            vdr = (m.get('videoDynamicRange') or '').upper()
            if any(tag in vdr for tag in ('HDR', 'DOLBY VISION', 'HLG', 'PQ', 'HDR10')):
                has_hdr = True
            # Some servers expose hdr=1/true
            hdr_attr = (m.get('hdr') or '').lower()
            if hdr_attr in {'1', 'true', 'yes'}:
                has_hdr = True
            # Streams may contain HDR hints in various attributes
            for s in m.findall('.//Stream'):
                attvals = ' '.join([str(vv).lower() for vv in s.attrib.values()])
                if any(k in attvals for k in ['hdr', 'dolby vision', 'dovi', 'hlg', 'pq', 'smpte2084', 'hdr10']):
                    has_hdr = True

        item: Dict[str, Any] = {
            'title': title,
            'year': int(year) if year and year.isdigit() else None,
            'ratingKey': int(rating_key) if rating_key and rating_key.isdigit() else rating_key,
            'type': media_type,
        }
        if response_level in [ResponseLevel.STANDARD, ResponseLevel.DETAILED, None]:
            item['videoResolution'] = video_resolution
            item['hasHDR'] = has_hdr
        items.append(item)
    return items


def make_get_plex_movies_4k_or_hdr(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        limit = int(args.get('limit', 30))
        or_semantics = bool(args.get('or_semantics', True))
        section_id = args.get('section_id')
        response_level = ResponseLevel(args.get('response_level', 'compact')) if args.get('response_level') else None

        settings = load_settings(project_root)
        # Discover movie section id if not provided
        if not section_id:
            plex = PlexClient(settings.plex_base_url, settings.plex_token or '')
            sections = plex.get_library_sections()
            chosen = None
            for _title, info in sections.items():
                if info.get('type') == 'movie':
                    chosen = info.get('section_id')
                    break
            if not chosen:
                # Fallback to first section
                if sections:
                    chosen = next(iter(sections.values())).get('section_id')
            if not chosen:
                raise ValueError('No Plex library sections available')
            section_id = str(chosen)
        else:
            section_id = str(section_id)

        base_url = settings.plex_base_url.rstrip('/')
        token = settings.plex_token or ''
        if not token:
            raise ValueError('PLEX_TOKEN is missing. Set it in your .env via the setup wizard.')

        async def _fetch(params: Dict[str, Any]) -> List[Dict[str, Any]]:
            qp: Dict[str, Any] = {
                'X-Plex-Token': token,
                'X-Plex-Container-Start': '0',
                'X-Plex-Container-Size': str(limit),
                'type': '1',  # movies
            }
            qp.update(params)
            url = f"{base_url}/library/sections/{section_id}/all"
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(url, params=qp, headers={'Accept': 'application/xml'})
                r.raise_for_status()
                return _parse_plex_xml_videos(r.text, response_level)

        attempts: List[Tuple[Dict[str, Any], int, Union[str, None]]] = []
        items: List[Dict[str, Any]] = []

        # Try OR variants first if requested
        if or_semantics:
            variants = [
                {'or': '1', 'resolution': '4k', 'hdr': '1'},
                {'or': '1', 'videoResolution': '4k', 'hdr': '1'},
                {'or': '1', 'resolution': '4k', 'hdr': 'true'},
                {'or': '1', 'videoResolution': '4k', 'hdr': 'true'},
            ]
            for p in variants:
                try:
                    res = await _fetch(p)
                    attempts.append((p, len(res), None))
                    if res:
                        items = res
                        break
                except Exception as e:
                    attempts.append((p, 0, str(e)))

        # If still empty, union of separate queries
        if not items:
            unions: Dict[Any, Dict[str, Any]] = {}
            fallbacks = [
                {'resolution': '4k'},
                {'videoResolution': '4k'},
                {'hdr': '1'},
                {'hdr': 'true'},
            ]
            for p in fallbacks:
                try:
                    res = await _fetch(p)
                    attempts.append((p, len(res), None))
                    for it in res:
                        rk = it.get('ratingKey')
                        unions[rk] = it
                    if len(unions) >= limit:
                        break
                except Exception as e:
                    attempts.append((p, 0, str(e)))
            items = list(unions.values())[:limit]

        return {
            'items': items,
            'total_found': len(items),
            'section_id': section_id,
            'attempts': attempts,
            'response_level': response_level.value if response_level else 'compact'
        }

    return impl

def _serialize_datetime(value):
    """Safely serialize datetime objects and other types to JSON-compatible format."""
    if value is None:
        return None
    
    # Handle datetime objects
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    
    # Handle other potentially problematic types
    if hasattr(value, '__str__'):
        return str(value)
    
    return value


def _matches_filters(movie, year_min, year_max, genres, actors, directors, 
                    content_rating, rating_min, rating_max):
    """Check if a movie matches all the specified filters."""
    def _get(field: str):
        if isinstance(movie, dict):
            return movie.get(field)
        return getattr(movie, field, None)

    # Year filtering
    year_val = _get("year") or 0
    if year_min is not None and year_val < year_min:
        return False
    year_max_val = _get("year") or 9999
    if year_max is not None and year_max_val > year_max:
        return False
    
    # Genre filtering (any genre match is sufficient)
    if genres:
        raw = _get("genres") or []
        # Serialized dicts carry genres as list[str]; objects as list of tag objects
        if raw and isinstance(raw[0], str):
            movie_genres = [g.lower() for g in raw]
        else:
            movie_genres = [getattr(genre, "tag", "").lower() for genre in (raw or [])]
        if not any(genre.lower() in movie_genres for genre in genres):
            return False
    
    # Actor filtering (any actor match is sufficient)
    if actors:
        raw = _get("actors") or []
        if raw and isinstance(raw[0], str):
            movie_actors = [a.lower() for a in raw]
        else:
            movie_actors = [getattr(actor, "tag", "").lower() for actor in (raw or [])]
        if not any(actor.lower() in movie_actors for actor in actors):
            return False
    
    # Director filtering (any director match is sufficient)
    if directors:
        raw = _get("directors") or []
        if raw and isinstance(raw[0], str):
            movie_directors = [d.lower() for d in raw]
        else:
            movie_directors = [getattr(director, "tag", "").lower() for director in (raw or [])]
        if not any(director.lower() in movie_directors for director in directors):
            return False
    
    # Content rating filtering
    if content_rating and (_get("contentRating") or "") != content_rating:
        return False
    
    # Rating filtering
    rating_val = _get("rating") or 0
    if rating_min is not None and rating_val < rating_min:
        return False
    rating_max_val = _get("rating") or 10
    if rating_max is not None and rating_max_val > rating_max:
        return False
    
    return True


def _sort_movies(movies, sort_by, sort_order):
    """Sort movies by the specified attribute and order."""
    reverse = sort_order.lower() == "desc"
    
    def get_sort_key(movie):
        if isinstance(movie, dict):
            value = movie.get(sort_by)
        else:
            value = getattr(movie, sort_by, None)
        if value is None:
            return "" if sort_order.lower() == "asc" else "zzzzz"
        return value
    
    try:
        return sorted(movies, key=get_sort_key, reverse=reverse)
    except (TypeError, AttributeError):
        # Fallback to title sorting if the specified sort_by fails
        def _title(m):
            if isinstance(m, dict):
                return m.get("title", "")
            return getattr(m, "title", "")
        return sorted(movies, key=_title, reverse=reverse)


def make_set_plex_rating(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        rating_key = int(args["rating_key"])  # raises if missing
        rating = int(args["rating"])  # raises if missing
        settings = load_settings(project_root)
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        await asyncio.to_thread(plex.set_rating, rating_key, rating)
        return {"ok": True}

    return impl


def make_tmdb_search(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        query = str(args.get("query", "")).strip()
        year = args.get("year")
        primary_release_year = args.get("primary_release_year")
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        response_level = TMDbResponseLevel(args.get("response_level", "compact")) if args.get("response_level") else None
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.search_movie(query, year, primary_release_year, language, page, response_level)
        return data

    return impl


def make_tmdb_recommendations(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        tmdb_id = int(args["tmdb_id"])  # raises if missing
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        response_level = TMDbResponseLevel(args.get("response_level", "compact")) if args.get("response_level") else None
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.recommendations(tmdb_id, language, page, response_level)
        return data

    return impl


def make_tmdb_discover_movies(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Advanced movie discovery with comprehensive filtering"""
    async def impl(args: dict) -> dict:
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        
        # Extract filter parameters
        sort_by = str(args.get("sort_by", "popularity.desc"))
        year = args.get("year")
        primary_release_year = args.get("primary_release_year")
        with_genres = args.get("with_genres")  # List of genre IDs
        without_genres = args.get("without_genres")  # List of genre IDs
        with_cast = args.get("with_cast")  # List of person IDs
        with_crew = args.get("with_crew")  # List of person IDs
        with_keywords = args.get("with_keywords")  # List of keyword IDs
        with_runtime_gte = args.get("with_runtime_gte")  # Minimum runtime in minutes
        with_runtime_lte = args.get("with_runtime_lte")  # Maximum runtime in minutes
        with_original_language = args.get("with_original_language")
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        response_level = TMDbResponseLevel(args.get("response_level", "compact")) if args.get("response_level") else None
        
        data = await tmdb.discover_movies(
            sort_by=sort_by,
            year=year,
            primary_release_year=primary_release_year,
            with_genres=with_genres,
            without_genres=without_genres,
            with_cast=with_cast,
            with_crew=with_crew,
            with_keywords=with_keywords,
            with_runtime_gte=with_runtime_gte,
            with_runtime_lte=with_runtime_lte,
            with_original_language=with_original_language,
            language=language,
            page=page,
            response_level=response_level
        )
        return data

    return impl


def make_tmdb_discover_tv(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Advanced TV series discovery with comprehensive filtering"""
    async def impl(args: dict) -> dict:
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        
        # Extract filter parameters
        sort_by = str(args.get("sort_by", "popularity.desc"))
        first_air_date_year = args.get("first_air_date_year")
        with_genres = args.get("with_genres")  # List of genre IDs
        without_genres = args.get("without_genres")  # List of genre IDs
        with_cast = args.get("with_cast")  # List of person IDs
        with_crew = args.get("with_crew")  # List of person IDs
        with_keywords = args.get("with_keywords")  # List of keyword IDs
        with_runtime_gte = args.get("with_runtime_gte")  # Minimum runtime in minutes
        with_runtime_lte = args.get("with_runtime_lte")  # Maximum runtime in minutes
        with_original_language = args.get("with_original_language")
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        response_level = TMDbResponseLevel(args.get("response_level", "compact")) if args.get("response_level") else None
        
        data = await tmdb.discover_tv(
            sort_by=sort_by,
            first_air_date_year=first_air_date_year,
            with_genres=with_genres,
            without_genres=without_genres,
            with_cast=with_cast,
            with_crew=with_crew,
            with_keywords=with_keywords,
            with_runtime_gte=with_runtime_gte,
            with_runtime_lte=with_runtime_lte,
            with_original_language=with_original_language,
            language=language,
            page=page,
            response_level=response_level
        )
        return data

    return impl


def make_tmdb_trending(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get trending movies, TV shows, or people"""
    async def impl(args: dict) -> dict:
        media_type = str(args.get("media_type", "all"))  # all, movie, tv, person
        time_window = str(args.get("time_window", "week"))  # day, week
        language = str(args.get("language", "en-US"))
        response_level = TMDbResponseLevel(args.get("response_level", "compact")) if args.get("response_level") else None
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.trending(media_type, time_window, language, response_level)
        return data

    return impl


def make_tmdb_popular_movies(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get popular movies"""
    async def impl(args: dict) -> dict:
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        response_level = TMDbResponseLevel(args.get("response_level", "compact")) if args.get("response_level") else None
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.popular_movies(language, page, response_level)
        return data

    return impl


def make_tmdb_top_rated_movies(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get top rated movies"""
    async def impl(args: dict) -> dict:
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        response_level = TMDbResponseLevel(args.get("response_level", "compact")) if args.get("response_level") else None
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.top_rated_movies(language, page, response_level)
        return data

    return impl


def make_tmdb_upcoming_movies(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get upcoming movie releases"""
    async def impl(args: dict) -> dict:
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        response_level = TMDbResponseLevel(args.get("response_level", "compact")) if args.get("response_level") else None
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.upcoming_movies(language, page, response_level)
        return data

    return impl


def make_tmdb_now_playing_movies(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get movies currently in theaters"""
    async def impl(args: dict) -> dict:
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        response_level = TMDbResponseLevel(args.get("response_level", "compact")) if args.get("response_level") else None
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.now_playing_movies(language, page, response_level)
        return data

    return impl


def make_tmdb_popular_tv(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get popular TV series"""
    async def impl(args: dict) -> dict:
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        response_level = TMDbResponseLevel(args.get("response_level", "compact")) if args.get("response_level") else None
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.popular_tv(language, page, response_level)
        return data

    return impl


def make_tmdb_top_rated_tv(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get top rated TV series"""
    async def impl(args: dict) -> dict:
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        response_level = TMDbResponseLevel(args.get("response_level", "compact")) if args.get("response_level") else None
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.top_rated_tv(language, page, response_level)
        return data

    return impl


def make_tmdb_on_the_air_tv(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get TV series currently on the air"""
    async def impl(args: dict) -> dict:
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        response_level = TMDbResponseLevel(args.get("response_level", "compact")) if args.get("response_level") else None
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.on_the_air_tv(language, page, response_level)
        return data

    return impl


def make_tmdb_airing_today_tv(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get TV series airing today"""
    async def impl(args: dict) -> dict:
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        response_level = TMDbResponseLevel(args.get("response_level", "compact")) if args.get("response_level") else None
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.airing_today_tv(language, page, response_level)
        return data

    return impl


def make_tmdb_movie_details(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get comprehensive movie details including credits, videos, images"""
    async def impl(args: dict) -> dict:
        movie_id = int(args["movie_id"])
        language = str(args.get("language", "en-US"))
        append_to_response = args.get("append_to_response")  # e.g., "credits,videos,images"
        response_level = TMDbResponseLevel(args.get("response_level", "detailed")) if args.get("response_level") else None
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.movie_details(movie_id, language, append_to_response, response_level)
        return data

    return impl


def make_tmdb_tv_details(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get comprehensive TV series details"""
    async def impl(args: dict) -> dict:
        tv_id = int(args["tv_id"])
        language = str(args.get("language", "en-US"))
        append_to_response = args.get("append_to_response")  # e.g., "credits,videos,images"
        response_level = TMDbResponseLevel(args.get("response_level", "detailed")) if args.get("response_level") else None
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.tv_details(tv_id, language, append_to_response, response_level)
        return data

    return impl


def make_tmdb_similar_movies(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get similar movies to a specific movie"""
    async def impl(args: dict) -> dict:
        movie_id = int(args["movie_id"])
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        response_level = TMDbResponseLevel(args.get("response_level", "compact")) if args.get("response_level") else None
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.similar_movies(movie_id, language, page, response_level)
        return data

    return impl


def make_tmdb_similar_tv(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get similar TV series to a specific series"""
    async def impl(args: dict) -> dict:
        tv_id = int(args["tv_id"])
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        response_level = TMDbResponseLevel(args.get("response_level", "compact")) if args.get("response_level") else None
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.similar_tv(tv_id, language, page, response_level)
        return data

    return impl


def make_tmdb_search_tv(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Search for TV series"""
    async def impl(args: dict) -> dict:
        query = str(args.get("query", "")).strip()
        first_air_date_year = args.get("first_air_date_year")
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        response_level = TMDbResponseLevel(args.get("response_level", "compact")) if args.get("response_level") else None
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.search_tv(query, first_air_date_year, language, page, response_level)
        return data

    return impl


def make_tmdb_search_multi(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Search across movies, TV shows, and people"""
    async def impl(args: dict) -> dict:
        query = str(args.get("query", "")).strip()
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        response_level = TMDbResponseLevel(args.get("response_level", "compact")) if args.get("response_level") else None
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.search_multi(query, language, page, response_level)
        return data

    return impl


def make_tmdb_search_person(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Search for people (actors, directors, etc.)"""
    async def impl(args: dict) -> dict:
        query = str(args.get("query", "")).strip()
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        response_level = TMDbResponseLevel(args.get("response_level", "compact")) if args.get("response_level") else None
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.search_person(query, language, page, response_level)
        return data

    return impl


def make_tmdb_genres(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get available genres for movies or TV"""
    async def impl(args: dict) -> dict:
        media_type = str(args.get("media_type", "movie"))  # movie or tv
        language = str(args.get("language", "en-US"))
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.genres(media_type, language)
        return data

    return impl


def make_tmdb_collection_details(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get details about a movie collection/franchise"""
    async def impl(args: dict) -> dict:
        collection_id = int(args["collection_id"])
        language = str(args.get("language", "en-US"))
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.collection_details(collection_id, language)
        return data

    return impl


def make_tmdb_watch_providers_movie(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get where a movie can be watched (streaming, rental, etc.)"""
    async def impl(args: dict) -> dict:
        movie_id = int(args["movie_id"])
        language = str(args.get("language", "en-US"))
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.watch_providers_movie(movie_id, language)
        return data

    return impl


def make_tmdb_watch_providers_tv(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get where a TV series can be watched"""
    async def impl(args: dict) -> dict:
        tv_id = int(args["tv_id"])
        language = str(args.get("language", "en-US"))
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.watch_providers_tv(tv_id, language)
        return data

    return impl


def make_sonarr_lookup(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        term = str(args.get("term", "")).strip()
        settings = load_settings(project_root)
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        data = await sonarr.lookup(term)
        await sonarr.close()
        return {"results": data}

    return impl


def make_sonarr_add_series(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        settings = load_settings(project_root)
        config = load_runtime_config(project_root)
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        
        # Enhanced parameters for better control
        seasons_to_monitor = args.get("seasons_to_monitor")
        episodes_to_monitor = args.get("episodes_to_monitor")
        monitor_new_episodes = args.get("monitor_new_episodes", True)
        
        # Get configuration values with validation
        quality_profile_id = args.get("quality_profile_id") or config.get("sonarr", {}).get("qualityProfileId")
        root_folder_path = args.get("root_folder_path") or config.get("sonarr", {}).get("rootFolderPath")
        
        if not quality_profile_id:
            raise ValueError("Sonarr quality profile ID not configured. Set in config/config.yaml or pass quality_profile_id")
        if not root_folder_path:
            raise ValueError("Sonarr root folder path not configured. Set in config/config.yaml or pass root_folder_path")
        
        data = await sonarr.add_series(
            tvdb_id=int(args["tvdb_id"]),
            quality_profile_id=int(quality_profile_id),
            root_folder_path=str(root_folder_path),
            monitored=bool(args.get("monitored", True)),
            search_for_missing=bool(args.get("search_for_missing", True)),
            season_folder=bool(args.get("season_folder", True)),
            # Enhanced parameters
            seasons_to_monitor=seasons_to_monitor,
            episodes_to_monitor=episodes_to_monitor,
            monitor_new_episodes=monitor_new_episodes,
        )
        await sonarr.close()
        return data

    return impl


def make_sonarr_get_series(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        series_id = args.get("series_id")
        settings = load_settings(project_root)
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        data = await sonarr.get_series(series_id)
        await sonarr.close()
        return {"series": data}

    return impl


def make_sonarr_update_series(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        series_id = int(args["series_id"])
        update_data = args.get("update_data", {})
        settings = load_settings(project_root)
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        data = await sonarr.update_series(series_id, **update_data)
        await sonarr.close()
        return {"updated_series": data}

    return impl


def make_sonarr_delete_series(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        series_id = int(args["series_id"])
        delete_files = bool(args.get("delete_files", False))
        add_import_list_exclusion = bool(args.get("add_import_list_exclusion", False))
        settings = load_settings(project_root)
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        await sonarr.delete_series(series_id, delete_files, add_import_list_exclusion)
        await sonarr.close()
        return {"ok": True, "deleted_series_id": series_id}

    return impl


def make_sonarr_get_episodes(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        series_id = args.get("series_id")
        episode_ids = args.get("episode_ids")
        settings = load_settings(project_root)
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        data = await sonarr.get_episodes(series_id, episode_ids)
        await sonarr.close()
        return {"episodes": data}

    return impl


def make_sonarr_monitor_episodes(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        episode_ids = [int(id) for id in args["episode_ids"]]
        monitored = bool(args["monitored"])
        settings = load_settings(project_root)
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        data = await sonarr.monitor_episodes(episode_ids, monitored)
        await sonarr.close()
        return {"updated_episodes": data}

    return impl


def make_sonarr_search_series(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        series_id = int(args["series_id"])
        settings = load_settings(project_root)
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        data = await sonarr.search_series(series_id)
        await sonarr.close()
        return {"search_command": data}

    return impl


def make_sonarr_search_missing(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        settings = load_settings(project_root)
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        data = await sonarr.search_missing()
        await sonarr.close()
        return {"search_command": data}

    return impl


def make_sonarr_get_queue(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        settings = load_settings(project_root)
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        data = await sonarr.get_queue()
        await sonarr.close()
        return {"queue": data}

    return impl


def make_sonarr_get_wanted(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        page = int(args.get("page", 1))
        page_size = int(args.get("page_size", 20))
        sort_key = str(args.get("sort_key", "airDateUtc"))
        sort_dir = str(args.get("sort_dir", "desc"))
        settings = load_settings(project_root)
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        data = await sonarr.get_wanted(page, page_size, sort_key, sort_dir)
        await sonarr.close()
        return {"wanted": data}

    return impl


def make_sonarr_get_calendar(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        start_date = args.get("start_date")
        end_date = args.get("end_date")
        settings = load_settings(project_root)
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        data = await sonarr.get_calendar(start_date, end_date)
        await sonarr.close()
        return {"calendar": data}

    return impl


def make_sonarr_system_status(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        settings = load_settings(project_root)
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        data = await sonarr.system_status()
        await sonarr.close()
        return {"system_status": data}

    return impl


def make_sonarr_health(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        settings = load_settings(project_root)
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        data = await sonarr.health()
        await sonarr.close()
        return {"health": data}

    return impl


def make_sonarr_disk_space(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        settings = load_settings(project_root)
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        data = await sonarr.disk_space()
        await sonarr.close()
        return {"disk_space": data}

    return impl


def make_sonarr_quality_profiles(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        settings = load_settings(project_root)
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        data = await sonarr.quality_profiles()
        await sonarr.close()
        return {"quality_profiles": data}

    return impl


def make_sonarr_root_folders(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        settings = load_settings(project_root)
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        data = await sonarr.root_folders()
        await sonarr.close()
        return {"root_folders": data}

    return impl


# Enhanced Sonarr Tools
def make_sonarr_monitor_season(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        series_id = int(args["series_id"])
        season_number = int(args["season_number"])
        monitored = bool(args["monitored"])
        settings = load_settings(project_root)
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        data = await sonarr.monitor_season(series_id, season_number, monitored)
        await sonarr.close()
        return {"season_monitoring_updated": data}

    return impl


def make_sonarr_monitor_episodes_by_season(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        series_id = int(args["series_id"])
        season_number = int(args["season_number"])
        monitored = bool(args["monitored"])
        settings = load_settings(project_root)
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        data = await sonarr.monitor_episodes_by_season(series_id, season_number, monitored)
        await sonarr.close()
        return {"episodes_monitoring_updated": data}

    return impl


def make_sonarr_search_season(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        series_id = int(args["series_id"])
        season_number = int(args["season_number"])
        settings = load_settings(project_root)
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        data = await sonarr.search_season(series_id, season_number)
        await sonarr.close()
        return {"season_search_command": data}

    return impl


def make_sonarr_search_episodes(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        episode_ids = [int(id) for id in args["episode_ids"]]
        settings = load_settings(project_root)
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        data = await sonarr.search_episodes(episode_ids)
        await sonarr.close()
        return {"episodes_search_command": data}

    return impl


def make_sonarr_get_series_summary(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        series_id = int(args["series_id"])
        settings = load_settings(project_root)
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        data = await sonarr.get_series_summary(series_id)
        await sonarr.close()
        return {"series_summary": data}

    return impl


def make_sonarr_get_season_summary(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        series_id = int(args["series_id"])
        season_number = int(args["season_number"])
        settings = load_settings(project_root)
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        data = await sonarr.get_season_summary(series_id, season_number)
        await sonarr.close()
        return {"season_summary": data}

    return impl


def make_sonarr_get_season_details(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        series_id = int(args["series_id"])
        season_number = int(args["season_number"])
        settings = load_settings(project_root)
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        data = await sonarr.get_season_details(series_id, season_number)
        await sonarr.close()
        return {"season_details": data}

    return impl


def make_sonarr_get_episode_file_info(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        episode_id = int(args["episode_id"])
        settings = load_settings(project_root)
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        data = await sonarr.get_episode_file_info(episode_id)
        await sonarr.close()
        return {"episode_file_info": data}

    return impl


def make_sonarr_episode_fallback_search(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Handle episode fallback search when season packs fail using sub-agent."""
    async def impl(args: dict) -> dict:
        from bot.sub_agent import SubAgent
        
        series_id = int(args["series_id"])
        season_number = int(args["season_number"])
        series_title = str(args["series_title"])
        target_episodes = [int(ep) for ep in args["target_episodes"]]
        
        settings = load_settings(project_root)
        config = load_runtime_config(project_root)
        
        # Get provider from main agent context or fall back to config
        # The main agent should pass this information when calling the tool
        provider = args.get("provider") or config.get("llm", {}).get("provider", "openai")
        api_key = args.get("api_key") or settings.openai_api_key or config.get("llm", {}).get("apiKey", "")
        
        # Create sub-agent for focused episode search with correct provider settings
        sub_agent = SubAgent(
            api_key=api_key,
            project_root=project_root,
            provider=provider
        )
        
        try:
            result = await sub_agent.handle_episode_fallback_search(
                series_id, season_number, series_title, target_episodes
            )
            return result
        finally:
            # Clean up sub-agent resources
            if hasattr(sub_agent.llm, 'client') and hasattr(sub_agent.llm.client, 'close'):
                await sub_agent.llm.client.close()

    return impl


def make_sonarr_quality_fallback(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Handle quality fallback when preferred quality isn't available using sub-agent."""
    async def impl(args: dict) -> dict:
        from bot.sub_agent import SubAgent
        
        series_id = int(args["series_id"])
        target_quality = str(args["target_quality"])
        fallback_qualities = [str(q) for q in args["fallback_qualities"]]
        
        settings = load_settings(project_root)
        config = load_runtime_config(project_root)
        
        # Get provider from main agent context or fall back to config
        # The main agent should pass this information when calling the tool
        provider = args.get("provider") or config.get("llm", {}).get("provider", "openai")
        api_key = args.get("api_key") or settings.openai_api_key or config.get("llm", {}).get("apiKey", "")
        
        # Create sub-agent for quality management with correct provider settings
        sub_agent = SubAgent(
            api_key=api_key,
            project_root=project_root,
            provider=provider
        )
        
        try:
            result = await sub_agent.handle_quality_fallback(
                series_id, target_quality, fallback_qualities
            )
            return result
        finally:
            # Clean up sub-agent resources
            if hasattr(sub_agent.llm, 'client') and hasattr(sub_agent.llm.client, 'close'):
                await sub_agent.llm.client.close()

    return impl


def make_radarr_lookup(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        term = str(args.get("term", "")).strip()
        settings = load_settings(project_root)
        radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key or "")
        data = await radarr.lookup(term)
        await radarr.close()
        return {"results": data}

    return impl


def make_radarr_add_movie(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        settings = load_settings(project_root)
        config = load_runtime_config(project_root)
        radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key or "")
        data = await radarr.add_movie(
            tmdb_id=int(args["tmdb_id"]),
            quality_profile_id=int(args.get("quality_profile_id") or config.get("radarr", {}).get("qualityProfileId")),
            root_folder_path=str(args.get("root_folder_path") or config.get("radarr", {}).get("rootFolderPath")),
            monitored=bool(args.get("monitored", True)),
            search_now=bool(args.get("search_now", True)),
        )
        await radarr.close()
        return data

    return impl


def make_radarr_get_movies(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        movie_id = args.get("movie_id")
        settings = load_settings(project_root)
        radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key or "")
        data = await radarr.get_movies(movie_id)
        await radarr.close()
        return {"movies": data}

    return impl


def make_radarr_update_movie(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        movie_id = int(args["movie_id"])
        update_data = args.get("update_data", {})
        settings = load_settings(project_root)
        radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key or "")
        data = await radarr.update_movie(movie_id, **update_data)
        await radarr.close()
        return {"updated_movie": data}

    return impl


def make_radarr_delete_movie(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        movie_id = int(args["movie_id"])
        delete_files = bool(args.get("delete_files", False))
        add_import_list_exclusion = bool(args.get("add_import_list_exclusion", False))
        settings = load_settings(project_root)
        radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key or "")
        await radarr.delete_movie(movie_id, delete_files, add_import_list_exclusion)
        await radarr.close()
        return {"ok": True, "deleted_movie_id": movie_id}

    return impl


def make_radarr_search_movie(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        movie_id = int(args["movie_id"])
        settings = load_settings(project_root)
        radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key or "")
        data = await radarr.search_movie(movie_id)
        await radarr.close()
        return {"search_command": data}

    return impl


def make_radarr_search_missing(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        settings = load_settings(project_root)
        radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key or "")
        data = await radarr.search_missing()
        await radarr.close()
        return {"search_command": data}

    return impl


def make_radarr_search_cutoff(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        settings = load_settings(project_root)
        radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key or "")
        data = await radarr.search_cutoff()
        await radarr.close()
        return {"search_command": data}

    return impl


def make_radarr_get_queue(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        settings = load_settings(project_root)
        radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key or "")
        data = await radarr.get_queue()
        await radarr.close()
        return {"queue": data}

    return impl


def make_radarr_get_wanted(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        page = int(args.get("page", 1))
        page_size = int(args.get("page_size", 20))
        sort_key = str(args.get("sort_key", "releaseDate"))
        sort_dir = str(args.get("sort_dir", "desc"))
        settings = load_settings(project_root)
        radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key or "")
        data = await radarr.get_wanted(page, page_size, sort_key, sort_dir)
        await radarr.close()
        return {"wanted": data}

    return impl


def make_radarr_get_calendar(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        start_date = args.get("start_date")
        end_date = args.get("end_date")
        settings = load_settings(project_root)
        radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key or "")
        data = await radarr.get_calendar(start_date, end_date)
        await radarr.close()
        return {"calendar": data}

    return impl


def make_radarr_get_blacklist(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        page = int(args.get("page", 1))
        page_size = int(args.get("page_size", 20))
        settings = load_settings(project_root)
        radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key or "")
        data = await radarr.get_blacklist(page, page_size)
        await radarr.close()
        return {"blacklist": data}

    return impl


def make_radarr_clear_blacklist(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        settings = load_settings(project_root)
        radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key or "")
        await radarr.clear_blacklist()
        await radarr.close()
        return {"ok": True, "message": "Blacklist cleared"}

    return impl


def make_radarr_system_status(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        settings = load_settings(project_root)
        radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key or "")
        data = await radarr.system_status()
        await radarr.close()
        return {"system_status": data}

    return impl


def make_radarr_health(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        settings = load_settings(project_root)
        radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key or "")
        data = await radarr.health()
        await radarr.close()
        return {"health": data}

    return impl


def make_radarr_disk_space(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        settings = load_settings(project_root)
        radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key or "")
        data = await radarr.disk_space()
        await radarr.close()
        return {"disk_space": data}

    return impl


def make_radarr_quality_profiles(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        settings = load_settings(project_root)
        radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key or "")
        data = await radarr.quality_profiles()
        await radarr.close()
        return {"quality_profiles": data}

    return impl


def make_radarr_root_folders(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        settings = load_settings(project_root)
        radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key or "")
        data = await radarr.root_folders()
        await radarr.close()
        return {"root_folders": data}

    return impl


def make_radarr_get_indexers(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        settings = load_settings(project_root)
        radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key or "")
        data = await radarr.get_indexers()
        await radarr.close()
        return {"indexers": data}

    return impl


def make_radarr_get_download_clients(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        settings = load_settings(project_root)
        radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key or "")
        data = await radarr.get_download_clients()
        await radarr.close()
        return {"download_clients": data}

    return impl


def _flatten(obj: Any, base_path: str = "") -> List[Tuple[str, str]]:
    items: List[Tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{base_path}.{k}" if base_path else k
            items.extend(_flatten(v, path))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            path = f"{base_path}[{i}]"
            items.extend(_flatten(v, path))
    else:
        items.append((base_path, str(obj)))
    return items


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    return [str(value)]


def _join(values: List[str], *, empty: str = "-", max_items: int | None = None) -> str:
    if not values:
        return empty
    items = values if (max_items is None or len(values) <= max_items) else values[:max_items] + ["…"]
    return ", ".join(items)


def _pick(obj: Dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in obj:
            return obj[k]
    return None


def build_preferences_context(data: Dict[str, Any]) -> str:
    """Build a compact, curated context string from the household preferences JSON."""
    likes = data.get("likes", {}) or {}
    dislikes = data.get("dislikes", {}) or {}
    constraints = data.get("constraints", {}) or {}
    profile = data.get("profile", {}) or {}
    anchors = data.get("anchors", {}) or {}
    heuristics = data.get("heuristics", {}) or {}
    curiosities = data.get("currentCuriosities", {}) or {}

    # Header / snapshot
    notes = (data.get("notes") or "").strip()
    plaus = profile.get("plausibilityScore10")
    header_bits: List[str] = []
    if notes:
        header_bits.append(notes)
    if plaus is not None:
        header_bits.append(f"plausibility ~{plaus}/10")
    header = "; ".join(header_bits)

    # Likes / dislikes
    like_genres = _join(_as_list(likes.get("genres")), max_items=8)
    like_people = _join(_as_list(likes.get("people")), max_items=8)
    like_vibes = _join(_as_list(likes.get("vibes")), max_items=8)
    like_aesthetics = _join(_as_list(likes.get("aesthetics")), max_items=8)
    like_motifs = _join(_as_list(likes.get("motifs")), max_items=8)

    dislike_genres = _join(_as_list(dislikes.get("genres")), max_items=8)
    dislike_aesthetics = _join(_as_list(dislikes.get("aesthetics")), max_items=8)
    dislike_tones = _join(_as_list(dislikes.get("tones")), max_items=8)
    dislike_structure = _join(_as_list(dislikes.get("structure")), max_items=8)
    dislike_vibes = _join(_as_list(dislikes.get("vibes")), max_items=8)

    # Constraints
    era_min = constraints.get("eraMinYear")
    lang_whitelist = _join(_as_list(_pick(constraints, "languageWhitelist", "languages")), max_items=6)
    rt = constraints.get("runtimeSweetSpotMins") or []
    rt_str = f"{rt[0]}–{rt[1]} min" if isinstance(rt, list) and len(rt) == 2 else "-"
    cw = _join(_as_list(constraints.get("contentWarnings")))
    visuals_disallow = _join(_as_list(constraints.get("visualsDisallow")))
    jumps = constraints.get("allowJumpScares")

    # Profile sliders / cues
    tone_non = _pick(profile.get("tone", {}), "nonHorror") if isinstance(profile.get("tone"), dict) else None
    tone_hor = _pick(profile.get("tone", {}), "horror") if isinstance(profile.get("tone"), dict) else None
    pacing = profile.get("pacing")
    structure = profile.get("structure")
    visuals = profile.get("visuals")
    reality = profile.get("reality")
    meta = profile.get("meta")
    ending = profile.get("ending")
    gore = profile.get("goreViolence")
    humor_non = _pick(profile.get("humor", {}), "nonHorror") if isinstance(profile.get("humor"), dict) else None
    humor_hor = _pick(profile.get("humor", {}), "horror") if isinstance(profile.get("humor"), dict) else None

    # Anchors
    loved = _join(_as_list(anchors.get("loved")), max_items=8)
    responded = _join(_as_list(_pick(anchors, "respondedTo", "responded")), max_items=8)
    comfort = _join(_as_list(anchors.get("comfortSignals")), max_items=8)
    faces = _join(_as_list(_pick(anchors, "trustedFaces", "faces")), max_items=8)

    # Heuristics
    lead = heuristics.get("lead")
    pairing = heuristics.get("pairing")
    themes = _join(_as_list(heuristics.get("themes")), max_items=8)
    chamber = heuristics.get("chamber")
    slow_burn = heuristics.get("slowBurn")
    exposition = heuristics.get("exposition")
    couple_first = heuristics.get("coupleFirst")
    zero_spoilers = heuristics.get("zeroSpoilers")
    max_options = heuristics.get("maxOptions")

    # Curiosities
    vibes_tonight = _join(_as_list(_pick(curiosities, "vibesTonight", "vibes")), max_items=6)
    themes_soon = _join(_as_list(_pick(curiosities, "themesSoon", "themes")), max_items=6)

    anti = _join(_as_list(data.get("antiPreferences")), max_items=8)
    never_titles = _join(_as_list(data.get("neverRecommend", {}).get("titles")), max_items=8)

    parts: List[str] = []
    if header:
        parts.append(f"Flavor: {header}.")
    parts.append(f"Constraints: {era_min or '-'}+, lang [{lang_whitelist}], runtime {rt_str}; disallow [{visuals_disallow}]; flags [{cw}]; jump scares: {'ok' if jumps else 'avoid' if jumps is False else '-'}.")
    parts.append(f"Likes: genres [{like_genres}]; vibes [{like_vibes}]; aesthetics [{like_aesthetics}]; motifs [{like_motifs}]; faces [{like_people}].")
    parts.append(f"Dislikes: genres [{dislike_genres}]; aesthetics [{dislike_aesthetics}]; tones [{dislike_tones}]; structure [{dislike_structure}]; vibes [{dislike_vibes}].")
    # Profile cues condensed
    profile_bits: List[str] = []
    if tone_non:
        profile_bits.append(f"non-horror tone: {tone_non}")
    if tone_hor:
        profile_bits.append(f"horror tone: {tone_hor}")
    for label, val in ("pacing", pacing), ("structure", structure), ("visuals", visuals), ("reality", reality), ("meta", meta), ("ending", ending), ("gore/violence", gore):
        if val:
            profile_bits.append(f"{label}: {val}")
    if humor_non:
        profile_bits.append(f"humor(non-horror): {humor_non}")
    if humor_hor:
        profile_bits.append(f"humor(horror): {humor_hor}")
    if profile_bits:
        parts.append("Profile: " + "; ".join(profile_bits) + ".")
    # Anchors
    anchor_bits: List[str] = []
    if loved and loved != "-":
        anchor_bits.append(f"loved [{loved}]")
    if responded and responded != "-":
        anchor_bits.append(f"responded [{responded}]")
    if comfort and comfort != "-":
        anchor_bits.append(f"comfort [{comfort}]")
    if faces and faces != "-":
        anchor_bits.append(f"faces [{faces}]")
    if anchor_bits:
        parts.append("Anchors: " + "; ".join(anchor_bits) + ".")
    # Heuristics
    heur_bits: List[str] = []
    if lead:
        heur_bits.append(f"lead: {lead}")
    if pairing:
        heur_bits.append(f"pair: {pairing}")
    if themes and themes != "-":
        heur_bits.append(f"themes [{themes}]")
    if chamber:
        heur_bits.append(f"chamber: {chamber}")
    if slow_burn:
        heur_bits.append(f"slow-burn: {slow_burn}")
    if exposition:
        heur_bits.append(f"exposition: {exposition}")
    if couple_first is not None:
        heur_bits.append(f"couple-first: {'yes' if couple_first else 'no'}")
    if zero_spoilers is not None:
        heur_bits.append(f"zero-spoilers: {'yes' if zero_spoilers else 'no'}")
    if max_options is not None:
        heur_bits.append(f"options: {max_options}")
    if heur_bits:
        parts.append("Heuristics: " + "; ".join(heur_bits) + ".")
    # Curiosities
    cur_bits: List[str] = []
    if vibes_tonight and vibes_tonight != "-":
        cur_bits.append(f"vibes tonight [{vibes_tonight}]")
    if themes_soon and themes_soon != "-":
        cur_bits.append(f"themes soon [{themes_soon}]")
    if cur_bits:
        parts.append("Curiosities: " + "; ".join(cur_bits) + ".")
    if anti and anti != "-":
        parts.append(f"Anti-prefs: [{anti}].")
    if never_titles and never_titles != "-":
        parts.append(f"Never recommend: titles [{never_titles}].")

    out = "\n".join(parts)
    # Hard cap to keep context efficient
    if len(out) > 1800:
        out = out[:1797] + "…"
    return out


class PreferencesStore:
    """Async, cached preferences store with deep-merge and path ops."""
    def __init__(self, project_root: Path) -> None:
        self.path = project_root / "data" / "household_preferences.json"
        self._cache: Dict[str, Any] | None = None
        self._mtime: float | None = None
        self._lock = asyncio.Lock()
        self._size: int | None = None

    def _loads(self, data: bytes | str) -> Dict[str, Any]:
        if orjson:
            return orjson.loads(data)  # type: ignore[arg-type]
        return json.loads(data)  # type: ignore[arg-type]

    def _dumps(self, obj: Any) -> bytes:
        if orjson:
            return orjson.dumps(obj, option=orjson.OPT_INDENT_2)
        return json.dumps(obj, indent=2).encode("utf-8")

    async def _read_file(self) -> Dict[str, Any]:
        def _read() -> Dict[str, Any]:
            with open(self.path, "rb") as f:
                raw = f.read()
            return self._loads(raw)
        return await asyncio.to_thread(_read)

    async def _write_file(self, data: Dict[str, Any]) -> None:
        def _write() -> None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "wb") as f:
                f.write(self._dumps(data))
        await asyncio.to_thread(_write)

    async def load(self) -> Dict[str, Any]:
        async with self._lock:
            try:
                st = os.stat(self.path)
                mtime = st.st_mtime
                size = st.st_size
            except FileNotFoundError:
                self._cache = {}
                self._mtime = None
                self._size = None
                return {}

            # Re-read if cache missing or file characteristics changed
            if self._cache is None or self._mtime != mtime or self._size != size:
                self._cache = await self._read_file()
                self._mtime = mtime
                self._size = size
            return self._cache

    async def save(self, data: Dict[str, Any]) -> None:
        async with self._lock:
            await self._write_file(data)
            try:
                st = os.stat(self.path)
                self._mtime = st.st_mtime
                self._size = st.st_size
            except FileNotFoundError:
                self._mtime = None
                self._size = None
            self._cache = data

    def _ensure_container_for_path(self, data: Dict[str, Any], parts: List[str]) -> Dict[str, Any]:
        cur: Any = data
        for p in parts[:-1]:
            if not isinstance(cur, dict):
                return data
            if p not in cur or not isinstance(cur[p], (dict, list)):
                cur[p] = {}
            cur = cur[p]
        return data

    def _get_by_path(self, data: Dict[str, Any], dotted_path: str) -> Any:
        cur: Any = data
        for part in dotted_path.split('.'):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return None
        return cur

    def _set_by_path(self, data: Dict[str, Any], dotted_path: str, value: Any) -> Dict[str, Any]:
        parts = dotted_path.split('.')
        self._ensure_container_for_path(data, parts)
        cur: Any = data
        for p in parts[:-1]:
            cur = cur[p]
        cur[parts[-1]] = value
        return data

    def _list_append(self, data: Dict[str, Any], dotted_path: str, value: Any) -> Dict[str, Any]:
        parts = dotted_path.split('.')
        self._ensure_container_for_path(data, parts)
        cur: Any = data
        for p in parts[:-1]:
            cur = cur[p]
        lst = cur.get(parts[-1])
        if lst is None:
            cur[parts[-1]] = [value]
            return data
        if not isinstance(lst, list):
            raise ValueError(f"Path '{dotted_path}' is not a list")
        if value not in lst:
            lst.append(value)
        return data

    def _list_remove_value(self, data: Dict[str, Any], dotted_path: str, value: Any) -> Dict[str, Any]:
        cur = self._get_by_path(data, dotted_path)
        if not isinstance(cur, list):
            raise ValueError(f"Path '{dotted_path}' is not a list")
        try:
            cur.remove(value)
        except ValueError:
            pass
        return data

    def _deep_merge(self, base: Any, patch: Any) -> Any:
        if isinstance(base, dict) and isinstance(patch, dict):
            for k, v in patch.items():
                if k in base:
                    base[k] = self._deep_merge(base[k], v)
                else:
                    base[k] = v
            return base
        return patch


def make_read_household_preferences(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    store = PreferencesStore(project_root)
    async def impl(args: dict) -> dict:
        data = await store.load()

        keys = args.get("keys")
        jpath = args.get("path")
        compact = bool(args.get("compact", False))
        if jpath:
            # Simple dotted path navigation
            cur: Any = data
            for part in str(jpath).split("."):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    cur = None
                    break
            return {"path": jpath, "value": cur}
        if keys:
            return {k: data.get(k) for k in keys}
        if compact:
            try:
                context = build_preferences_context(data)
            except Exception:
                # Fallback to a simple flattened string if formatting fails
                flat = _flatten(data)
                context = "; ".join(f"{k}: {v}" for k, v in flat[:100])
            return {"compact": context}
        return data

    return impl


def make_update_household_preferences(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    store = PreferencesStore(project_root)
    async def impl(args: dict) -> dict:
        # Supports: patch (deep merge), path+value (set), append/remove_value for lists, and json patch ops
        patch = args.get("patch")
        dotted_path = args.get("path")
        value: Any = args.get("value")
        append = args.get("append")
        remove_value = args.get("remove_value")
        ops = args.get("ops")

        # Allow stringified JSON value to be parsed
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except Exception:
                pass
        if isinstance(append, str):
            try:
                append = json.loads(append)
            except Exception:
                pass
        if isinstance(remove_value, str):
            try:
                remove_value = json.loads(remove_value)
            except Exception:
                pass

        data = await store.load()

        if ops:
            # Minimal JSON Patch support: add, replace, remove
            if not isinstance(ops, list):
                raise ValueError("ops must be a list of JSON patch operations")
            for op in ops:
                if not isinstance(op, dict):
                    continue
                operation = op.get("op")
                path_str = op.get("path", "").lstrip("/").replace("/", ".")
                if operation in ("add", "replace"):
                    val = op.get("value")
                    data = store._set_by_path(data, path_str, val)
                elif operation == "remove":
                    parts = path_str.split('.')
                    cur: Any = data
                    for p in parts[:-1]:
                        if isinstance(cur, dict) and p in cur:
                            cur = cur[p]
                        else:
                            cur = None
                            break
                    if isinstance(cur, dict):
                        cur.pop(parts[-1], None)
            await store.save(data)
            return {"ok": True}

        if dotted_path is not None:
            if append is not None and remove_value is not None:
                raise ValueError("Specify only one of append or remove_value")
            if append is not None:
                data = store._list_append(data, dotted_path, append)
            elif remove_value is not None:
                data = store._list_remove_value(data, dotted_path, remove_value)
            else:
                data = store._set_by_path(data, dotted_path, value)
            await store.save(data)
            return {"ok": True}

        if patch is not None:
            if not isinstance(patch, dict):
                raise ValueError("patch must be an object")
            merged = store._deep_merge(data or {}, patch)
            await store.save(merged)
            return {"ok": True}

        raise ValueError("No valid update parameters provided")

    return impl


def make_search_household_preferences(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        query = str(args.get("query", "")).strip().lower()
        limit = int(args.get("limit", 10))
        path = project_root / "data" / "household_preferences.json"
        try:
            def _read():
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            data = await asyncio.to_thread(_read)
        except FileNotFoundError:
            return {"matches": []}
        flat = _flatten(data)
        matches = [(k, v) for k, v in flat if query in k.lower() or query in v.lower()]
        out = [{"path": k, "value": v} for k, v in matches[:limit]]
        return {"matches": out}

    return impl


def make_query_household_preferences(project_root: Path, llm_client) -> Callable[[dict], Awaitable[dict]]:
    """Query household preferences using available LLM and return a concise one-sentence response."""
    async def impl(args: dict) -> dict:
        query = str(args.get("query", "")).strip()
        if not query:
            return {"error": "Query is required"}
        
        path = project_root / "data" / "household_preferences.json"
        try:
            def _read():
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            data = await asyncio.to_thread(_read)
        except FileNotFoundError:
            return {"error": "Household preferences not found"}
        
        # Build the compact summary
        try:
            compact = build_preferences_context(data)
        except Exception:
            # Fallback to a simple flattened string if formatting fails
            flat = _flatten(data)
            compact = "; ".join(f"{k}: {v}" for k, v in flat[:100])
        
        # Choose model and selection from config
        from config.loader import resolve_llm_selection
        _, sel = resolve_llm_selection(project_root, "worker")
        model = sel.get("model", "gpt-5-nano")
        
        # Prepare the prompt for the selected model
        system_message = {
            "role": "system",
            "content": "You are a helpful assistant that answers questions about household movie preferences. Based on the preferences provided, answer the user's question in exactly one sentence. Be concise and specific. Do not include explanations or additional context - just the direct answer."
        }
        
        user_message = {
            "role": "user", 
            "content": f"Preferences: {compact}\n\nQuestion: {query}\n\nAnswer in one sentence:"
        }
        
        try:
            # Call the async LLM client
            response = await llm_client.achat(
                model=model,
                messages=[system_message, user_message],
                reasoning=sel.get("reasoningEffort"),
                **(sel.get("params", {}) or {}),
            )
            print(response)
            # Extract the response content
            content = response.choices[0].message.content or ""
            # Clean up and ensure it's just one sentence
            content = content.strip()
            if content.endswith('.'):
                content = content[:-1]
            
            return {"answer": content}
            
        except Exception as e:
            return {"error": f"Failed to query preferences: {str(e)}"}

    return impl


def make_get_plex_library_sections(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        settings = load_settings(project_root)
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        sections = await asyncio.to_thread(plex.get_library_sections)
        return {"sections": sections}

    return impl


def make_get_plex_recently_added(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        section_type = str(args.get("section_type", "movie")).lower()
        limit = int(args.get("limit", 20))
        response_level = ResponseLevel(args.get("response_level", "compact")) if args.get("response_level") else None
        settings = load_settings(project_root)
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        items = await asyncio.to_thread(plex.get_recently_added, section_type, limit, response_level)
        return {
            "items": items,
            "section_type": section_type,
            "limit": limit,
            "total_found": len(items),
            "response_level": response_level.value if response_level else "compact"
        }

    return impl


def make_get_plex_on_deck(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        limit = int(args.get("limit", 20))
        response_level = ResponseLevel(args.get("response_level", "compact")) if args.get("response_level") else None
        settings = load_settings(project_root)
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        items = await asyncio.to_thread(plex.get_on_deck, limit, response_level)
        return {
            "items": items,
            "limit": limit,
            "total_found": len(items),
            "response_level": response_level.value if response_level else "compact"
        }

    return impl


def make_get_plex_continue_watching(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        limit = int(args.get("limit", 20))
        response_level = ResponseLevel(args.get("response_level", "compact")) if args.get("response_level") else None
        settings = load_settings(project_root)
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        items = await asyncio.to_thread(plex.get_continue_watching, limit, response_level)
        return {
            "items": items,
            "limit": limit,
            "total_found": len(items),
            "response_level": response_level.value if response_level else "compact"
        }

    return impl


def make_get_plex_unwatched(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        section_type = str(args.get("section_type", "movie")).lower()
        limit = int(args.get("limit", 20))
        response_level = ResponseLevel(args.get("response_level", "compact")) if args.get("response_level") else None
        settings = load_settings(project_root)
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        items = await asyncio.to_thread(plex.get_unwatched, section_type, limit, response_level)
        return {
            "items": items,
            "section_type": section_type,
            "limit": limit,
            "total_found": len(items),
            "response_level": response_level.value if response_level else "compact"
        }

    return impl


def make_get_plex_collections(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        section_type = str(args.get("section_type", "movie")).lower()
        limit = int(args.get("limit", 50))
        response_level = ResponseLevel(args.get("response_level", "compact")) if args.get("response_level") else None
        settings = load_settings(project_root)
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        collections = await asyncio.to_thread(plex.get_collections, section_type, limit, response_level)
        return {
            "collections": collections,
            "section_type": section_type,
            "limit": limit,
            "total_found": len(collections),
            "response_level": response_level.value if response_level else "compact"
        }

    return impl


def make_get_plex_playlists(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        limit = int(args.get("limit", 50))
        response_level = ResponseLevel(args.get("response_level", "compact")) if args.get("response_level") else None
        settings = load_settings(project_root)
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        playlists = await asyncio.to_thread(plex.get_playlists, limit, response_level)
        return {
            "playlists": playlists,
            "limit": limit,
            "total_found": len(playlists),
            "response_level": response_level.value if response_level else "compact"
        }

    return impl


def make_get_plex_similar_items(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        rating_key = int(args["rating_key"])
        limit = int(args.get("limit", 10))
        response_level = ResponseLevel(args.get("response_level", "compact")) if args.get("response_level") else None
        settings = load_settings(project_root)
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        items = await asyncio.to_thread(plex.get_similar_items, rating_key, limit, response_level)
        return {
            "items": items,
            "rating_key": rating_key,
            "limit": limit,
            "total_found": len(items),
            "response_level": response_level.value if response_level else "compact"
        }

    return impl


def make_get_plex_extras(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        rating_key = int(args["rating_key"])
        settings = load_settings(project_root)
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        extras = await asyncio.to_thread(plex.get_extras, rating_key)
        return {
            "extras": extras,
            "rating_key": rating_key,
            "total_found": len(extras)
        }

    return impl


def make_get_plex_playback_status(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        response_level = ResponseLevel(args.get("response_level", "compact")) if args.get("response_level") else None
        settings = load_settings(project_root)
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        status = await asyncio.to_thread(plex.get_playback_status, response_level)
        return {
            **status,
            "response_level": response_level.value if response_level else "compact"
        }

    return impl


def make_get_plex_watch_history(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        rating_key = int(args["rating_key"])
        limit = int(args.get("limit", 20))
        settings = load_settings(project_root)
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        history = await asyncio.to_thread(plex.get_watch_history, rating_key, limit)
        return {
            "history": history,
            "rating_key": rating_key,
            "limit": limit,
            "total_found": len(history)
        }

    return impl


def make_get_plex_item_details(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        rating_key = int(args["rating_key"])
        response_level = ResponseLevel(args.get("response_level", "detailed")) if args.get("response_level") else None
        settings = load_settings(project_root)
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        item = await asyncio.to_thread(plex.get_item_details, rating_key, response_level)
        if item:
            return {
                "item": item,
                "response_level": response_level.value if response_level else "detailed"
            }
        else:
            return {"error": "Item not found", "rating_key": rating_key}

    return impl


def make_sonarr_search_episode(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        episode_id = int(args["episode_id"])
        settings = load_settings(project_root)
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        data = await sonarr.search_episode(episode_id)
        await sonarr.close()
        return {"episode_search_command": data}


def make_sonarr_search_episodes(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        episode_ids = [int(id) for id in args["episode_ids"]]
        settings = load_settings(project_root)
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        data = await sonarr.search_episodes(episode_ids)
        await sonarr.close()
        return {"episodes_search_command": data}

    return impl


