from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable, Dict

from bot.workers.tmdb import TMDbWorker


def make_tmdb_search(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = TMDbWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.search_movie(
            query=str(args.get("query", "")).strip(),
            year=args.get("year"),
            primary_release_year=args.get("primary_release_year"),
            language=str(args.get("language", "en-US")),
            page=int(args.get("page", 1)),
            response_level=args.get("response_level"),
            include_details=args.get("include_details", True),  # Default to True for unified behavior
            max_details=args.get("max_details", 5),
        )

    return impl


def make_tmdb_recommendations(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = TMDbWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.recommendations(
            tmdb_id=int(args["tmdb_id"]),
            language=str(args.get("language", "en-US")),
            page=int(args.get("page", 1)),
            response_level=args.get("response_level"),
        )

    return impl


def make_tmdb_discover_movies(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = TMDbWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.discover_movies(
            sort_by=str(args.get("sort_by", "popularity.desc")),
            year=args.get("year"),
            primary_release_year=args.get("primary_release_year"),
            with_genres=args.get("with_genres"),
            without_genres=args.get("without_genres"),
            with_cast=args.get("with_cast"),
            with_crew=args.get("with_crew"),
            with_keywords=args.get("with_keywords"),
            with_runtime_gte=args.get("with_runtime_gte"),
            with_runtime_lte=args.get("with_runtime_lte"),
            with_original_language=args.get("with_original_language"),
            language=str(args.get("language", "en-US")),
            page=int(args.get("page", 1)),
            response_level=args.get("response_level"),
        )

    return impl


def make_tmdb_discover_tv(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = TMDbWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.discover_tv(
            sort_by=str(args.get("sort_by", "popularity.desc")),
            first_air_date_year=args.get("first_air_date_year"),
            with_genres=args.get("with_genres"),
            without_genres=args.get("without_genres"),
            with_cast=args.get("with_cast"),
            with_crew=args.get("with_crew"),
            with_keywords=args.get("with_keywords"),
            with_runtime_gte=args.get("with_runtime_gte"),
            with_runtime_lte=args.get("with_runtime_lte"),
            with_original_language=args.get("with_original_language"),
            language=str(args.get("language", "en-US")),
            page=int(args.get("page", 1)),
            response_level=args.get("response_level"),
        )

    return impl


def make_tmdb_trending(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = TMDbWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.trending(
            media_type=str(args.get("media_type", "all")),
            time_window=str(args.get("time_window", "week")),
            language=str(args.get("language", "en-US")),
            response_level=args.get("response_level"),
        )

    return impl


def make_tmdb_popular_movies(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = TMDbWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.popular_movies(
            language=str(args.get("language", "en-US")),
            page=int(args.get("page", 1)),
            response_level=args.get("response_level"),
        )

    return impl


def make_tmdb_top_rated_movies(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = TMDbWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.top_rated_movies(
            language=str(args.get("language", "en-US")),
            page=int(args.get("page", 1)),
            response_level=args.get("response_level"),
        )

    return impl


def make_tmdb_upcoming_movies(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = TMDbWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.upcoming_movies(
            language=str(args.get("language", "en-US")),
            page=int(args.get("page", 1)),
            response_level=args.get("response_level"),
        )

    return impl


def make_tmdb_now_playing_movies(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = TMDbWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.now_playing_movies(
            language=str(args.get("language", "en-US")),
            page=int(args.get("page", 1)),
            response_level=args.get("response_level"),
        )

    return impl


def make_tmdb_popular_tv(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = TMDbWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.popular_tv(
            language=str(args.get("language", "en-US")),
            page=int(args.get("page", 1)),
            response_level=args.get("response_level"),
        )

    return impl


def make_tmdb_top_rated_tv(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = TMDbWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.top_rated_tv(
            language=str(args.get("language", "en-US")),
            page=int(args.get("page", 1)),
            response_level=args.get("response_level"),
        )

    return impl


def make_tmdb_on_the_air_tv(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = TMDbWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.on_the_air_tv(
            language=str(args.get("language", "en-US")),
            page=int(args.get("page", 1)),
            response_level=args.get("response_level"),
        )

    return impl


def make_tmdb_airing_today_tv(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = TMDbWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.airing_today_tv(
            language=str(args.get("language", "en-US")),
            page=int(args.get("page", 1)),
            response_level=args.get("response_level"),
        )

    return impl


def make_tmdb_movie_details(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = TMDbWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.movie_details(
            movie_id=int(args["movie_id"]),
            language=str(args.get("language", "en-US")),
            append_to_response=args.get("append_to_response"),
            response_level=args.get("response_level"),
        )

    return impl


def make_tmdb_tv_details(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = TMDbWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.tv_details(
            tv_id=int(args["tv_id"]),
            language=str(args.get("language", "en-US")),
            append_to_response=args.get("append_to_response"),
            response_level=args.get("response_level"),
        )

    return impl


def make_tmdb_similar_movies(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = TMDbWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.similar_movies(
            movie_id=int(args["movie_id"]),
            language=str(args.get("language", "en-US")),
            page=int(args.get("page", 1)),
            response_level=args.get("response_level"),
        )

    return impl


def make_tmdb_similar_tv(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = TMDbWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.similar_tv(
            tv_id=int(args["tv_id"]),
            language=str(args.get("language", "en-US")),
            page=int(args.get("page", 1)),
            response_level=args.get("response_level"),
        )

    return impl


def make_tmdb_search_tv(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = TMDbWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.search_tv(
            query=str(args.get("query", "")).strip(),
            first_air_date_year=args.get("first_air_date_year"),
            language=str(args.get("language", "en-US")),
            page=int(args.get("page", 1)),
            response_level=args.get("response_level"),
        )

    return impl


def make_tmdb_search_multi(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = TMDbWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.search_multi(
            query=str(args.get("query", "")).strip(),
            language=str(args.get("language", "en-US")),
            page=int(args.get("page", 1)),
            response_level=args.get("response_level"),
        )

    return impl


def make_tmdb_search_person(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = TMDbWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.search_person(
            query=str(args.get("query", "")).strip(),
            language=str(args.get("language", "en-US")),
            page=int(args.get("page", 1)),
            response_level=args.get("response_level"),
        )

    return impl


def make_tmdb_genres(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = TMDbWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.genres(
            media_type=str(args.get("media_type", "movie")),
            language=str(args.get("language", "en-US")),
        )

    return impl


def make_tmdb_collection_details(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = TMDbWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.collection_details(
            collection_id=int(args["collection_id"]),
            language=str(args.get("language", "en-US")),
        )

    return impl


def make_tmdb_watch_providers_movie(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = TMDbWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.watch_providers_movie(
            movie_id=int(args["movie_id"]),
            language=str(args.get("language", "en-US")),
        )

    return impl


def make_tmdb_watch_providers_tv(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = TMDbWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.watch_providers_tv(
            tv_id=int(args["tv_id"]),
            language=str(args.get("language", "en-US")),
        )

    return impl


def make_tmdb_discovery_suite(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Bundled tool that provides comprehensive TMDb discovery across multiple methods in parallel."""
    worker = TMDbWorker(project_root)

    async def impl(args: dict) -> dict:
        import asyncio
        
        # Extract common parameters
        language = str(args.get("language", "en-US"))
        page = int(args.get("page", 1))
        response_level = args.get("response_level")
        
        # Get discovery types to include (default to all)
        discovery_types = args.get("discovery_types", ["trending", "popular", "top_rated", "discover"])
        
        # Build tasks based on requested discovery types
        tasks = []
        task_names = []
        
        if "trending" in discovery_types:
            tasks.extend([
                worker.trending(media_type="movie", time_window="week", language=language, response_level=response_level),
                worker.trending(media_type="tv", time_window="week", language=language, response_level=response_level),
            ])
            task_names.extend(["trending_movies", "trending_tv"])
        
        if "popular" in discovery_types:
            tasks.extend([
                worker.popular_movies(language=language, page=page, response_level=response_level),
                worker.popular_tv(language=language, page=page, response_level=response_level),
            ])
            task_names.extend(["popular_movies", "popular_tv"])
        
        if "top_rated" in discovery_types:
            tasks.extend([
                worker.top_rated_movies(language=language, page=page, response_level=response_level),
                worker.top_rated_tv(language=language, page=page, response_level=response_level),
            ])
            task_names.extend(["top_rated_movies", "top_rated_tv"])
        
        if "discover" in discovery_types:
            # Use basic discover parameters if not specified
            discover_params = {
                "sort_by": str(args.get("sort_by", "popularity.desc")),
                "year": args.get("year"),
                "primary_release_year": args.get("primary_release_year"),
                "first_air_date_year": args.get("first_air_date_year"),
                "with_genres": args.get("with_genres"),
                "without_genres": args.get("without_genres"),
                "with_cast": args.get("with_cast"),
                "with_crew": args.get("with_crew"),
                "with_keywords": args.get("with_keywords"),
                "with_runtime_gte": args.get("with_runtime_gte"),
                "with_runtime_lte": args.get("with_runtime_lte"),
                "with_original_language": args.get("with_original_language"),
                "language": language,
                "page": page,
                "response_level": response_level,
            }
            
            tasks.extend([
                worker.discover_movies(**{k: v for k, v in discover_params.items() if k != "first_air_date_year"}),
                worker.discover_tv(**{k: v for k, v in discover_params.items() if k != "year" and k != "primary_release_year"}),
            ])
            task_names.extend(["discover_movies", "discover_tv"])
        
        if not tasks:
            return {
                "success": False,
                "error": "No discovery types specified",
                "discovery_types": discovery_types,
                "results": {}
            }
        
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results and handle any exceptions
            def safe_result(result, name):
                if isinstance(result, Exception):
                    return {"error": str(result), "name": name, "data": []}
                return result
            
            # Build results dictionary
            results_dict = {}
            for i, (result, name) in enumerate(zip(results, task_names)):
                results_dict[name] = safe_result(result, name)
            
            # Calculate summary statistics
            total_results = 0
            error_count = 0
            for result in results:
                if isinstance(result, Exception):
                    error_count += 1
                else:
                    total_results += len(result.get("results", []))
            
            return {
                "success": True,
                "discovery_types": discovery_types,
                "language": language,
                "page": page,
                "results": results_dict,
                "summary": {
                    "total_discovery_methods": len(tasks),
                    "successful_methods": len(tasks) - error_count,
                    "error_count": error_count,
                    "total_results": total_results,
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to fetch TMDb discovery suite: {str(e)}",
                "discovery_types": discovery_types,
                "results": {}
            }

    return impl


