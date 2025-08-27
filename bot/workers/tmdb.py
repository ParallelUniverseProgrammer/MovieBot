from __future__ import annotations

from typing import Any, Dict, List, Optional
from pathlib import Path

from config.loader import load_settings
from integrations.tmdb_client import TMDbClient, TMDbResponseLevel


class TMDbWorker:
    """Worker that centralizes TMDb operations and tolerant arg normalization.

    This worker wraps `TMDbClient` and provides convenience methods that:
    - Normalize and coerce incoming arguments (ids, lists, enums)
    - Apply sensible defaults for response levels and pagination
    - Keep callsites (tools) small and focused on intent
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.settings = load_settings(project_root)
        self.client = TMDbClient(self.settings.tmdb_api_key or "")

    # -------------------------- helpers --------------------------
    def _coerce_response_level(self, value: Optional[str], default: str = "compact") -> Optional[TMDbResponseLevel]:
        if not value:
            return None
        try:
            return TMDbResponseLevel(value)
        except Exception:
            # Fall back to default when unexpected input provided
            try:
                return TMDbResponseLevel(default)
            except Exception:
                return None

    @staticmethod
    def _coerce_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except Exception:
            return None

    @staticmethod
    def _coerce_int_list(value: Any) -> Optional[List[int]]:
        if value is None:
            return None
        if isinstance(value, list):
            out: List[int] = []
            for v in value:
                iv = TMDbWorker._coerce_int(v)
                if iv is not None:
                    out.append(iv)
            return out
        if isinstance(value, str):
            parts = [p.strip() for p in value.split(",") if p.strip()]
            out = []
            for p in parts:
                iv = TMDbWorker._coerce_int(p)
                if iv is not None:
                    out.append(iv)
            return out
        # best-effort single item
        iv = TMDbWorker._coerce_int(value)
        return [iv] if iv is not None else None

    # -------------------------- search & recommend --------------------------
    async def search_movie(
        self,
        *,
        query: str,
        year: Optional[int] = None,
        primary_release_year: Optional[int] = None,
        language: str = "en-US",
        page: int = 1,
        response_level: Optional[str] = None,
    ) -> Dict[str, Any]:
        rl = self._coerce_response_level(response_level)
        return await self.client.search_movie(query, year, primary_release_year, language, page, rl)

    async def recommendations(
        self,
        *,
        tmdb_id: int,
        language: str = "en-US",
        page: int = 1,
        response_level: Optional[str] = None,
    ) -> Dict[str, Any]:
        rl = self._coerce_response_level(response_level)
        return await self.client.recommendations(tmdb_id, language, page, rl)

    # -------------------------- discovery --------------------------
    async def discover_movies(
        self,
        *,
        sort_by: str = "popularity.desc",
        year: Optional[int] = None,
        primary_release_year: Optional[int] = None,
        with_genres: Optional[List[int]] = None,
        without_genres: Optional[List[int]] = None,
        with_cast: Optional[List[int]] = None,
        with_crew: Optional[List[int]] = None,
        with_keywords: Optional[List[int]] = None,
        with_runtime_gte: Optional[int] = None,
        with_runtime_lte: Optional[int] = None,
        with_original_language: Optional[str] = None,
        language: str = "en-US",
        page: int = 1,
        response_level: Optional[str] = None,
    ) -> Dict[str, Any]:
        rl = self._coerce_response_level(response_level)
        return await self.client.discover_movies(
            sort_by=sort_by,
            year=year,
            primary_release_year=primary_release_year,
            with_genres=self._coerce_int_list(with_genres) if with_genres is not None else None,
            without_genres=self._coerce_int_list(without_genres) if without_genres is not None else None,
            with_cast=self._coerce_int_list(with_cast) if with_cast is not None else None,
            with_crew=self._coerce_int_list(with_crew) if with_crew is not None else None,
            with_keywords=self._coerce_int_list(with_keywords) if with_keywords is not None else None,
            with_runtime_gte=self._coerce_int(with_runtime_gte),
            with_runtime_lte=self._coerce_int(with_runtime_lte),
            with_original_language=with_original_language,
            language=language,
            page=page,
            response_level=rl,
        )

    async def discover_tv(
        self,
        *,
        sort_by: str = "popularity.desc",
        first_air_date_year: Optional[int] = None,
        with_genres: Optional[List[int]] = None,
        without_genres: Optional[List[int]] = None,
        with_cast: Optional[List[int]] = None,
        with_crew: Optional[List[int]] = None,
        with_keywords: Optional[List[int]] = None,
        with_runtime_gte: Optional[int] = None,
        with_runtime_lte: Optional[int] = None,
        with_original_language: Optional[str] = None,
        language: str = "en-US",
        page: int = 1,
        response_level: Optional[str] = None,
    ) -> Dict[str, Any]:
        rl = self._coerce_response_level(response_level)
        return await self.client.discover_tv(
            sort_by=sort_by,
            first_air_date_year=first_air_date_year,
            with_genres=self._coerce_int_list(with_genres) if with_genres is not None else None,
            without_genres=self._coerce_int_list(without_genres) if without_genres is not None else None,
            with_cast=self._coerce_int_list(with_cast) if with_cast is not None else None,
            with_crew=self._coerce_int_list(with_crew) if with_crew is not None else None,
            with_keywords=self._coerce_int_list(with_keywords) if with_keywords is not None else None,
            with_runtime_gte=self._coerce_int(with_runtime_gte),
            with_runtime_lte=self._coerce_int(with_runtime_lte),
            with_original_language=with_original_language,
            language=language,
            page=page,
            response_level=rl,
        )

    # -------------------------- curated lists --------------------------
    async def trending(self, *, media_type: str = "all", time_window: str = "week", language: str = "en-US", response_level: Optional[str] = None) -> Dict[str, Any]:
        rl = self._coerce_response_level(response_level)
        return await self.client.trending(media_type, time_window, language, rl)

    async def popular_movies(self, *, language: str = "en-US", page: int = 1, response_level: Optional[str] = None) -> Dict[str, Any]:
        rl = self._coerce_response_level(response_level)
        return await self.client.popular_movies(language, page, rl)

    async def top_rated_movies(self, *, language: str = "en-US", page: int = 1, response_level: Optional[str] = None) -> Dict[str, Any]:
        rl = self._coerce_response_level(response_level)
        return await self.client.top_rated_movies(language, page, rl)

    async def upcoming_movies(self, *, language: str = "en-US", page: int = 1, response_level: Optional[str] = None) -> Dict[str, Any]:
        rl = self._coerce_response_level(response_level)
        return await self.client.upcoming_movies(language, page, rl)

    async def now_playing_movies(self, *, language: str = "en-US", page: int = 1, response_level: Optional[str] = None) -> Dict[str, Any]:
        rl = self._coerce_response_level(response_level)
        return await self.client.now_playing_movies(language, page, rl)

    async def popular_tv(self, *, language: str = "en-US", page: int = 1, response_level: Optional[str] = None) -> Dict[str, Any]:
        rl = self._coerce_response_level(response_level)
        return await self.client.popular_tv(language, page, rl)

    async def top_rated_tv(self, *, language: str = "en-US", page: int = 1, response_level: Optional[str] = None) -> Dict[str, Any]:
        rl = self._coerce_response_level(response_level)
        return await self.client.top_rated_tv(language, page, rl)

    async def on_the_air_tv(self, *, language: str = "en-US", page: int = 1, response_level: Optional[str] = None) -> Dict[str, Any]:
        rl = self._coerce_response_level(response_level)
        return await self.client.on_the_air_tv(language, page, rl)

    async def airing_today_tv(self, *, language: str = "en-US", page: int = 1, response_level: Optional[str] = None) -> Dict[str, Any]:
        rl = self._coerce_response_level(response_level)
        return await self.client.airing_today_tv(language, page, rl)

    # -------------------------- details & similar --------------------------
    async def movie_details(self, *, movie_id: int, language: str = "en-US", append_to_response: Optional[str] = None, response_level: Optional[str] = None) -> Dict[str, Any]:
        rl = self._coerce_response_level(response_level, default="detailed")
        return await self.client.movie_details(movie_id, language, append_to_response, rl)

    async def tv_details(self, *, tv_id: int, language: str = "en-US", append_to_response: Optional[str] = None, response_level: Optional[str] = None) -> Dict[str, Any]:
        rl = self._coerce_response_level(response_level, default="detailed")
        return await self.client.tv_details(tv_id, language, append_to_response, rl)

    async def similar_movies(self, *, movie_id: int, language: str = "en-US", page: int = 1, response_level: Optional[str] = None) -> Dict[str, Any]:
        rl = self._coerce_response_level(response_level)
        return await self.client.similar_movies(movie_id, language, page, rl)

    async def similar_tv(self, *, tv_id: int, language: str = "en-US", page: int = 1, response_level: Optional[str] = None) -> Dict[str, Any]:
        rl = self._coerce_response_level(response_level)
        return await self.client.similar_tv(tv_id, language, page, rl)

    # -------------------------- search misc --------------------------
    async def search_tv(self, *, query: str, first_air_date_year: Optional[int] = None, language: str = "en-US", page: int = 1, response_level: Optional[str] = None) -> Dict[str, Any]:
        rl = self._coerce_response_level(response_level)
        return await self.client.search_tv(query, first_air_date_year, language, page, rl)

    async def search_multi(self, *, query: str, language: str = "en-US", page: int = 1, response_level: Optional[str] = None) -> Dict[str, Any]:
        rl = self._coerce_response_level(response_level)
        return await self.client.search_multi(query, language, page, rl)

    async def search_person(self, *, query: str, language: str = "en-US", page: int = 1, response_level: Optional[str] = None) -> Dict[str, Any]:
        rl = self._coerce_response_level(response_level)
        return await self.client.search_person(query, language, page, rl)

    async def genres(self, *, media_type: str = "movie", language: str = "en-US") -> Dict[str, Any]:
        return await self.client.genres(media_type, language)

    async def collection_details(self, *, collection_id: int, language: str = "en-US") -> Dict[str, Any]:
        return await self.client.collection_details(collection_id, language)

    async def watch_providers_movie(self, *, movie_id: int, language: str = "en-US") -> Dict[str, Any]:
        return await self.client.watch_providers_movie(movie_id, language)

    async def watch_providers_tv(self, *, tv_id: int, language: str = "en-US") -> Dict[str, Any]:
        return await self.client.watch_providers_tv(tv_id, language)


