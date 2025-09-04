from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from config.loader import load_settings, load_runtime_config
from integrations.radarr_client import RadarrClient
from integrations.ttl_cache import shared_cache


class RadarrWorker:
    """Worker that centralizes Radarr operations with tolerant argument handling."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.settings = load_settings(project_root)
        self.config = load_runtime_config(project_root)
        self.client = RadarrClient(self.settings.radarr_base_url, self.settings.radarr_api_key or "")

    # --------------------------- helpers ---------------------------
    @staticmethod
    def _coerce_bool(value: Any, default: bool = True) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            v = value.strip().lower()
            if v in ("1", "true", "yes", "y", "on"):  # tolerant parsing
                return True
            if v in ("0", "false", "no", "n", "off"):
                return False
        return default

    @staticmethod
    def _coerce_int(value: Any) -> Optional[int]:
        try:
            return int(value)
        except Exception:
            return None

    # --------------------------- operations ---------------------------
    async def lookup(self, term: str) -> Dict[str, Any]:
        data = await self.client.lookup(term)
        return {"results": data}

    async def add_movie(
        self,
        *,
        tmdb_id: int,
        quality_profile_id: Optional[int] = None,
        root_folder_path: Optional[str] = None,
        monitored: Optional[bool] = True,
        search_now: Optional[bool] = True,
    ) -> Dict[str, Any]:
        qpid = quality_profile_id or self.config.get("radarr", {}).get("qualityProfileId")
        root = root_folder_path or self.config.get("radarr", {}).get("rootFolderPath")
        data = await self.client.add_movie(
            tmdb_id=int(tmdb_id),
            quality_profile_id=int(qpid) if qpid is not None else None,
            root_folder_path=str(root) if root is not None else None,
            monitored=self._coerce_bool(monitored, True),
            search_now=self._coerce_bool(search_now, True),
        )
        
        # If the movie already exists, return a user-friendly response
        if data.get("already_exists"):
            return {
                "success": True,
                "already_exists": True,
                "message": data.get("message", f"Movie with TMDb ID {tmdb_id} already exists in Radarr"),
                "movie": data,
                "tmdb_id": tmdb_id
            }
        
        return data

    async def get_movies(self, *, movie_id: Optional[int] = None, bypass_cache: bool = False) -> Dict[str, Any]:
        """Get movies with intelligent caching for better performance."""
        # Create cache key based on parameters
        cache_key = f"radarr:movies:{movie_id if movie_id else 'all'}"
        
        if not bypass_cache:
            cached = shared_cache.get(cache_key)
            if cached is not None:
                return cached
        
        data = await self.client.get_movies(movie_id)
        result = {"movies": data}
        
        # Cache for 2 minutes for all movies, 5 minutes for specific movie
        ttl = 300 if movie_id else 120
        shared_cache.set(cache_key, result, ttl)
        
        return result

    async def update_movie(self, *, movie_id: int, update_data: Dict[str, Any]) -> Dict[str, Any]:
        data = await self.client.update_movie(int(movie_id), **(update_data or {}))
        return {"updated_movie": data}

    async def delete_movie(self, *, movie_id: int, delete_files: Optional[bool], add_import_list_exclusion: Optional[bool]) -> Dict[str, Any]:
        await self.client.delete_movie(
            int(movie_id),
            self._coerce_bool(delete_files, False),
            self._coerce_bool(add_import_list_exclusion, False),
        )
        return {"ok": True, "deleted_movie_id": int(movie_id)}

    async def search_movie(self, *, movie_id: int) -> Dict[str, Any]:
        data = await self.client.search_movie(int(movie_id))
        return {"search_command": data}

    async def search_missing(self) -> Dict[str, Any]:
        data = await self.client.search_missing()
        return {"search_command": data}

    async def search_cutoff(self) -> Dict[str, Any]:
        data = await self.client.search_cutoff()
        return {"search_command": data}

    async def get_queue(self) -> Dict[str, Any]:
        data = await self.client.get_queue()
        return {"queue": data}

    async def get_wanted(self, *, page: int = 1, page_size: int = 20, sort_key: str = "releaseDate", sort_dir: str = "desc") -> Dict[str, Any]:
        data = await self.client.get_wanted(int(page), int(page_size), str(sort_key), str(sort_dir))
        return {"wanted": data}

    async def get_calendar(self, *, start_date: Optional[str], end_date: Optional[str]) -> Dict[str, Any]:
        data = await self.client.get_calendar(start_date, end_date)
        return {"calendar": data}

    async def get_blacklist(self, *, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        data = await self.client.get_blacklist(int(page), int(page_size))
        return {"blacklist": data}

    async def clear_blacklist(self) -> Dict[str, Any]:
        await self.client.clear_blacklist()
        return {"ok": True, "message": "Blacklist cleared"}

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

    async def get_indexers(self) -> Dict[str, Any]:
        data = await self.client.get_indexers()
        return {"indexers": data}

    async def get_download_clients(self) -> Dict[str, Any]:
        data = await self.client.get_download_clients()
        return {"download_clients": data}


