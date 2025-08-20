from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx


class SonarrClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = httpx.AsyncClient(base_url=self.base_url, headers={"X-Api-Key": api_key}, timeout=20.0)

    async def close(self) -> None:
        await self._client.aclose()

    # System & Status
    async def system_status(self) -> Dict[str, Any]:
        r = await self._client.get("/api/v3/system/status")
        r.raise_for_status()
        return r.json()

    async def health(self) -> List[Dict[str, Any]]:
        r = await self._client.get("/api/v3/health")
        r.raise_for_status()
        return r.json()

    async def disk_space(self) -> List[Dict[str, Any]]:
        r = await self._client.get("/api/v3/diskspace")
        r.raise_for_status()
        return r.json()

    # Quality & Folders
    async def quality_profiles(self) -> List[Dict[str, Any]]:
        r = await self._client.get("/api/v3/qualityprofile")
        r.raise_for_status()
        return r.json()

    async def root_folders(self) -> List[Dict[str, Any]]:
        r = await self._client.get("/api/v3/rootfolder")
        r.raise_for_status()
        return r.json()

    # Series Management
    async def get_series(self, series_id: Optional[int] = None) -> List[Dict[str, Any]]:
        if series_id:
            r = await self._client.get(f"/api/v3/series/{series_id}")
        else:
            r = await self._client.get("/api/v3/series")
        r.raise_for_status()
        return r.json()

    async def lookup(self, term: str) -> List[Dict[str, Any]]:
        r = await self._client.get("/api/v3/series/lookup", params={"term": term})
        r.raise_for_status()
        return r.json()

    async def add_series(
        self,
        *,
        tvdb_id: int,
        quality_profile_id: int,
        root_folder_path: str,
        monitored: bool = True,
        search_for_missing: bool = True,
        season_folder: bool = True,
    ) -> Dict[str, Any]:
        payload = {
            "tvdbId": tvdb_id,
            "qualityProfileId": quality_profile_id,
            "rootFolderPath": root_folder_path,
            "monitored": monitored,
            "seasonFolder": season_folder,
            "addOptions": {"searchForMissingEpisodes": search_for_missing},
        }
        r = await self._client.post("/api/v3/series", json=payload)
        r.raise_for_status()
        return r.json()

    async def update_series(self, series_id: int, **kwargs) -> Dict[str, Any]:
        r = await self._client.put(f"/api/v3/series/{series_id}", json=kwargs)
        r.raise_for_status()
        return r.json()

    async def delete_series(self, series_id: int, delete_files: bool = False, add_import_list_exclusion: bool = False) -> None:
        params = {
            "deleteFiles": delete_files,
            "addImportListExclusion": add_import_list_exclusion
        }
        r = await self._client.delete(f"/api/v3/series/{series_id}", params=params)
        r.raise_for_status()

    # Episode Management
    async def get_episodes(self, series_id: Optional[int] = None, episode_ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
        if episode_ids:
            params = {"episodeIds": episode_ids}
            r = await self._client.get("/api/v3/episode", params=params)
        elif series_id:
            r = await self._client.get(f"/api/v3/episode", params={"seriesId": series_id})
        else:
            r = await self._client.get("/api/v3/episode")
        r.raise_for_status()
        return r.json()

    async def update_episodes(self, episodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        r = await self._client.put("/api/v3/episode", json=episodes)
        r.raise_for_status()
        return r.json()

    async def monitor_episodes(self, episode_ids: List[int], monitored: bool) -> List[Dict[str, Any]]:
        episodes = await self.get_episodes(episode_ids=episode_ids)
        for episode in episodes:
            episode["monitored"] = monitored
        return await self.update_episodes(episodes)

    # Season Management
    async def get_seasons(self, series_id: int) -> List[Dict[str, Any]]:
        r = await self._client.get(f"/api/v3/season/{series_id}")
        r.raise_for_status()
        return r.json()

    async def monitor_season(self, series_id: int, season_number: int, monitored: bool) -> Dict[str, Any]:
        season = await self._client.get(f"/api/v3/season/{series_id}/{season_number}")
        season.raise_for_status()
        season_data = season.json()
        season_data["monitored"] = monitored
        r = await self._client.put(f"/api/v3/season/{series_id}/{season_number}", json=season_data)
        r.raise_for_status()
        return r.json()

    # Search & Download
    async def search_series(self, series_id: int) -> Dict[str, Any]:
        r = await self._client.post(f"/api/v3/command", json={
            "name": "SeriesSearch",
            "seriesId": series_id
        })
        r.raise_for_status()
        return r.json()

    async def search_episode(self, episode_id: int) -> Dict[str, Any]:
        r = await self._client.post(f"/api/v3/command", json={
            "name": "EpisodeSearch",
            "episodeIds": [episode_id]
        })
        r.raise_for_status()
        return r.json()

    async def search_missing(self) -> Dict[str, Any]:
        r = await self._client.post(f"/api/v3/command", json={
            "name": "MissingEpisodeSearch"
        })
        r.raise_for_status()
        return r.json()

    # Commands & Queue
    async def get_commands(self) -> List[Dict[str, Any]]:
        r = await self._client.get("/api/v3/command")
        r.raise_for_status()
        return r.json()

    async def get_queue(self) -> Dict[str, Any]:
        r = await self._client.get("/api/v3/queue")
        r.raise_for_status()
        return r.json()

    async def delete_queue_item(self, queue_id: int, blacklist: bool = False) -> None:
        params = {"blacklist": blacklist}
        r = await self._client.delete(f"/api/v3/queue/{queue_id}", params=params)
        r.raise_for_status()

    # History
    async def get_history(self, series_id: Optional[int] = None, episode_id: Optional[int] = None, 
                         page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        params = {"page": page, "pageSize": page_size}
        if series_id:
            params["seriesId"] = series_id
        if episode_id:
            params["episodeId"] = episode_id
        
        r = await self._client.get("/api/v3/history", params=params)
        r.raise_for_status()
        return r.json()

    # Import Lists
    async def get_import_lists(self) -> List[Dict[str, Any]]:
        r = await self._client.get("/api/v3/importlist")
        r.raise_for_status()
        return r.json()

    async def test_import_list(self, import_list_id: int) -> Dict[str, Any]:
        r = await self._client.post(f"/api/v3/importlist/test", json={"id": import_list_id})
        r.raise_for_status()
        return r.json()

    # Notifications
    async def get_notifications(self) -> List[Dict[str, Any]]:
        r = await self._client.get("/api/v3/notification")
        r.raise_for_status()
        return r.json()

    # Tags
    async def get_tags(self) -> List[Dict[str, Any]]:
        r = await self._client.get("/api/v3/tag")
        r.raise_for_status()
        return r.json()

    async def create_tag(self, label: str) -> Dict[str, Any]:
        r = await self._client.post("/api/v3/tag", json={"label": label})
        r.raise_for_status()
        return r.json()

    async def delete_tag(self, tag_id: int) -> None:
        r = await self._client.delete(f"/api/v3/tag/{tag_id}")
        r.raise_for_status()

    # Calendar
    async def get_calendar(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        params = {}
        if start_date:
            params["start"] = start_date
        if end_date:
            params["end"] = end_date
        
        r = await self._client.get("/api/v3/calendar", params=params)
        r.raise_for_status()
        return r.json()

    # Wanted (Missing Episodes)
    async def get_wanted(self, page: int = 1, page_size: int = 20, sort_key: str = "airDateUtc", 
                        sort_dir: str = "desc") -> Dict[str, Any]:
        params = {
            "page": page,
            "pageSize": page_size,
            "sortKey": sort_key,
            "sortDir": sort_dir
        }
        r = await self._client.get("/api/v3/wanted/missing", params=params)
        r.raise_for_status()
        return r.json()

    # Cutoff (Unmet Quality)
    async def get_cutoff(self, page: int = 1, page_size: int = 20, sort_key: str = "airDateUtc", 
                         sort_dir: str = "desc") -> Dict[str, Any]:
        params = {
            "page": page,
            "pageSize": page_size,
            "sortKey": sort_key,
            "sortDir": sort_dir
        }
        r = await self._client.get("/api/v3/wanted/cutoff", params=params)
        r.raise_for_status()
        return r.json()


