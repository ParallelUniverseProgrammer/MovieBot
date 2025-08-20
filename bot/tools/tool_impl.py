from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Tuple

from config.loader import load_settings, load_runtime_config
from integrations.plex_client import PlexClient
from integrations.tmdb_client import TMDbClient
from integrations.radarr_client import RadarrClient
from integrations.sonarr_client import SonarrClient


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
        
        settings = load_settings(project_root)
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        
        # Get all movies if no query, otherwise search
        if query:
            results = plex.search_movies(query)
        else:
            # Get all movies from the library
            movie_library = plex.plex.library.section("Movies")
            results = movie_library.all()
        
        # Apply filters
        filtered_results = []
        for movie in results:
            if _matches_filters(movie, year_min, year_max, genres, actors, directors, 
                              content_rating, rating_min, rating_max):
                filtered_results.append(movie)
        
        # Sort results
        filtered_results = _sort_movies(filtered_results, sort_by, sort_order)
        
        # Apply limit
        filtered_results = filtered_results[:limit]
        
        # Extract metadata
        items = []
        for movie in filtered_results:
            item = {
                "title": getattr(movie, "title", None),
                "year": getattr(movie, "year", None),
                "ratingKey": getattr(movie, "ratingKey", None),
                "rating": getattr(movie, "rating", None),
                "contentRating": getattr(movie, "contentRating", None),
                "duration": getattr(movie, "duration", None),
                "genres": [genre.tag for genre in getattr(movie, "genres", [])] if hasattr(movie, "genres") else [],
                "actors": [actor.tag for actor in getattr(movie, "actors", [])] if hasattr(movie, "actors") else [],
                "directors": [director.tag for director in getattr(movie, "directors", [])] if hasattr(movie, "directors") else [],
                "summary": getattr(movie, "summary", None),
                "tagline": getattr(movie, "tagline", None),
                "studio": getattr(movie, "studio", None),
                "addedAt": _serialize_datetime(getattr(movie, "addedAt", None)),
                "updatedAt": _serialize_datetime(getattr(movie, "updatedAt", None)),
            }
            items.append(item)
        
        return {
            "items": items,
            "total_found": len(filtered_results),
            "filters_applied": filters,
            "query": query
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
    
    # Year filtering
    if year_min is not None and getattr(movie, "year", 0) < year_min:
        return False
    if year_max is not None and getattr(movie, "year", 9999) > year_max:
        return False
    
    # Genre filtering (any genre match is sufficient)
    if genres:
        movie_genres = [genre.tag.lower() for genre in getattr(movie, "genres", [])]
        if not any(genre.lower() in movie_genres for genre in genres):
            return False
    
    # Actor filtering (any actor match is sufficient)
    if actors:
        movie_actors = [actor.tag.lower() for actor in getattr(movie, "actors", [])]
        if not any(actor.lower() in movie_actors for actor in actors):
            return False
    
    # Director filtering (any director match is sufficient)
    if directors:
        movie_directors = [director.tag.lower() for director in getattr(movie, "directors", [])]
        if not any(director.lower() in movie_directors for director in directors):
            return False
    
    # Content rating filtering
    if content_rating and getattr(movie, "contentRating", "") != content_rating:
        return False
    
    # Rating filtering
    if rating_min is not None and getattr(movie, "rating", 0) < rating_min:
        return False
    if rating_max is not None and getattr(movie, "rating", 10) > rating_max:
        return False
    
    return True


def _sort_movies(movies, sort_by, sort_order):
    """Sort movies by the specified attribute and order."""
    reverse = sort_order.lower() == "desc"
    
    def get_sort_key(movie):
        value = getattr(movie, sort_by, None)
        if value is None:
            return "" if sort_order.lower() == "asc" else "zzzzz"
        return value
    
    try:
        return sorted(movies, key=get_sort_key, reverse=reverse)
    except (TypeError, AttributeError):
        # Fallback to title sorting if the specified sort_by fails
        return sorted(movies, key=lambda m: getattr(m, "title", ""), reverse=reverse)


def make_set_plex_rating(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        rating_key = int(args["rating_key"])  # raises if missing
        rating = int(args["rating"])  # raises if missing
        settings = load_settings(project_root)
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        plex.set_rating(rating_key, rating)
        return {"ok": True}

    return impl


def make_tmdb_search(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        query = str(args.get("query", "")).strip()
        year = args.get("year")
        primary_release_year = args.get("primary_release_year")
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.search_movie(query, year, primary_release_year, language, page)
        await tmdb.close()
        return data

    return impl


def make_tmdb_recommendations(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        tmdb_id = int(args["tmdb_id"])  # raises if missing
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.recommendations(tmdb_id, language, page)
        await tmdb.close()
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
            page=page
        )
        await tmdb.close()
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
            page=page
        )
        await tmdb.close()
        return data

    return impl


def make_tmdb_trending(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get trending movies, TV shows, or people"""
    async def impl(args: dict) -> dict:
        media_type = str(args.get("media_type", "all"))  # all, movie, tv, person
        time_window = str(args.get("time_window", "week"))  # day, week
        language = str(args.get("language", "en-US"))
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.trending(media_type, time_window, language)
        await tmdb.close()
        return data

    return impl


def make_tmdb_popular_movies(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get popular movies"""
    async def impl(args: dict) -> dict:
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.popular_movies(language, page)
        await tmdb.close()
        return data

    return impl


def make_tmdb_top_rated_movies(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get top rated movies"""
    async def impl(args: dict) -> dict:
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.top_rated_movies(language, page)
        await tmdb.close()
        return data

    return impl


def make_tmdb_upcoming_movies(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get upcoming movie releases"""
    async def impl(args: dict) -> dict:
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.upcoming_movies(language, page)
        await tmdb.close()
        return data

    return impl


def make_tmdb_now_playing_movies(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get movies currently in theaters"""
    async def impl(args: dict) -> dict:
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.now_playing_movies(language, page)
        await tmdb.close()
        return data

    return impl


def make_tmdb_popular_tv(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get popular TV series"""
    async def impl(args: dict) -> dict:
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.popular_tv(language, page)
        await tmdb.close()
        return data

    return impl


def make_tmdb_top_rated_tv(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get top rated TV series"""
    async def impl(args: dict) -> dict:
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.top_rated_tv(language, page)
        await tmdb.close()
        return data

    return impl


def make_tmdb_on_the_air_tv(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get TV series currently on the air"""
    async def impl(args: dict) -> dict:
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.on_the_air_tv(language, page)
        await tmdb.close()
        return data

    return impl


def make_tmdb_airing_today_tv(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get TV series airing today"""
    async def impl(args: dict) -> dict:
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.airing_today_tv(language, page)
        await tmdb.close()
        return data

    return impl


def make_tmdb_movie_details(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get comprehensive movie details including credits, videos, images"""
    async def impl(args: dict) -> dict:
        movie_id = int(args["movie_id"])
        language = str(args.get("language", "en-US"))
        append_to_response = args.get("append_to_response")  # e.g., "credits,videos,images"
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.movie_details(movie_id, language, append_to_response)
        await tmdb.close()
        return data

    return impl


def make_tmdb_tv_details(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get comprehensive TV series details"""
    async def impl(args: dict) -> dict:
        tv_id = int(args["tv_id"])
        language = str(args.get("language", "en-US"))
        append_to_response = args.get("append_to_response")  # e.g., "credits,videos,images"
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.tv_details(tv_id, language, append_to_response)
        await tmdb.close()
        return data

    return impl


def make_tmdb_similar_movies(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get similar movies to a specific movie"""
    async def impl(args: dict) -> dict:
        movie_id = int(args["movie_id"])
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.similar_movies(movie_id, language, page)
        await tmdb.close()
        return data

    return impl


def make_tmdb_similar_tv(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Get similar TV series to a specific series"""
    async def impl(args: dict) -> dict:
        tv_id = int(args["tv_id"])
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.similar_tv(tv_id, language, page)
        await tmdb.close()
        return data

    return impl


def make_tmdb_search_tv(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Search for TV series"""
    async def impl(args: dict) -> dict:
        query = str(args.get("query", "")).strip()
        first_air_date_year = args.get("first_air_date_year")
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.search_tv(query, first_air_date_year, language, page)
        await tmdb.close()
        return data

    return impl


def make_tmdb_search_multi(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Search across movies, TV shows, and people"""
    async def impl(args: dict) -> dict:
        query = str(args.get("query", "")).strip()
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.search_multi(query, language, page)
        await tmdb.close()
        return data

    return impl


def make_tmdb_search_person(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Search for people (actors, directors, etc.)"""
    async def impl(args: dict) -> dict:
        query = str(args.get("query", "")).strip()
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        
        settings = load_settings(project_root)
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.search_person(query, language, page)
        await tmdb.close()
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
        await tmdb.close()
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
        await tmdb.close()
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
        await tmdb.close()
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
        await tmdb.close()
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
        data = await sonarr.add_series(
            tvdb_id=int(args["tvdb_id"]),
            quality_profile_id=int(args.get("quality_profile_id") or config.get("sonarr", {}).get("qualityProfileId")),
            root_folder_path=str(args.get("root_folder_path") or config.get("sonarr", {}).get("rootFolderPath")),
            monitored=bool(args.get("monitored", True)),
            search_for_missing=bool(args.get("search_for_missing", True)),
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


def _join(values: List[str], *, empty: str = "-") -> str:
    return ", ".join(values) if values else empty


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
    like_genres = _join(_as_list(likes.get("genres")))
    like_people = _join(_as_list(likes.get("people")))
    like_vibes = _join(_as_list(likes.get("vibes")))
    like_aesthetics = _join(_as_list(likes.get("aesthetics")))
    like_motifs = _join(_as_list(likes.get("motifs")))

    dislike_genres = _join(_as_list(dislikes.get("genres")))
    dislike_aesthetics = _join(_as_list(dislikes.get("aesthetics")))
    dislike_tones = _join(_as_list(dislikes.get("tones")))
    dislike_structure = _join(_as_list(dislikes.get("structure")))
    dislike_vibes = _join(_as_list(dislikes.get("vibes")))

    # Constraints
    era_min = constraints.get("eraMinYear")
    lang_whitelist = _join(_as_list(_pick(constraints, "languageWhitelist", "languages")))
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
    loved = _join(_as_list(anchors.get("loved")))
    responded = _join(_as_list(_pick(anchors, "respondedTo", "responded")))
    comfort = _join(_as_list(anchors.get("comfortSignals")))
    faces = _join(_as_list(_pick(anchors, "trustedFaces", "faces")))

    # Heuristics
    lead = heuristics.get("lead")
    pairing = heuristics.get("pairing")
    themes = _join(_as_list(heuristics.get("themes")))
    chamber = heuristics.get("chamber")
    slow_burn = heuristics.get("slowBurn")
    exposition = heuristics.get("exposition")
    couple_first = heuristics.get("coupleFirst")
    zero_spoilers = heuristics.get("zeroSpoilers")
    max_options = heuristics.get("maxOptions")

    # Curiosities
    vibes_tonight = _join(_as_list(_pick(curiosities, "vibesTonight", "vibes")))
    themes_soon = _join(_as_list(_pick(curiosities, "themesSoon", "themes")))

    anti = _join(_as_list(data.get("antiPreferences")))
    never_titles = _join(_as_list(data.get("neverRecommend", {}).get("titles")))

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

    return "\n".join(parts)


def make_read_household_preferences(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        path = project_root / "data" / "household_preferences.json"
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {}

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
    async def impl(args: dict) -> dict:
        patch = args.get("patch", {})
        path = project_root / "data" / "household_preferences.json"
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {}
        if not isinstance(patch, dict):
            raise ValueError("patch must be an object")
        data.update(patch)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return {"ok": True}

    return impl


def make_search_household_preferences(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        query = str(args.get("query", "")).strip().lower()
        limit = int(args.get("limit", 10))
        path = project_root / "data" / "household_preferences.json"
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return {"matches": []}
        flat = _flatten(data)
        matches = [(k, v) for k, v in flat if query in k.lower() or query in v.lower()]
        out = [{"path": k, "value": v} for k, v in matches[:limit]]
        return {"matches": out}

    return impl


def make_query_household_preferences(project_root: Path, llm_client) -> Callable[[dict], Awaitable[dict]]:
    """Query household preferences using GPT-5-nano and return a concise one-sentence response."""
    async def impl(args: dict) -> dict:
        query = str(args.get("query", "")).strip()
        if not query:
            return {"error": "Query is required"}
        
        path = project_root / "data" / "household_preferences.json"
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return {"error": "Household preferences not found"}
        
        # Build the compact summary
        try:
            compact = build_preferences_context(data)
        except Exception:
            # Fallback to a simple flattened string if formatting fails
            flat = _flatten(data)
            compact = "; ".join(f"{k}: {v}" for k, v in flat[:100])
        
        # Prepare the prompt for GPT-5-nano
        system_message = {
            "role": "system",
            "content": "You are a helpful assistant that answers questions about household movie preferences. Based on the preferences provided, answer the user's question in exactly one sentence. Be concise and specific. Do not include explanations or additional context - just the direct answer."
        }
        
        user_message = {
            "role": "user", 
            "content": f"Preferences: {compact}\n\nQuestion: {query}\n\nAnswer in one sentence:"
        }
        
        try:
            # Call the synchronous LLM client
            response = llm_client.chat(
                model="gpt-5-nano",
                messages=[system_message, user_message],
                temperature=1,   # Limit to ensure single sentence
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
        sections = plex.get_library_sections()
        return {"sections": sections}

    return impl


def make_get_plex_recently_added(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        section_type = str(args.get("section_type", "movie")).lower()
        limit = int(args.get("limit", 20))
        settings = load_settings(project_root)
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        items = plex.get_recently_added(section_type, limit)
        return {
            "items": items,
            "section_type": section_type,
            "limit": limit,
            "total_found": len(items)
        }

    return impl


def make_get_plex_on_deck(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        limit = int(args.get("limit", 20))
        settings = load_settings(project_root)
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        items = plex.get_on_deck(limit)
        return {
            "items": items,
            "limit": limit,
            "total_found": len(items)
        }

    return impl


def make_get_plex_continue_watching(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        limit = int(args.get("limit", 20))
        settings = load_settings(project_root)
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        items = plex.get_continue_watching(limit)
        return {
            "items": items,
            "limit": limit,
            "total_found": len(items)
        }

    return impl


def make_get_plex_unwatched(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        section_type = str(args.get("section_type", "movie")).lower()
        limit = int(args.get("limit", 20))
        settings = load_settings(project_root)
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        items = plex.get_unwatched(section_type, limit)
        return {
            "items": items,
            "section_type": section_type,
            "limit": limit,
            "total_found": len(items)
        }

    return impl


def make_get_plex_collections(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        section_type = str(args.get("section_type", "movie")).lower()
        limit = int(args.get("limit", 50))
        settings = load_settings(project_root)
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        collections = plex.get_collections(section_type, limit)
        return {
            "collections": collections,
            "section_type": section_type,
            "limit": limit,
            "total_found": len(collections)
        }

    return impl


def make_get_plex_playlists(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        limit = int(args.get("limit", 50))
        settings = load_settings(project_root)
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        playlists = plex.get_playlists(limit)
        return {
            "playlists": playlists,
            "limit": limit,
            "total_found": len(playlists)
        }

    return impl


def make_get_plex_similar_items(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        rating_key = int(args["rating_key"])
        limit = int(args.get("limit", 10))
        settings = load_settings(project_root)
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        items = plex.get_similar_items(rating_key, limit)
        return {
            "items": items,
            "rating_key": rating_key,
            "limit": limit,
            "total_found": len(items)
        }

    return impl


def make_get_plex_extras(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        rating_key = int(args["rating_key"])
        settings = load_settings(project_root)
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        extras = plex.get_extras(rating_key)
        return {
            "extras": extras,
            "rating_key": rating_key,
            "total_found": len(extras)
        }

    return impl


def make_get_plex_playback_status(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        settings = load_settings(project_root)
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        status = plex.get_playback_status()
        return status

    return impl


def make_get_plex_watch_history(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    async def impl(args: dict) -> dict:
        rating_key = int(args["rating_key"])
        limit = int(args.get("limit", 20))
        settings = load_settings(project_root)
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        history = plex.get_watch_history(rating_key, limit)
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
        settings = load_settings(project_root)
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        item = plex.get_item_details(rating_key)
        if item:
            return {"item": item}
        else:
            return {"error": "Item not found", "rating_key": rating_key}

    return impl


