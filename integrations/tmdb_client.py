from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import date, datetime
from enum import Enum
from integrations.http_client import SharedHttpClient
import json


class TMDbResponseLevel(Enum):
    """Response detail levels to control context usage for TMDb API responses."""
    MINIMAL = "minimal"      # Only essential fields (id, title, media_type, release_date)
    COMPACT = "compact"      # Key fields for browsing (id, title, overview, vote_average, release_date)
    STANDARD = "standard"    # Common fields (id, title, overview, genres, runtime, poster_path)
    DETAILED = "detailed"    # All available fields (current behavior)


class TMDbClient:
    def __init__(self, api_key: str, default_response_level: TMDbResponseLevel = TMDbResponseLevel.COMPACT):
        self.api_key = api_key
        self._client = SharedHttpClient.instance()
        self._base = "https://api.themoviedb.org/3"
        self.default_response_level = default_response_level

    async def close(self) -> None:
        await self._client.aclose()

    def set_response_level(self, level: TMDbResponseLevel) -> None:
        """Dynamically change the default response level for all subsequent calls."""
        self.default_response_level = level

    def get_response_level(self) -> TMDbResponseLevel:
        """Get the current default response level."""
        return self.default_response_level

    def _get_params(self, **kwargs) -> Dict[str, Any]:
        """Helper to build request parameters with API key"""
        params = {"api_key": self.api_key}
        params.update({k: v for k, v in kwargs.items() if v is not None})
        return params

    def _serialize_tmdb_item(self, item: Dict[str, Any], response_level: Optional[TMDbResponseLevel] = None) -> Dict[str, Any]:
        """Serialize a TMDb item based on the specified response level for efficiency."""
        level = response_level or self.default_response_level
        
        if level == TMDbResponseLevel.MINIMAL:
            # Only essential fields - ~70% context reduction
            return {
                "id": item.get("id"),
                "title": item.get("title") or item.get("name"),
                "media_type": item.get("media_type", "movie"),
                "release_date": item.get("release_date") or item.get("first_air_date"),
                "vote_average": item.get("vote_average")
            }
        elif level == TMDbResponseLevel.COMPACT:
            # Key fields for browsing - ~50% context reduction
            return {
                "id": item.get("id"),
                "title": item.get("title") or item.get("name"),
                "overview": item.get("overview"),
                "vote_average": item.get("vote_average"),
                "vote_count": item.get("vote_count"),
                "release_date": item.get("release_date") or item.get("first_air_date"),
                "media_type": item.get("media_type", "movie"),
                "poster_path": item.get("poster_path")
            }
        elif level == TMDbResponseLevel.STANDARD:
            # Common fields - ~30% context reduction
            result = {
                "id": item.get("id"),
                "title": item.get("title") or item.get("name"),
                "overview": item.get("overview"),
                "vote_average": item.get("vote_average"),
                "vote_count": item.get("vote_count"),
                "release_date": item.get("release_date") or item.get("first_air_date"),
                "media_type": item.get("media_type", "movie"),
                "poster_path": item.get("poster_path"),
                "backdrop_path": item.get("backdrop_path"),
                "popularity": item.get("popularity"),
                "original_language": item.get("original_language"),
                "original_title": item.get("original_title") or item.get("original_name")
            }
            
            # Add genres if available
            if "genres" in item:
                result["genres"] = [{"id": g.get("id"), "name": g.get("name")} for g in item.get("genres", [])]
            
            # Add runtime for movies
            if "runtime" in item:
                result["runtime"] = item.get("runtime")
            
            # Add episode runtime for TV
            if "episode_run_time" in item:
                result["episode_run_time"] = item.get("episode_run_time")
            
            return result
        else:  # DETAILED
            # All available fields (current behavior)
            return item

    def _serialize_tmdb_list(self, data: Dict[str, Any], response_level: Optional[TMDbResponseLevel] = None) -> Dict[str, Any]:
        """Serialize a TMDb list response (search results, recommendations, etc.) with configurable detail."""
        level = response_level or self.default_response_level
        
        result = {
            "page": data.get("page"),
            "total_pages": data.get("total_pages"),
            "total_results": data.get("total_results"),
            "results": []
        }
        
        # Serialize each result item
        for item in data.get("results", []):
            serialized_item = self._serialize_tmdb_item(item, level)
            result["results"].append(serialized_item)
        
        return result

    async def search_movie(self, query: str, year: Optional[int] = None, 
                          primary_release_year: Optional[int] = None,
                          language: str = "en-US", page: int = 1, 
                          response_level: Optional[TMDbResponseLevel] = None) -> Dict[str, Any]:
        """Enhanced movie search with filtering options and configurable response detail."""
        params = self._get_params(
            query=query, year=year, primary_release_year=primary_release_year,
            language=language, page=page
        )
        resp = await self._client.request("GET", f"{self._base}/search/movie", params=params)
        data = await resp.json()
        return self._serialize_tmdb_list(data, response_level)

    async def search_tv(self, query: str, first_air_date_year: Optional[int] = None,
                        language: str = "en-US", page: int = 1, 
                        response_level: Optional[TMDbResponseLevel] = None) -> Dict[str, Any]:
        """Search for TV series with configurable response detail."""
        params = self._get_params(
            query=query, first_air_date_year=first_air_date_year,
            language=language, page=page
        )
        r = await self._client.get("/search/tv", params=params)
        r.raise_for_status()
        data = r.json()
        return self._serialize_tmdb_list(data, response_level)

    async def search_multi(self, query: str, language: str = "en-US", 
                          page: int = 1, response_level: Optional[TMDbResponseLevel] = None) -> Dict[str, Any]:
        """Search across movies, TV shows, and people with configurable response detail."""
        params = self._get_params(query=query, language=language, page=page)
        r = await self._client.get("/search/multi", params=params)
        r.raise_for_status()
        data = r.json()
        return self._serialize_tmdb_list(data, response_level)

    async def movie_details(self, movie_id: int, language: str = "en-US",
                           append_to_response: Optional[str] = None, 
                           response_level: Optional[TMDbResponseLevel] = None) -> Dict[str, Any]:
        """Get comprehensive movie details including credits, videos, images with configurable response detail."""
        params = self._get_params(language=language)
        if append_to_response:
            params["append_to_response"] = append_to_response
        
        r = await self._client.get(f"/movie/{movie_id}", params=params)
        r.raise_for_status()
        data = r.json()
        return self._serialize_tmdb_item(data, response_level)

    async def tv_details(self, tv_id: int, language: str = "en-US",
                        append_to_response: Optional[str] = None, 
                        response_level: Optional[TMDbResponseLevel] = None) -> Dict[str, Any]:
        """Get comprehensive TV series details with configurable response detail."""
        params = self._get_params(language=language)
        if append_to_response:
            params["append_to_response"] = append_to_response
        
        r = await self._client.get(f"/tv/{tv_id}", params=params)
        r.raise_for_status()
        data = r.json()
        return self._serialize_tmdb_item(data, response_level)

    async def recommendations(self, tmdb_id: int, language: str = "en-US", 
                            page: int = 1, response_level: Optional[TMDbResponseLevel] = None) -> Dict[str, Any]:
        """Get movie recommendations with configurable response detail."""
        params = self._get_params(language=language, page=page)
        r = await self._client.get(f"/movie/{tmdb_id}/recommendations", params=params)
        r.raise_for_status()
        data = r.json()
        return self._serialize_tmdb_list(data, response_level)

    async def similar_movies(self, movie_id: int, language: str = "en-US",
                           page: int = 1, response_level: Optional[TMDbResponseLevel] = None) -> Dict[str, Any]:
        """Get similar movies with configurable response detail."""
        params = self._get_params(language=language, page=page)
        r = await self._client.get(f"/movie/{movie_id}/similar", params=params)
        r.raise_for_status()
        data = r.json()
        return self._serialize_tmdb_list(data, response_level)

    async def similar_tv(self, tv_id: int, language: str = "en-US",
                        page: int = 1, response_level: Optional[TMDbResponseLevel] = None) -> Dict[str, Any]:
        """Get similar TV series with configurable response detail."""
        params = self._get_params(language=language, page=page)
        r = await self._client.get(f"/tv/{tv_id}/similar", params=params)
        r.raise_for_status()
        data = r.json()
        return self._serialize_tmdb_list(data, response_level)

    async def discover_movies(self, sort_by: str = "popularity.desc",
                            year: Optional[int] = None, 
                            primary_release_year: Optional[int] = None,
                            with_genres: Optional[List[int]] = None,
                            without_genres: Optional[List[int]] = None,
                            with_cast: Optional[List[int]] = None,
                            with_crew: Optional[List[int]] = None,
                            with_keywords: Optional[List[int]] = None,
                            with_runtime_gte: Optional[int] = None,
                            with_runtime_lte: Optional[int] = None,
                            with_release_type: Optional[int] = None,
                            with_original_language: Optional[str] = None,
                            with_watch_providers: Optional[List[int]] = None,
                            watch_region: Optional[str] = None,
                            language: str = "en-US", page: int = 1, 
                            response_level: Optional[TMDbResponseLevel] = None) -> Dict[str, Any]:
        """Advanced movie discovery with comprehensive filtering and configurable response detail."""
        params = self._get_params(
            sort_by=sort_by, year=year, primary_release_year=primary_release_year,
            with_genres=",".join(map(str, with_genres)) if with_genres else None,
            without_genres=",".join(map(str, without_genres)) if without_genres else None,
            with_cast=",".join(map(str, with_cast)) if with_cast else None,
            with_crew=",".join(map(str, with_crew)) if with_crew else None,
            with_keywords=",".join(map(str, with_keywords)) if with_keywords else None,
            with_runtime_gte=with_runtime_gte, with_runtime_lte=with_runtime_lte,
            with_release_type=with_release_type, with_original_language=with_original_language,
            with_watch_providers=",".join(map(str, with_watch_providers)) if with_watch_providers else None,
            watch_region=watch_region, language=language, page=page
        )
        r = await self._client.get("/discover/movie", params=params)
        r.raise_for_status()
        data = r.json()
        return self._serialize_tmdb_list(data, response_level)

    async def discover_tv(self, sort_by: str = "popularity.desc",
                         first_air_date_year: Optional[int] = None,
                         with_genres: Optional[List[int]] = None,
                         without_genres: Optional[List[int]] = None,
                         with_cast: Optional[List[int]] = None,
                         with_crew: Optional[List[int]] = None,
                         with_keywords: Optional[List[int]] = None,
                         with_runtime_gte: Optional[int] = None,
                         with_runtime_lte: Optional[int] = None,
                         with_original_language: Optional[str] = None,
                         with_watch_providers: Optional[List[int]] = None,
                         watch_region: Optional[str] = None,
                         language: str = "en-US", page: int = 1, 
                         response_level: Optional[TMDbResponseLevel] = None) -> Dict[str, Any]:
        """Advanced TV discovery with comprehensive filtering and configurable response detail."""
        params = self._get_params(
            sort_by=sort_by, first_air_date_year=first_air_date_year,
            with_genres=",".join(map(str, with_genres)) if with_genres else None,
            without_genres=",".join(map(str, without_genres)) if without_genres else None,
            with_cast=",".join(map(str, with_cast)) if with_cast else None,
            with_crew=",".join(map(str, with_crew)) if with_crew else None,
            with_keywords=",".join(map(str, with_keywords)) if with_keywords else None,
            with_runtime_gte=with_runtime_gte, with_runtime_lte=with_runtime_lte,
            with_original_language=with_original_language,
            with_watch_providers=",".join(map(str, with_watch_providers)) if with_watch_providers else None,
            watch_region=watch_region, language=language, page=page
        )
        r = await self._client.get("/discover/tv", params=params)
        r.raise_for_status()
        data = r.json()
        return self._serialize_tmdb_list(data, response_level)

    async def trending(self, media_type: str = "all", time_window: str = "week",
                      language: str = "en-US", response_level: Optional[TMDbResponseLevel] = None) -> Dict[str, Any]:
        """Get trending movies, TV shows, or people with configurable response detail."""
        params = self._get_params(language=language)
        r = await self._client.get(f"/trending/{media_type}/{time_window}", params=params)
        r.raise_for_status()
        data = r.json()
        return self._serialize_tmdb_list(data, response_level)

    async def popular_movies(self, language: str = "en-US", page: int = 1, 
                           response_level: Optional[TMDbResponseLevel] = None) -> Dict[str, Any]:
        """Get popular movies with configurable response detail."""
        params = self._get_params(language=language, page=page)
        r = await self._client.get("/movie/popular", params=params)
        r.raise_for_status()
        data = r.json()
        return self._serialize_tmdb_list(data, response_level)

    async def top_rated_movies(self, language: str = "en-US", page: int = 1, 
                              response_level: Optional[TMDbResponseLevel] = None) -> Dict[str, Any]:
        """Get top rated movies with configurable response detail."""
        params = self._get_params(language=language, page=page)
        r = await self._client.get("/movie/top_rated", params=params)
        r.raise_for_status()
        data = r.json()
        return self._serialize_tmdb_list(data, response_level)

    async def upcoming_movies(self, language: str = "en-US", page: int = 1, 
                             response_level: Optional[TMDbResponseLevel] = None) -> Dict[str, Any]:
        """Get upcoming movie releases with configurable response detail."""
        params = self._get_params(language=language, page=page)
        r = await self._client.get("/movie/upcoming", params=params)
        r.raise_for_status()
        data = r.json()
        return self._serialize_tmdb_list(data, response_level)

    async def now_playing_movies(self, language: str = "en-US", page: int = 1, 
                                response_level: Optional[TMDbResponseLevel] = None) -> Dict[str, Any]:
        """Get movies currently in theaters with configurable response detail."""
        params = self._get_params(language=language, page=page)
        r = await self._client.get("/movie/now_playing", params=params)
        r.raise_for_status()
        data = r.json()
        return self._serialize_tmdb_list(data, response_level)

    async def popular_tv(self, language: str = "en-US", page: int = 1, 
                         response_level: Optional[TMDbResponseLevel] = None) -> Dict[str, Any]:
        """Get popular TV series with configurable response detail."""
        params = self._get_params(language=language, page=page)
        r = await self._client.get("/tv/popular", params=params)
        r.raise_for_status()
        data = r.json()
        return self._serialize_tmdb_list(data, response_level)

    async def top_rated_tv(self, language: str = "en-US", page: int = 1, 
                           response_level: Optional[TMDbResponseLevel] = None) -> Dict[str, Any]:
        """Get top rated TV series with configurable response detail."""
        params = self._get_params(language=language, page=page)
        r = await self._client.get("/tv/top_rated", params=params)
        r.raise_for_status()
        data = r.json()
        return self._serialize_tmdb_list(data, response_level)

    async def on_the_air_tv(self, language: str = "en-US", page: int = 1, 
                            response_level: Optional[TMDbResponseLevel] = None) -> Dict[str, Any]:
        """Get TV series currently on the air with configurable response detail."""
        params = self._get_params(language=language, page=page)
        r = await self._client.get("/tv/on_the_air", params=params)
        r.raise_for_status()
        data = r.json()
        return self._serialize_tmdb_list(data, response_level)

    async def airing_today_tv(self, language: str = "en-US", page: int = 1, 
                              response_level: Optional[TMDbResponseLevel] = None) -> Dict[str, Any]:
        """Get TV series airing today with configurable response detail."""
        params = self._get_params(language=language, page=page)
        r = await self._client.get("/tv/airing_today", params=params)
        r.raise_for_status()
        data = r.json()
        return self._serialize_tmdb_list(data, response_level)

    async def genres(self, media_type: str = "movie", language: str = "en-US") -> Dict[str, Any]:
        """Get available genres for movies or TV"""
        params = self._get_params(language=language)
        r = await self._client.get(f"/genre/{media_type}/list", params=params)
        r.raise_for_status()
        return r.json()

    async def keywords(self, media_type: str = "movie", language: str = "en-US") -> Dict[str, Any]:
        """Get available keywords for movies or TV"""
        params = self._get_params(language=language)
        r = await self._client.get(f"/keyword/{media_type}/list", params=params)
        r.raise_for_status()
        return r.json()

    async def movie_credits(self, movie_id: int, language: str = "en-US") -> Dict[str, Any]:
        """Get cast and crew for a movie"""
        params = self._get_params(language=language)
        r = await self._client.get(f"/movie/{movie_id}/credits", params=params)
        r.raise_for_status()
        return r.json()

    async def tv_credits(self, tv_id: int, language: str = "en-US") -> Dict[str, Any]:
        """Get cast and crew for a TV series"""
        params = self._get_params(language=language)
        r = await self._client.get(f"/tv/{tv_id}/credits", params=params)
        r.raise_for_status()
        return r.json()

    async def movie_videos(self, movie_id: int, language: str = "en-US") -> Dict[str, Any]:
        """Get videos (trailers, clips) for a movie"""
        params = self._get_params(language=language)
        r = await self._client.get(f"/movie/{movie_id}/videos", params=params)
        r.raise_for_status()
        return r.json()

    async def tv_videos(self, tv_id: int, language: str = "en-US") -> Dict[str, Any]:
        """Get videos for a TV series"""
        params = self._get_params(language=language)
        r = await self._client.get(f"/tv/{tv_id}/videos", params=params)
        r.raise_for_status()
        return r.json()

    async def movie_images(self, movie_id: int, language: str = "en-US") -> Dict[str, Any]:
        """Get images (posters, backdrops) for a movie"""
        params = self._get_params(language=language)
        r = await self._client.get(f"/movie/{movie_id}/images", params=params)
        r.raise_for_status()
        return r.json()

    async def tv_images(self, tv_id: int, language: str = "en-US") -> Dict[str, Any]:
        """Get images for a TV series"""
        params = self._get_params(language=language)
        r = await self._client.get(f"/tv/{tv_id}/images", params=params)
        r.raise_for_status()
        return r.json()

    async def movie_reviews(self, movie_id: int, language: str = "en-US", page: int = 1) -> Dict[str, Any]:
        """Get reviews for a movie"""
        params = self._get_params(language=language, page=page)
        r = await self._client.get(f"/movie/{movie_id}/reviews", params=params)
        r.raise_for_status()
        return r.json()

    async def collection_details(self, collection_id: int, language: str = "en-US") -> Dict[str, Any]:
        """Get details about a movie collection/franchise"""
        params = self._get_params(language=language)
        r = await self._client.get(f"/collection/{collection_id}", params=params)
        r.raise_for_status()
        return r.json()

    async def person_details(self, person_id: int, language: str = "en-US",
                           append_to_response: Optional[str] = None) -> Dict[str, Any]:
        """Get details about a person (actor, director, etc.)"""
        params = self._get_params(language=language)
        if append_to_response:
            params["append_to_response"] = append_to_response
        
        r = await self._client.get(f"/person/{person_id}", params=params)
        r.raise_for_status()
        return r.json()

    async def person_movie_credits(self, person_id: int, language: str = "en-US") -> Dict[str, Any]:
        """Get movie credits for a person"""
        params = self._get_params(language=language)
        r = await self._client.get(f"/person/{person_id}/movie_credits", params=params)
        r.raise_for_status()
        return r.json()

    async def person_tv_credits(self, person_id: int, language: str = "en-US") -> Dict[str, Any]:
        """Get TV credits for a person"""
        params = self._get_params(language=language)
        r = await self._client.get(f"/person/{person_id}/tv_credits", params=params)
        r.raise_for_status()
        return r.json()

    async def search_person(self, query: str, language: str = "en-US", page: int = 1, 
                           response_level: Optional[TMDbResponseLevel] = None) -> Dict[str, Any]:
        """Search for people (actors, directors, etc.) with configurable response detail."""
        params = self._get_params(query=query, language=language, page=page)
        r = await self._client.get("/search/person", params=params)
        r.raise_for_status()
        data = r.json()
        return self._serialize_tmdb_list(data, response_level)

    async def movie_changes(self, movie_id: int, start_date: Optional[str] = None,
                           end_date: Optional[str] = None) -> Dict[str, Any]:
        """Get changes made to a movie (for tracking updates)"""
        params = self._get_params()
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        
        r = await self._client.get(f"/movie/{movie_id}/changes", params=params)
        r.raise_for_status()
        return r.json()

    async def tv_changes(self, tv_id: int, start_date: Optional[str] = None,
                        end_date: Optional[str] = None) -> Dict[str, Any]:
        """Get changes made to a TV series"""
        params = self._get_params()
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        
        r = await self._client.get(f"/tv/{tv_id}/changes", params=params)
        r.raise_for_status()
        return r.json()

    async def watch_providers_movie(self, movie_id: int, language: str = "en-US") -> Dict[str, Any]:
        """Get where a movie can be watched (streaming, rental, etc.)"""
        params = self._get_params(language=language)
        r = await self._client.get(f"/movie/{movie_id}/watch/providers", params=params)
        r.raise_for_status()
        return r.json()

    async def watch_providers_tv(self, tv_id: int, language: str = "en-US") -> Dict[str, Any]:
        """Get where a TV series can be watched"""
        params = self._get_params(language=language)
        r = await self._client.get(f"/tv/{tv_id}/watch/providers", params=params)
        r.raise_for_status()
        return r.json()

    async def configuration(self) -> Dict[str, Any]:
        """Get TMDb configuration (image URLs, etc.)"""
        r = await self._client.get("/configuration", params={"api_key": self.api_key})
        r.raise_for_status()
        return r.json()


