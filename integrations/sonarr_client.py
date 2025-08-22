from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

import httpx


class SonarrClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        
        if not base_url or not base_url.strip():
            raise ValueError("base_url cannot be empty")
        if not api_key or not api_key.strip():
            raise ValueError("api_key cannot be empty")
        
        # Validate URL format
        if not base_url.startswith(('http://', 'https://')):
            raise ValueError("base_url must start with http:// or https://")
        
        # Avoid binding an AsyncClient to a specific event loop; create per-call clients instead
        self._client = None
        
        print(f"🔗 Sonarr client initialized for: {self.base_url}")

    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers={"X-Api-Key": self.api_key},
            timeout=20.0,
        )

    async def close(self) -> None:
        try:
            if self._client is not None:
                await self._client.aclose()
        except RuntimeError as e:
            if "Event loop is closed" not in str(e):
                raise

    # System & Status
    async def system_status(self) -> Dict[str, Any]:
        async with self._new_client() as client:
            r = await client.get("/api/v3/system/status")
            r.raise_for_status()
            return r.json()

    async def health(self) -> List[Dict[str, Any]]:
        async with self._new_client() as client:
            r = await client.get("/api/v3/health")
            r.raise_for_status()
            return r.json()

    async def disk_space(self) -> List[Dict[str, Any]]:
        async with self._new_client() as client:
            r = await client.get("/api/v3/diskspace")
            r.raise_for_status()
            return r.json()

    # Quality & Folders
    async def quality_profiles(self) -> List[Dict[str, Any]]:
        async with self._new_client() as client:
            r = await client.get("/api/v3/qualityprofile")
            r.raise_for_status()
            return r.json()

    async def get_quality_profile_names(self) -> List[Dict[str, Any]]:
        """Get quality profiles with just id and name for easier selection."""
        profiles = await self.quality_profiles()
        return [{"id": p.get("id"), "name": p.get("name")} for p in profiles if p.get("id") and p.get("name")]

    async def root_folders(self) -> List[Dict[str, Any]]:
        async with self._new_client() as client:
            r = await client.get("/api/v3/rootfolder")
            r.raise_for_status()
            return r.json()

    async def get_root_folder_paths(self) -> List[str]:
        """Get just the root folder paths for easier selection."""
        folders = await self.root_folders()
        return [f.get("path") for f in folders if f.get("path")]

    # Series Management
    async def get_series(self, series_id: Optional[int] = None) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        async with self._new_client() as client:
            if series_id:
                r = await client.get(f"/api/v3/series/{series_id}")
                r.raise_for_status()
                return r.json()
            else:
                r = await client.get("/api/v3/series")
                r.raise_for_status()
                return r.json()

    async def lookup(self, term: str) -> List[Dict[str, Any]]:
        async with self._new_client() as client:
            r = await client.get("/api/v3/series/lookup", params={"term": term})
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
        # Enhanced parameters for better control
        seasons_to_monitor: Optional[List[int]] = None,
        episodes_to_monitor: Optional[List[int]] = None,
        monitor_new_episodes: bool = True,
    ) -> Dict[str, Any]:
        # Validate required parameters
        await self._validate_add_series_params(
            tvdb_id=tvdb_id,
            quality_profile_id=quality_profile_id,
            root_folder_path=root_folder_path
        )
        
        # Get series title from TVDB ID lookup
        lookup_results = await self.lookup(str(tvdb_id))
        if not lookup_results:
            raise ValueError(f"TVDB ID {tvdb_id} not found in Sonarr lookup")
        
        series_info = lookup_results[0]
        series_title = series_info.get("title")
        if not series_title:
            raise ValueError(f"Series title not found for TVDB ID {tvdb_id}")
        
        # Build the payload with all required fields for Sonarr v3 API
        payload = {
            "tvdbId": tvdb_id,
            "title": series_title,  # Required field that was missing
            "titleSlug": series_info.get("titleSlug", ""),  # Required for Sonarr
            "overview": series_info.get("overview", ""),  # Required for Sonarr
            "qualityProfileId": quality_profile_id,
            "rootFolderPath": root_folder_path,
            "monitored": monitored,
            "seasonFolder": season_folder,
            "addOptions": {
                "searchForMissingEpisodes": search_for_missing,
                "ignoreEpisodesWithFiles": False,
                "ignoreEpisodesWithoutFiles": False,
                "addAndSearchForMissing": search_for_missing
            },
            "monitorNewEpisodes": monitor_new_episodes,
            # Additional required fields that Sonarr expects
            "useAlternateTitlesForSearch": False,
            "addOnly": False,
            "seasons": [],  # Will be populated by Sonarr automatically
            "episodes": [],  # Will be populated by Sonarr automatically
        }
        
        try:
            # If specific seasons/episodes are specified, we'll need to update after creation
            async with self._new_client() as client:
                r = await client.post("/api/v3/series", json=payload)
                r.raise_for_status()
                series_data = r.json()
            
            # Apply season/episode monitoring if specified
            if seasons_to_monitor is not None or episodes_to_monitor is not None:
                series_id = series_data.get("id")
                if series_id:
                    await self._apply_monitoring_rules(series_id, seasons_to_monitor, episodes_to_monitor)
                    # Refresh series data
                    series_data = await self.get_series(series_id)
            
            return series_data
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400:
                # Get detailed error information from Sonarr
                try:
                    error_detail = e.response.json()
                    error_msg = f"Sonarr API error (400): {error_detail.get('message', 'Unknown error')}"
                    if 'validationErrors' in error_detail:
                        validation_errors = error_detail['validationErrors']
                        error_msg += f" Validation errors: {validation_errors}"
                except Exception:
                    error_msg = f"Sonarr API error (400): {e.response.text}"
                
                raise ValueError(error_msg) from e
            else:
                raise

    async def _validate_add_series_params(self, tvdb_id: int, quality_profile_id: int, root_folder_path: str) -> None:
        """Validate parameters before attempting to add a series."""
        if not tvdb_id or tvdb_id <= 0:
            raise ValueError("tvdb_id must be a positive integer")
        
        if not quality_profile_id or quality_profile_id <= 0:
            raise ValueError("quality_profile_id must be a positive integer")
        
        if not root_folder_path or not root_folder_path.strip():
            raise ValueError("root_folder_path cannot be empty")
        
        # Verify the quality profile exists
        try:
            quality_profiles = await self.quality_profiles()
            profile_ids = [p.get("id") for p in quality_profiles if p.get("id")]
            if quality_profile_id not in profile_ids:
                raise ValueError(f"Quality profile ID {quality_profile_id} not found. Available IDs: {profile_ids}")
        except Exception as e:
            raise ValueError(f"Failed to validate quality profile: {e}")
        
        # Verify the root folder exists
        try:
            root_folders = await self.root_folders()
            folder_paths = [f.get("path") for f in root_folders if f.get("path")]
            if root_folder_path not in folder_paths:
                raise ValueError(f"Root folder path '{root_folder_path}' not found. Available paths: {folder_paths}")
        except Exception as e:
            raise ValueError(f"Failed to validate root folder: {e}")
        
        # Verify the TVDB ID is valid by doing a lookup
        try:
            lookup_results = await self.lookup(str(tvdb_id))
            if not lookup_results:
                raise ValueError(f"TVDB ID {tvdb_id} not found in Sonarr lookup")
        except Exception as e:
            raise ValueError(f"Failed to validate TVDB ID: {e}")

    async def _apply_monitoring_rules(self, series_id: int, seasons_to_monitor: Optional[List[int]], episodes_to_monitor: Optional[List[int]]) -> None:
        """Apply season and episode monitoring rules after series creation."""
        if seasons_to_monitor is not None:
            # First, get all seasons
            seasons = await self.get_seasons(series_id)
            for season in seasons:
                season_number = season.get("seasonNumber")
                if season_number is not None:
                    should_monitor = season_number in seasons_to_monitor
                    await self.monitor_season(series_id, season_number, should_monitor)
        
        if episodes_to_monitor is not None:
            # Get episodes and apply monitoring
            episodes = await self.get_episodes(series_id)
            episode_ids_to_monitor = []
            episode_ids_to_unmonitor = []
            
            for episode in episodes:
                episode_id = episode.get("id")
                if episode_id is not None:
                    if episode_id in episodes_to_monitor:
                        episode_ids_to_monitor.append(episode_id)
                    else:
                        episode_ids_to_unmonitor.append(episode_id)
            
            # Apply monitoring in batches
            if episode_ids_to_monitor:
                await self.monitor_episodes(episode_ids_to_monitor, True)
            if episode_ids_to_unmonitor:
                await self.monitor_episodes(episode_ids_to_unmonitor, False)

    async def update_series(self, series_id: int, **kwargs) -> Dict[str, Any]:
        async with self._new_client() as client:
            r = await client.put(f"/api/v3/series/{series_id}", json=kwargs)
            r.raise_for_status()
            return r.json()

    async def delete_series(self, series_id: int, delete_files: bool = False, add_import_list_exclusion: bool = False) -> None:
        params = {
            "deleteFiles": delete_files,
            "addImportListExclusion": add_import_list_exclusion
        }
        async with self._new_client() as client:
            r = await client.delete(f"/api/v3/series/{series_id}", params=params)
            r.raise_for_status()

    # Episode Management
    async def get_episodes(self, series_id: Optional[int] = None, episode_ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
        async with self._new_client() as client:
            if episode_ids:
                params = {"episodeIds": episode_ids}
                r = await client.get("/api/v3/episode", params=params)
            elif series_id:
                r = await client.get(f"/api/v3/episode", params={"seriesId": series_id})
            else:
                r = await client.get("/api/v3/episode")
            r.raise_for_status()
            return r.json()

    async def update_episodes(self, episodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        async with self._new_client() as client:
            r = await client.put("/api/v3/episode", json=episodes)
            r.raise_for_status()
            return r.json()

    async def monitor_episodes(self, episode_ids: List[int], monitored: bool) -> List[Dict[str, Any]]:
        episodes = await self.get_episodes(episode_ids=episode_ids)
        for episode in episodes:
            episode["monitored"] = monitored
        return await self.update_episodes(episodes)

    # Enhanced Episode Control
    async def monitor_episodes_by_season(self, series_id: int, season_number: int, monitored: bool) -> List[Dict[str, Any]]:
        """Monitor all episodes in a specific season."""
        episodes = await self.get_episodes(series_id)
        season_episode_ids = [
            episode["id"] for episode in episodes 
            if episode.get("seasonNumber") == season_number
        ]
        return await self.monitor_episodes(season_episode_ids, monitored)

    async def monitor_episodes_by_air_date(self, series_id: int, start_date: str, end_date: str, monitored: bool) -> List[Dict[str, Any]]:
        """Monitor episodes within a date range."""
        episodes = await self.get_episodes(series_id)
        date_filtered_ids = [
            episode["id"] for episode in episodes 
            if episode.get("airDateUtc") and start_date <= episode["airDateUtc"] <= end_date
        ]
        return await self.monitor_episodes(date_filtered_ids, monitored)

    async def get_episode_file_info(self, episode_id: int) -> Dict[str, Any]:
        """Get file information for a specific episode."""
        async with self._new_client() as client:
            r = await client.get(f"/api/v3/episodefile/{episode_id}")
            r.raise_for_status()
            return r.json()

    # Season Management
    async def get_seasons(self, series_id: int) -> List[Dict[str, Any]]:
        async with self._new_client() as client:
            r = await client.get(f"/api/v3/season/{series_id}")
            r.raise_for_status()
            return r.json()

    async def monitor_season(self, series_id: int, season_number: int, monitored: bool) -> Dict[str, Any]:
        async with self._new_client() as client:
            season = await client.get(f"/api/v3/season/{series_id}/{season_number}")
            season.raise_for_status()
            season_data = season.json()
            season_data["monitored"] = monitored
            r = await client.put(f"/api/v3/season/{series_id}/{season_number}", json=season_data)
            r.raise_for_status()
            return r.json()

    async def get_season_details(self, series_id: int, season_number: int) -> Dict[str, Any]:
        """Get detailed information about a specific season."""
        async with self._new_client() as client:
            r = await client.get(f"/api/v3/season/{series_id}/{season_number}")
            r.raise_for_status()
            return r.json()

    # Enhanced Search & Download
    async def search_series(self, series_id: int) -> Dict[str, Any]:
        async with self._new_client() as client:
            r = await client.post(f"/api/v3/command", json={
            "name": "SeriesSearch",
            "seriesId": series_id
        })
            r.raise_for_status()
            return r.json()

    async def search_episode(self, episode_id: int) -> Dict[str, Any]:
        async with self._new_client() as client:
            r = await client.post(f"/api/v3/command", json={
            "name": "EpisodeSearch",
            "episodeIds": [episode_id]
        })
            r.raise_for_status()
            return r.json()

    async def search_episodes(self, episode_ids: List[int]) -> Dict[str, Any]:
        """Search for multiple episodes at once."""
        async with self._new_client() as client:
            r = await client.post(f"/api/v3/command", json={
            "name": "EpisodeSearch",
            "episodeIds": episode_ids
        })
            r.raise_for_status()
            return r.json()

    async def search_season(self, series_id: int, season_number: int) -> Dict[str, Any]:
        """Search for all episodes in a specific season."""
        episodes = await self.get_episodes(series_id)
        season_episode_ids = [
            episode["id"] for episode in episodes 
            if episode.get("seasonNumber") == season_number
        ]
        if season_episode_ids:
            return await self.search_episodes(season_episode_ids)
        return {"ok": False, "error": "No episodes found for season"}

    async def search_missing(self) -> Dict[str, Any]:
        async with self._new_client() as client:
            r = await client.post(f"/api/v3/command", json={
            "name": "MissingEpisodeSearch"
        })
            r.raise_for_status()
            return r.json()

    # Commands & Queue
    async def get_commands(self) -> List[Dict[str, Any]]:
        async with self._new_client() as client:
            r = await client.get("/api/v3/command")
            r.raise_for_status()
            return r.json()

    async def get_queue(self) -> Dict[str, Any]:
        async with self._new_client() as client:
            r = await client.get("/api/v3/queue")
            r.raise_for_status()
            return r.json()

    async def delete_queue_item(self, queue_id: int, blacklist: bool = False) -> None:
        params = {"blacklist": blacklist}
        async with self._new_client() as client:
            r = await client.delete(f"/api/v3/queue/{queue_id}", params=params)
            r.raise_for_status()

    # History
    async def get_history(self, series_id: Optional[int] = None, episode_id: Optional[int] = None, 
                         page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        params = {"page": page, "pageSize": page_size}
        if series_id:
            params["seriesId"] = series_id
        if episode_id:
            params["episodeId"] = episode_id
        async with self._new_client() as client:
            r = await client.get("/api/v3/history", params=params)
            r.raise_for_status()
            return r.json()

    # Import Lists
    async def get_import_lists(self) -> List[Dict[str, Any]]:
        async with self._new_client() as client:
            r = await client.get("/api/v3/importlist")
            r.raise_for_status()
            return r.json()

    async def test_import_list(self, import_list_id: int) -> Dict[str, Any]:
        async with self._new_client() as client:
            r = await client.post(f"/api/v3/importlist/test", json={"id": import_list_id})
            r.raise_for_status()
            return r.json()

    # Notifications
    async def get_notifications(self) -> List[Dict[str, Any]]:
        async with self._new_client() as client:
            r = await client.get("/api/v3/notification")
            r.raise_for_status()
            return r.json()

    # Tags
    async def get_tags(self) -> List[Dict[str, Any]]:
        async with self._new_client() as client:
            r = await client.get("/api/v3/tag")
            r.raise_for_status()
            return r.json()

    async def create_tag(self, label: str) -> Dict[str, Any]:
        async with self._new_client() as client:
            r = await client.post("/api/v3/tag", json={"label": label})
            r.raise_for_status()
            return r.json()

    async def delete_tag(self, tag_id: int) -> None:
        async with self._new_client() as client:
            r = await client.delete(f"/api/v3/tag/{tag_id}")
            r.raise_for_status()

    # Calendar
    async def get_calendar(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        params = {}
        if start_date:
            params["start"] = start_date
        if end_date:
            params["end"] = end_date
        async with self._new_client() as client:
            r = await client.get("/api/v3/calendar", params=params)
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
        async with self._new_client() as client:
            r = await client.get("/api/v3/wanted/missing", params=params)
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
        async with self._new_client() as client:
            r = await client.get("/api/v3/wanted/cutoff", params=params)
            r.raise_for_status()
            return r.json()

    # Enhanced Context Management Methods
    async def get_series_summary(self, series_id: int) -> Dict[str, Any]:
        """Get a concise summary of series status for efficient context usage."""
        series = await self.get_series(series_id)
        if isinstance(series, list):
            series = next((s for s in series if s.get("id") == series_id), {})
        
        # Get basic episode counts
        episodes = await self.get_episodes(series_id)
        monitored_episodes = sum(1 for ep in episodes if ep.get("monitored", False))
        total_episodes = len(episodes)
        
        return {
            "id": series.get("id"),
            "title": series.get("title"),
            "status": series.get("status"),
            "monitored": series.get("monitored"),
            "total_episodes": total_episodes,
            "monitored_episodes": monitored_episodes,
            "path": series.get("path"),
            "quality_profile_id": series.get("qualityProfileId"),
            "root_folder_path": series.get("rootFolderPath"),
        }

    async def get_season_summary(self, series_id: int, season_number: int) -> Dict[str, Any]:
        """Get a concise summary of season status for efficient context usage."""
        season = await self.get_season_details(series_id, season_number)
        episodes = await self.get_episodes(series_id)
        season_episodes = [ep for ep in episodes if ep.get("seasonNumber") == season_number]
        
        monitored_count = sum(1 for ep in season_episodes if ep.get("monitored", False))
        total_count = len(season_episodes)
        
        return {
            "series_id": series_id,
            "season_number": season_number,
            "monitored": season.get("monitored"),
            "total_episodes": total_count,
            "monitored_episodes": monitored_count,
            "episode_file_count": season.get("episodeFileCount", 0),
            "size_on_disk": season.get("sizeOnDisk", 0),
        }

    async def test_connection(self) -> bool:
        """Test if the Sonarr connection is working."""
        try:
            await self.system_status()
            return True
        except Exception:
            return False


