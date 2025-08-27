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


