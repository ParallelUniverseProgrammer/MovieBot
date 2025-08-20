from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx


class RadarrClient:
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

    # Movie Management
    async def get_movies(self, movie_id: Optional[int] = None) -> List[Dict[str, Any]]:
        if movie_id:
            r = await self._client.get(f"/api/v3/movie/{movie_id}")
        else:
            r = await self._client.get("/api/v3/movie")
        r.raise_for_status()
        return r.json()

    async def lookup(self, term: str) -> List[Dict[str, Any]]:
        r = await self._client.get("/api/v3/movie/lookup", params={"term": term})
        r.raise_for_status()
        return r.json()

    async def add_movie(
        self,
        *,
        tmdb_id: int,
        quality_profile_id: int,
        root_folder_path: str,
        monitored: bool = True,
        search_now: bool = True,
        minimum_availability: str = "announced",
    ) -> Dict[str, Any]:
        payload = {
            "tmdbId": tmdb_id,
            "qualityProfileId": quality_profile_id,
            "rootFolderPath": root_folder_path,
            "monitored": monitored,
            "minimumAvailability": minimum_availability,
            "addOptions": {"searchForMovie": search_now},
        }
        r = await self._client.post("/api/v3/movie", json=payload)
        r.raise_for_status()
        return r.json()

    async def update_movie(self, movie_id: int, **kwargs) -> Dict[str, Any]:
        r = await self._client.put(f"/api/v3/movie/{movie_id}", json=kwargs)
        r.raise_for_status()
        return r.json()

    async def delete_movie(self, movie_id: int, delete_files: bool = False, add_import_list_exclusion: bool = False) -> None:
        params = {
            "deleteFiles": delete_files,
            "addImportListExclusion": add_import_list_exclusion
        }
        r = await self._client.delete(f"/api/v3/movie/{movie_id}", params=params)
        r.raise_for_status()

    # Search & Download
    async def search_movie(self, movie_id: int) -> Dict[str, Any]:
        r = await self._client.post(f"/api/v3/command", json={
            "name": "MoviesSearch",
            "movieIds": [movie_id]
        })
        r.raise_for_status()
        return r.json()

    async def search_missing(self) -> Dict[str, Any]:
        r = await self._client.post(f"/api/v3/command", json={
            "name": "MissingMovieSearch"
        })
        r.raise_for_status()
        return r.json()

    async def search_cutoff(self) -> Dict[str, Any]:
        r = await self._client.post(f"/api/v3/command", json={
            "name": "CutOffUnmetMoviesSearch"
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
    async def get_history(self, movie_id: Optional[int] = None, page: int = 1, 
                         page_size: int = 20, event_type: Optional[str] = None) -> Dict[str, Any]:
        params = {"page": page, "pageSize": page_size}
        if movie_id:
            params["movieId"] = movie_id
        if event_type:
            params["eventType"] = event_type
        
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

    # Wanted (Missing Movies)
    async def get_wanted(self, page: int = 1, page_size: int = 20, sort_key: str = "releaseDate", 
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
    async def get_cutoff(self, page: int = 1, page_size: int = 20, sort_key: str = "releaseDate", 
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

    # Blacklist
    async def get_blacklist(self, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        params = {"page": page, "pageSize": page_size}
        r = await self._client.get("/api/v3/blacklist", params=params)
        r.raise_for_status()
        return r.json()

    async def delete_blacklist_item(self, blacklist_id: int) -> None:
        r = await self._client.delete(f"/api/v3/blacklist/{blacklist_id}")
        r.raise_for_status()

    async def clear_blacklist(self) -> None:
        r = await self._client.delete("/api/v3/blacklist")
        r.raise_for_status()

    # Indexers
    async def get_indexers(self) -> List[Dict[str, Any]]:
        r = await self._client.get("/api/v3/indexer")
        r.raise_for_status()
        return r.json()

    async def test_indexer(self, indexer_id: int) -> Dict[str, Any]:
        r = await self._client.post(f"/api/v3/indexer/test", json={"id": indexer_id})
        r.raise_for_status()
        return r.json()

    # Download Clients
    async def get_download_clients(self) -> List[Dict[str, Any]]:
        r = await self._client.get("/api/v3/downloadclient")
        r.raise_for_status()
        return r.json()

    async def test_download_client(self, download_client_id: int) -> Dict[str, Any]:
        r = await self._client.post(f"/api/v3/downloadclient/test", json={"id": download_client_id})
        r.raise_for_status()
        return r.json()

    # Metadata
    async def get_metadata_profiles(self) -> List[Dict[str, Any]]:
        r = await self._client.get("/api/v3/metadataprofile")
        r.raise_for_status()
        return r.json()

    # Naming
    async def get_naming_config(self) -> Dict[str, Any]:
        r = await self._client.get("/api/v3/config/naming")
        r.raise_for_status()
        return r.json()

    async def update_naming_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        r = await self._client.put("/api/v3/config/naming", json=config)
        r.raise_for_status()
        return r.json()

    # UI Config
    async def get_ui_config(self) -> Dict[str, Any]:
        r = await self._client.get("/api/v3/config/ui")
        r.raise_for_status()
        return r.json()

    async def update_ui_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        r = await self._client.put("/api/v3/config/ui", json=config)
        r.raise_for_status()
        return r.json()


