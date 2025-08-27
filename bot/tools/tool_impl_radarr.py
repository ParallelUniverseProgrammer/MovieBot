from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable

from bot.workers.radarr import RadarrWorker


def make_radarr_lookup(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = RadarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.lookup(str(args.get("term", "")).strip())

    return impl


def make_radarr_add_movie(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = RadarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.add_movie(
            tmdb_id=int(args["tmdb_id"]),
            quality_profile_id=args.get("quality_profile_id"),
            root_folder_path=args.get("root_folder_path"),
            monitored=args.get("monitored", True),
            search_now=args.get("search_now", True),
        )

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


