from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable

from bot.workers.radarr import RadarrWorker
from config.loader import load_settings, load_runtime_config


def make_radarr_lookup(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = RadarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.lookup(str(args.get("term", "")).strip())

    return impl


def make_radarr_add_movie(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = RadarrWorker(project_root)

    async def impl(args: dict) -> dict:
        result = await worker.add_movie(
            tmdb_id=int(args["tmdb_id"]),
            quality_profile_id=args.get("quality_profile_id"),
            root_folder_path=args.get("root_folder_path"),
            monitored=args.get("monitored", True),
            search_now=args.get("search_now", True),
        )
        
        # If movie already exists, return a clear success response
        if result.get("already_exists"):
            return {
                "success": True,
                "already_exists": True,
                "message": result.get("message", "Movie already exists in Radarr"),
                "movie": result.get("movie", {}),
                "tmdb_id": result.get("tmdb_id")
            }
        
        return result

    return impl


def make_radarr_get_movies(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = RadarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_movies(movie_id=args.get("movie_id"))

    return impl


def make_radarr_update_movie(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = RadarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.update_movie(movie_id=int(args["movie_id"]), update_data=args.get("update_data", {}))

    return impl


def make_radarr_delete_movie(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = RadarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.delete_movie(
            movie_id=int(args["movie_id"]),
            delete_files=args.get("delete_files"),
            add_import_list_exclusion=args.get("add_import_list_exclusion"),
        )

    return impl


def make_radarr_search_movie(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = RadarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.search_movie(movie_id=int(args["movie_id"]))

    return impl


def make_radarr_search_missing(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = RadarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.search_missing()

    return impl


def make_radarr_search_cutoff(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = RadarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.search_cutoff()

    return impl


def make_radarr_get_queue(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = RadarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_queue()

    return impl


def make_radarr_get_wanted(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = RadarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_wanted(
            page=int(args.get("page", 1)),
            page_size=int(args.get("page_size", 20)),
            sort_key=str(args.get("sort_key", "releaseDate")),
            sort_dir=str(args.get("sort_dir", "desc")),
        )

    return impl


def make_radarr_get_calendar(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = RadarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_calendar(start_date=args.get("start_date"), end_date=args.get("end_date"))

    return impl


def make_radarr_get_blacklist(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = RadarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_blacklist(page=int(args.get("page", 1)), page_size=int(args.get("page_size", 20)))

    return impl


def make_radarr_clear_blacklist(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = RadarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.clear_blacklist()

    return impl


def make_radarr_system_status(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = RadarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.system_status()

    return impl


def make_radarr_health(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = RadarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.health()

    return impl


def make_radarr_disk_space(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = RadarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.disk_space()

    return impl


def make_radarr_quality_profiles(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = RadarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.quality_profiles()

    return impl


def make_radarr_root_folders(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = RadarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.root_folders()

    return impl


def make_radarr_get_indexers(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = RadarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_indexers()

    return impl


def make_radarr_get_download_clients(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = RadarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_download_clients()

    return impl


def make_radarr_movie_addition_fallback(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Handle movie addition with quality fallback when preferred quality isn't available using sub-agent."""
    async def impl(args: dict) -> dict:
        from bot.sub_agent import SubAgent
        
        tmdb_id = int(args["tmdb_id"])
        movie_title = str(args["movie_title"])
        preferred_quality = args.get("preferred_quality")
        fallback_qualities = args.get("fallback_qualities", [])
        
        settings = load_settings(project_root)
        config = load_runtime_config(project_root)
        
        # Get provider from main agent context or fall back to config
        provider = args.get("provider") or config.get("llm", {}).get("provider", "openai")
        api_key = args.get("api_key") or settings.openai_api_key or config.get("llm", {}).get("apiKey", "")
        
        # Create sub-agent for focused movie addition with correct provider settings
        sub_agent = SubAgent(
            api_key=api_key,
            project_root=project_root,
            provider=provider
        )
        
        try:
            result = await sub_agent.handle_radarr_movie_addition_fallback(
                tmdb_id=tmdb_id,
                movie_title=movie_title,
                preferred_quality=preferred_quality,
                fallback_qualities=fallback_qualities
            )
            return result
        finally:
            # Clean up sub-agent resources
            if hasattr(sub_agent.llm, 'client') and hasattr(sub_agent.llm.client, 'close'):
                await sub_agent.llm.client.close()

    return impl


def make_radarr_activity_check(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Check Radarr activity status including queue, wanted movies, and upcoming releases using sub-agent."""
    async def impl(args: dict) -> dict:
        from bot.sub_agent import SubAgent
        
        check_queue = args.get("check_queue", True)
        check_wanted = args.get("check_wanted", True)
        check_calendar = args.get("check_calendar", False)
        max_results = int(args.get("max_results", 10))
        
        settings = load_settings(project_root)
        config = load_runtime_config(project_root)
        
        # Get provider from main agent context or fall back to config
        provider = args.get("provider") or config.get("llm", {}).get("provider", "openai")
        api_key = args.get("api_key") or settings.openai_api_key or config.get("llm", {}).get("apiKey", "")
        
        # Create sub-agent for activity checking with correct provider settings
        sub_agent = SubAgent(
            api_key=api_key,
            project_root=project_root,
            provider=provider
        )
        
        try:
            result = await sub_agent.handle_radarr_activity_check(
                check_queue=check_queue,
                check_wanted=check_wanted,
                check_calendar=check_calendar,
                max_results=max_results
            )
            return result
        finally:
            # Clean up sub-agent resources
            if hasattr(sub_agent.llm, 'client') and hasattr(sub_agent.llm.client, 'close'):
                await sub_agent.llm.client.close()

    return impl


def make_radarr_quality_fallback(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Handle quality fallback for existing movies when preferred quality isn't available using sub-agent."""
    async def impl(args: dict) -> dict:
        from bot.sub_agent import SubAgent
        
        movie_id = int(args["movie_id"])
        movie_title = str(args["movie_title"])
        target_quality = str(args["target_quality"])
        fallback_qualities = [str(q) for q in args["fallback_qualities"]]
        
        settings = load_settings(project_root)
        config = load_runtime_config(project_root)
        
        # Get provider from main agent context or fall back to config
        provider = args.get("provider") or config.get("llm", {}).get("provider", "openai")
        api_key = args.get("api_key") or settings.openai_api_key or config.get("llm", {}).get("apiKey", "")
        
        # Create sub-agent for quality management with correct provider settings
        sub_agent = SubAgent(
            api_key=api_key,
            project_root=project_root,
            provider=provider
        )
        
        try:
            result = await sub_agent.handle_radarr_quality_fallback(
                movie_id=movie_id,
                movie_title=movie_title,
                target_quality=target_quality,
                fallback_qualities=fallback_qualities
            )
            return result
        finally:
            # Clean up sub-agent resources
            if hasattr(sub_agent.llm, 'client') and hasattr(sub_agent.llm.client, 'close'):
                await sub_agent.llm.client.close()

    return impl


