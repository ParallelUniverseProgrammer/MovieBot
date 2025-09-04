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


def make_system_health_overview(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Bundled tool that checks system health across all services in parallel."""
    async def impl(args: dict) -> dict:
        import asyncio
        from bot.workers.radarr import RadarrWorker
        from bot.workers.sonarr import SonarrWorker
        from bot.workers.plex import PlexWorker
        
        # Initialize workers
        radarr_worker = RadarrWorker(project_root)
        sonarr_worker = SonarrWorker(project_root)
        plex_worker = PlexWorker(project_root)
        
        # Run all health checks in parallel
        tasks = [
            radarr_worker.system_status(),
            radarr_worker.health(),
            radarr_worker.disk_space(),
            sonarr_worker.system_status(),
            sonarr_worker.health(),
            sonarr_worker.disk_space(),
            plex_worker.get_library_sections(),
        ]
        
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results and handle any exceptions
            radarr_status, radarr_health, radarr_disk, sonarr_status, sonarr_health, sonarr_disk, plex_sections = results
            
            # Check for exceptions and provide fallback data
            def safe_result(result, default_name):
                if isinstance(result, Exception):
                    return {"error": str(result), "name": default_name, "status": "error"}
                return result
            
            # Determine overall system health
            all_healthy = True
            error_count = 0
            
            for result in results:
                if isinstance(result, Exception):
                    all_healthy = False
                    error_count += 1
            
            return {
                "success": True,
                "overall_health": "healthy" if all_healthy else "degraded",
                "error_count": error_count,
                "total_checks": len(tasks),
                "radarr": {
                    "system_status": safe_result(radarr_status, "radarr_system_status"),
                    "health": safe_result(radarr_health, "radarr_health"),
                    "disk_space": safe_result(radarr_disk, "radarr_disk_space"),
                },
                "sonarr": {
                    "system_status": safe_result(sonarr_status, "sonarr_system_status"),
                    "health": safe_result(sonarr_health, "sonarr_health"),
                    "disk_space": safe_result(sonarr_disk, "sonarr_disk_space"),
                },
                "plex": {
                    "library_sections": safe_result(plex_sections, "plex_library_sections"),
                },
                "summary": {
                    "radarr_healthy": not isinstance(radarr_status, Exception) and not isinstance(radarr_health, Exception),
                    "sonarr_healthy": not isinstance(sonarr_status, Exception) and not isinstance(sonarr_health, Exception),
                    "plex_healthy": not isinstance(plex_sections, Exception),
                    "total_disk_space_available": (
                        (radarr_disk.get("free_space", 0) if not isinstance(radarr_disk, Exception) else 0) +
                        (sonarr_disk.get("free_space", 0) if not isinstance(sonarr_disk, Exception) else 0)
                    ) if not isinstance(radarr_disk, Exception) and not isinstance(sonarr_disk, Exception) else 0,
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to fetch system health overview: {str(e)}",
                "overall_health": "error",
                "error_count": len(tasks),
                "total_checks": len(tasks),
                "radarr": {
                    "system_status": {"error": str(e), "name": "radarr_system_status", "status": "error"},
                    "health": {"error": str(e), "name": "radarr_health", "status": "error"},
                    "disk_space": {"error": str(e), "name": "radarr_disk_space", "status": "error"},
                },
                "sonarr": {
                    "system_status": {"error": str(e), "name": "sonarr_system_status", "status": "error"},
                    "health": {"error": str(e), "name": "sonarr_health", "status": "error"},
                    "disk_space": {"error": str(e), "name": "sonarr_disk_space", "status": "error"},
                },
                "plex": {
                    "library_sections": {"error": str(e), "name": "plex_library_sections", "status": "error"},
                },
                "summary": {
                    "radarr_healthy": False,
                    "sonarr_healthy": False,
                    "plex_healthy": False,
                    "total_disk_space_available": 0,
                }
            }

    return impl


def make_radarr_activity_overview(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Bundled tool that fetches comprehensive Radarr activity overview in parallel."""
    worker = RadarrWorker(project_root)

    async def impl(args: dict) -> dict:
        import asyncio
        
        # Extract parameters
        page = int(args.get("page", 1))
        page_size = int(args.get("page_size", 20))
        sort_key = str(args.get("sort_key", "releaseDate"))
        sort_dir = str(args.get("sort_dir", "desc"))
        start_date = args.get("start_date")
        end_date = args.get("end_date")
        
        # Run all activity checks in parallel
        tasks = [
            worker.get_queue(),
            worker.get_wanted(page=page, page_size=page_size, sort_key=sort_key, sort_dir=sort_dir),
            worker.get_calendar(start_date=start_date, end_date=end_date),
        ]
        
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results and handle any exceptions
            queue, wanted, calendar = results
            
            # Check for exceptions and provide fallback data
            def safe_result(result, default_name):
                if isinstance(result, Exception):
                    return {"error": str(result), "data": [], "name": default_name}
                return result
            
            return {
                "success": True,
                "queue": safe_result(queue, "queue"),
                "wanted": safe_result(wanted, "wanted"),
                "calendar": safe_result(calendar, "calendar"),
                "summary": {
                    "queue_count": len(queue.get("records", [])) if not isinstance(queue, Exception) else 0,
                    "wanted_count": len(wanted.get("records", [])) if not isinstance(wanted, Exception) else 0,
                    "calendar_count": len(calendar.get("records", [])) if not isinstance(calendar, Exception) else 0,
                    "total_activity": (
                        len(queue.get("records", [])) if not isinstance(queue, Exception) else 0 +
                        len(wanted.get("records", [])) if not isinstance(wanted, Exception) else 0 +
                        len(calendar.get("records", [])) if not isinstance(calendar, Exception) else 0
                    ),
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to fetch Radarr activity overview: {str(e)}",
                "queue": {"error": str(e), "data": [], "name": "queue"},
                "wanted": {"error": str(e), "data": [], "name": "wanted"},
                "calendar": {"error": str(e), "data": [], "name": "calendar"},
                "summary": {
                    "queue_count": 0,
                    "wanted_count": 0,
                    "calendar_count": 0,
                    "total_activity": 0,
                }
            }

    return impl


