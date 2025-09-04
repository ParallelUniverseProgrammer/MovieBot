from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable

from bot.workers.plex import PlexWorker


def make_get_plex_library_sections(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = PlexWorker(project_root)

    async def impl(_args: dict) -> dict:
        return await worker.get_library_sections()

    return impl


def make_get_plex_recently_added(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = PlexWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_recently_added(
            section_type=str(args.get("section_type", "movie")).lower(),
            limit=int(args.get("limit", 20)),
            response_level=args.get("response_level"),
        )

    return impl


def make_get_plex_on_deck(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = PlexWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_on_deck(
            limit=int(args.get("limit", 20)),
            response_level=args.get("response_level"),
        )

    return impl


def make_get_plex_continue_watching(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = PlexWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_continue_watching(
            limit=int(args.get("limit", 20)),
            response_level=args.get("response_level"),
        )

    return impl


def make_get_plex_unwatched(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = PlexWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_unwatched(
            section_type=str(args.get("section_type", "movie")).lower(),
            limit=int(args.get("limit", 20)),
            response_level=args.get("response_level"),
        )

    return impl


def make_get_plex_collections(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = PlexWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_collections(
            section_type=str(args.get("section_type", "movie")).lower(),
            limit=int(args.get("limit", 50)),
            response_level=args.get("response_level"),
        )

    return impl


def make_get_plex_playlists(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = PlexWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_playlists(
            limit=int(args.get("limit", 50)),
            response_level=args.get("response_level"),
        )

    return impl


def make_get_plex_similar_items(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = PlexWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_similar_items(
            rating_key=int(args["rating_key"]),
            limit=int(args.get("limit", 10)),
            response_level=args.get("response_level"),
        )

    return impl


def make_get_plex_extras(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = PlexWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_extras(rating_key=int(args["rating_key"]))

    return impl


def make_get_plex_playback_status(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = PlexWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_playback_status(response_level=args.get("response_level"))

    return impl


def make_get_plex_watch_history(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = PlexWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_watch_history(rating_key=int(args["rating_key"]), limit=int(args.get("limit", 20)))

    return impl


def make_get_plex_item_details(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = PlexWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_item_details(rating_key=int(args["rating_key"]), response_level=args.get("response_level"))

    return impl


def make_get_plex_movies_4k_or_hdr(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = PlexWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_movies_4k_or_hdr(
            limit=int(args.get("limit", 30)),
            section_id=args.get("section_id"),
            or_semantics=bool(args.get("or_semantics", True)),
            response_level=args.get("response_level"),
        )

    return impl


def make_set_plex_rating(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = PlexWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.set_rating(rating_key=int(args["rating_key"]), rating=int(args["rating"]))

    return impl


def make_plex_library_overview(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    """Bundled tool that fetches comprehensive Plex library overview in parallel."""
    worker = PlexWorker(project_root)

    async def impl(args: dict) -> dict:
        import asyncio
        
        # Extract common parameters
        section_type = str(args.get("section_type", "movie")).lower()
        limit = int(args.get("limit", 20))
        response_level = args.get("response_level")
        
        # Run all library overview calls in parallel
        tasks = [
            worker.get_library_sections(),
            worker.get_recently_added(section_type=section_type, limit=limit, response_level=response_level),
            worker.get_on_deck(limit=limit, response_level=response_level),
            worker.get_continue_watching(limit=limit, response_level=response_level),
            worker.get_unwatched(section_type=section_type, limit=limit, response_level=response_level),
        ]
        
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results and handle any exceptions
            library_sections, recently_added, on_deck, continue_watching, unwatched = results
            
            # Check for exceptions and provide fallback data
            def safe_result(result, default_name):
                if isinstance(result, Exception):
                    return {"error": str(result), "data": [], "name": default_name}
                return result
            
            return {
                "success": True,
                "library_sections": safe_result(library_sections, "library_sections"),
                "recently_added": safe_result(recently_added, "recently_added"),
                "on_deck": safe_result(on_deck, "on_deck"),
                "continue_watching": safe_result(continue_watching, "continue_watching"),
                "unwatched": safe_result(unwatched, "unwatched"),
                "summary": {
                    "total_sections": len(library_sections.get("sections", [])) if not isinstance(library_sections, Exception) else 0,
                    "recently_added_count": len(recently_added.get("items", [])) if not isinstance(recently_added, Exception) else 0,
                    "on_deck_count": len(on_deck.get("items", [])) if not isinstance(on_deck, Exception) else 0,
                    "continue_watching_count": len(continue_watching.get("items", [])) if not isinstance(continue_watching, Exception) else 0,
                    "unwatched_count": len(unwatched.get("items", [])) if not isinstance(unwatched, Exception) else 0,
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to fetch library overview: {str(e)}",
                "library_sections": {"error": str(e), "data": [], "name": "library_sections"},
                "recently_added": {"error": str(e), "data": [], "name": "recently_added"},
                "on_deck": {"error": str(e), "data": [], "name": "on_deck"},
                "continue_watching": {"error": str(e), "data": [], "name": "continue_watching"},
                "unwatched": {"error": str(e), "data": [], "name": "unwatched"},
                "summary": {
                    "total_sections": 0,
                    "recently_added_count": 0,
                    "on_deck_count": 0,
                    "continue_watching_count": 0,
                    "unwatched_count": 0,
                }
            }

    return impl


