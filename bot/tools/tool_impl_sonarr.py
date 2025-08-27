from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable

from bot.workers.sonarr import SonarrWorker


def make_sonarr_lookup(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = SonarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.lookup(str(args.get("term", "")).strip())

    return impl


def make_sonarr_add_series(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = SonarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.add_series(
            tvdb_id=int(args["tvdb_id"]),
            quality_profile_id=args.get("quality_profile_id"),
            root_folder_path=args.get("root_folder_path"),
            monitored=args.get("monitored", True),
            search_for_missing=args.get("search_for_missing", True),
            season_folder=args.get("season_folder", True),
            seasons_to_monitor=args.get("seasons_to_monitor"),
            episodes_to_monitor=args.get("episodes_to_monitor"),
            monitor_new_episodes=args.get("monitor_new_episodes", True),
        )

    return impl


def make_sonarr_get_series(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = SonarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_series(series_id=args.get("series_id"))

    return impl


def make_sonarr_update_series(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = SonarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.update_series(series_id=int(args["series_id"]), update_data=args.get("update_data", {}))

    return impl


def make_sonarr_delete_series(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = SonarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.delete_series(
            series_id=int(args["series_id"]),
            delete_files=args.get("delete_files"),
            add_import_list_exclusion=args.get("add_import_list_exclusion"),
        )

    return impl


def make_sonarr_get_episodes(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = SonarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_episodes(series_id=args.get("series_id"), episode_ids=args.get("episode_ids"))

    return impl


def make_sonarr_monitor_episodes(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = SonarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.monitor_episodes(episode_ids=args["episode_ids"], monitored=args["monitored"])

    return impl


def make_sonarr_search_series(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = SonarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.search_series(series_id=int(args["series_id"]))

    return impl


def make_sonarr_search_missing(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = SonarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.search_missing()

    return impl


def make_sonarr_get_queue(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = SonarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_queue()

    return impl


def make_sonarr_get_wanted(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = SonarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_wanted(
            page=int(args.get("page", 1)),
            page_size=int(args.get("page_size", 20)),
            sort_key=str(args.get("sort_key", "airDateUtc")),
            sort_dir=str(args.get("sort_dir", "desc")),
        )

    return impl


def make_sonarr_get_calendar(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = SonarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_calendar(start_date=args.get("start_date"), end_date=args.get("end_date"))

    return impl


def make_sonarr_system_status(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = SonarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.system_status()

    return impl


def make_sonarr_health(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = SonarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.health()

    return impl


def make_sonarr_disk_space(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = SonarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.disk_space()

    return impl


def make_sonarr_quality_profiles(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = SonarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.quality_profiles()

    return impl


def make_sonarr_root_folders(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = SonarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.root_folders()

    return impl


def make_sonarr_monitor_season(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = SonarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.monitor_season(series_id=int(args["series_id"]), season_number=int(args["season_number"]), monitored=args["monitored"])

    return impl


def make_sonarr_monitor_episodes_by_season(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = SonarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.monitor_episodes_by_season(series_id=int(args["series_id"]), season_number=int(args["season_number"]), monitored=args["monitored"])

    return impl


def make_sonarr_search_season(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = SonarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.search_season(series_id=int(args["series_id"]), season_number=int(args["season_number"]))

    return impl


def make_sonarr_search_episode(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = SonarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.search_episode(episode_id=int(args["episode_id"]))

    return impl


def make_sonarr_search_episodes(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = SonarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.search_episodes(episode_ids=args["episode_ids"]) 

    return impl


def make_sonarr_get_series_summary(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = SonarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_series_summary(series_id=int(args["series_id"]))

    return impl


def make_sonarr_get_season_summary(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = SonarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_season_summary(series_id=int(args["series_id"]), season_number=int(args["season_number"]))

    return impl


def make_sonarr_get_season_details(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = SonarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_season_details(series_id=int(args["series_id"]), season_number=int(args["season_number"]))

    return impl


def make_sonarr_get_episode_file_info(project_root: Path) -> Callable[[dict], Awaitable[dict]]:
    worker = SonarrWorker(project_root)

    async def impl(args: dict) -> dict:
        return await worker.get_episode_file_info(episode_id=int(args["episode_id"]))

    return impl


