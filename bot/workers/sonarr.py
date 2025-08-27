from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from config.loader import load_settings, load_runtime_config
from integrations.sonarr_client import SonarrClient


class SonarrWorker:
    """Worker centralizing Sonarr operations with robust arg normalization."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.settings = load_settings(project_root)
        self.config = load_runtime_config(project_root)
        self.client = SonarrClient(self.settings.sonarr_base_url, self.settings.sonarr_api_key or "")

    # --------------------------- helpers ---------------------------
    @staticmethod
    def _coerce_bool(value: Any, default: bool = True) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            v = value.strip().lower()
            if v in ("1", "true", "yes", "y", "on"):
                return True
            if v in ("0", "false", "no", "n", "off"):
                return False
        return default

    @staticmethod
    def _coerce_int_list(value: Any) -> Optional[List[int]]:
        if value is None:
            return None
        if isinstance(value, list):
            out: List[int] = []
            for v in value:
                try:
                    out.append(int(v))
                except Exception:
                    pass
            return out
        if isinstance(value, str):
            parts = [p.strip() for p in value.split(",") if p.strip()]
            out: List[int] = []
            for p in parts:
                try:
                    out.append(int(p))
                except Exception:
                    pass
            return out
        try:
            return [int(value)]
        except Exception:
            return None

    # --------------------------- basic ops ---------------------------
    async def lookup(self, term: str) -> Dict[str, Any]:
        data = await self.client.lookup(term)
        return {"results": data}

    async def add_series(
        self,
        *,
        tvdb_id: int,
        quality_profile_id: Optional[int] = None,
        root_folder_path: Optional[str] = None,
        monitored: Optional[bool] = True,
        search_for_missing: Optional[bool] = True,
        season_folder: Optional[bool] = True,
        seasons_to_monitor: Optional[List[int]] = None,
        episodes_to_monitor: Optional[List[int]] = None,
        monitor_new_episodes: Optional[bool] = True,
    ) -> Dict[str, Any]:
        qpid = quality_profile_id or self.config.get("sonarr", {}).get("qualityProfileId")
        root = root_folder_path or self.config.get("sonarr", {}).get("rootFolderPath")
        if not qpid:
            raise ValueError("Sonarr quality profile ID not configured. Set in config/config.yaml or pass quality_profile_id")
        if not root:
            raise ValueError("Sonarr root folder path not configured. Set in config/config.yaml or pass root_folder_path")
        data = await self.client.add_series(
            tvdb_id=int(tvdb_id),
            quality_profile_id=int(qpid),
            root_folder_path=str(root),
            monitored=self._coerce_bool(monitored, True),
            search_for_missing=self._coerce_bool(search_for_missing, True),
            season_folder=self._coerce_bool(season_folder, True),
            seasons_to_monitor=self._coerce_int_list(seasons_to_monitor),
            episodes_to_monitor=self._coerce_int_list(episodes_to_monitor),
            monitor_new_episodes=self._coerce_bool(monitor_new_episodes, True),
        )
        return data

    async def get_series(self, *, series_id: Optional[int] = None) -> Dict[str, Any]:
        data = await self.client.get_series(series_id)
        return {"series": data}

    async def update_series(self, *, series_id: int, update_data: Dict[str, Any]) -> Dict[str, Any]:
        data = await self.client.update_series(int(series_id), **(update_data or {}))
        return {"updated_series": data}

    async def delete_series(self, *, series_id: int, delete_files: Optional[bool], add_import_list_exclusion: Optional[bool]) -> Dict[str, Any]:
        await self.client.delete_series(
            int(series_id),
            self._coerce_bool(delete_files, False),
            self._coerce_bool(add_import_list_exclusion, False),
        )
        return {"ok": True, "deleted_series_id": int(series_id)}

    async def get_episodes(self, *, series_id: Optional[int] = None, episode_ids: Optional[List[int]] = None) -> Dict[str, Any]:
        data = await self.client.get_episodes(series_id, self._coerce_int_list(episode_ids))
        return {"episodes": data}

    async def monitor_episodes(self, *, episode_ids: List[int], monitored: bool) -> Dict[str, Any]:
        ids = self._coerce_int_list(episode_ids) or []
        data = await self.client.monitor_episodes(ids, self._coerce_bool(monitored, True))
        return {"updated_episodes": data}

    async def search_series(self, *, series_id: int) -> Dict[str, Any]:
        data = await self.client.search_series(int(series_id))
        return {"search_command": data}

    async def search_missing(self) -> Dict[str, Any]:
        data = await self.client.search_missing()
        return {"search_command": data}

    async def get_queue(self) -> Dict[str, Any]:
        data = await self.client.get_queue()
        return {"queue": data}

    async def get_wanted(self, *, page: int = 1, page_size: int = 20, sort_key: str = "airDateUtc", sort_dir: str = "desc") -> Dict[str, Any]:
        data = await self.client.get_wanted(int(page), int(page_size), str(sort_key), str(sort_dir))
        return {"wanted": data}

    async def get_calendar(self, *, start_date: Optional[str], end_date: Optional[str]) -> Dict[str, Any]:
        data = await self.client.get_calendar(start_date, end_date)
        return {"calendar": data}

    async def system_status(self) -> Dict[str, Any]:
        data = await self.client.system_status()
        return {"system_status": data}

    async def health(self) -> Dict[str, Any]:
        data = await self.client.health()
        return {"health": data}

    async def disk_space(self) -> Dict[str, Any]:
        data = await self.client.disk_space()
        return {"disk_space": data}

    async def quality_profiles(self) -> Dict[str, Any]:
        data = await self.client.quality_profiles()
        return {"quality_profiles": data}

    async def root_folders(self) -> Dict[str, Any]:
        data = await self.client.root_folders()
        return {"root_folders": data}

    # --------------------------- enhanced ops ---------------------------
    async def monitor_season(self, *, series_id: int, season_number: int, monitored: bool) -> Dict[str, Any]:
        data = await self.client.monitor_season(int(series_id), int(season_number), self._coerce_bool(monitored, True))
        return {"season_monitoring_updated": data}

    async def monitor_episodes_by_season(self, *, series_id: int, season_number: int, monitored: bool) -> Dict[str, Any]:
        data = await self.client.monitor_episodes_by_season(int(series_id), int(season_number), self._coerce_bool(monitored, True))
        return {"episodes_monitoring_updated": data}

    async def search_season(self, *, series_id: int, season_number: int) -> Dict[str, Any]:
        data = await self.client.search_season(int(series_id), int(season_number))
        return {"season_search_command": data}

    async def search_episode(self, *, episode_id: int) -> Dict[str, Any]:
        data = await self.client.search_episode(int(episode_id))
        return {"episode_search_command": data}

    async def search_episodes(self, *, episode_ids: List[int]) -> Dict[str, Any]:
        ids = self._coerce_int_list(episode_ids) or []
        data = await self.client.search_episodes(ids)
        return {"episodes_search_command": data}

    async def get_series_summary(self, *, series_id: int) -> Dict[str, Any]:
        data = await self.client.get_series_summary(int(series_id))
        return {"series_summary": data}

    async def get_season_summary(self, *, series_id: int, season_number: int) -> Dict[str, Any]:
        data = await self.client.get_season_summary(int(series_id), int(season_number))
        return {"season_summary": data}

    async def get_season_details(self, *, series_id: int, season_number: int) -> Dict[str, Any]:
        data = await self.client.get_season_details(int(series_id), int(season_number))
        return {"season_details": data}

    async def get_episode_file_info(self, *, episode_id: int) -> Dict[str, Any]:
        data = await self.client.get_episode_file_info(int(episode_id))
        return {"episode_file_info": data}


