from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Tuple
from pathlib import Path
import json
import asyncio

from .tool_impl import (
    make_search_plex,
    make_set_plex_rating,
    make_get_plex_library_sections,
    make_get_plex_recently_added,
    make_get_plex_on_deck,
    make_get_plex_continue_watching,
    make_get_plex_unwatched,
    make_get_plex_collections,
    make_get_plex_playlists,
    make_get_plex_similar_items,
    make_get_plex_extras,
    make_get_plex_playback_status,
    make_get_plex_watch_history,
    make_get_plex_item_details,
    make_tmdb_search,
    make_tmdb_recommendations,
    make_tmdb_discover_movies,
    make_tmdb_discover_tv,
    make_tmdb_trending,
    make_tmdb_popular_movies,
    make_tmdb_top_rated_movies,
    make_tmdb_upcoming_movies,
    make_tmdb_now_playing_movies,
    make_tmdb_popular_tv,
    make_tmdb_top_rated_tv,
    make_tmdb_on_the_air_tv,
    make_tmdb_airing_today_tv,
    make_tmdb_movie_details,
    make_tmdb_tv_details,
    make_tmdb_similar_movies,
    make_tmdb_similar_tv,
    make_tmdb_search_tv,
    make_tmdb_search_multi,
    make_tmdb_search_person,
    make_tmdb_genres,
    make_tmdb_collection_details,
    make_tmdb_watch_providers_movie,
    make_tmdb_watch_providers_tv,
    make_radarr_lookup,
    make_radarr_add_movie,
    make_radarr_get_movies,
    make_radarr_update_movie,
    make_radarr_delete_movie,
    make_radarr_search_movie,
    make_radarr_search_missing,
    make_radarr_search_cutoff,
    make_radarr_get_queue,
    make_radarr_get_wanted,
    make_radarr_get_calendar,
    make_radarr_get_blacklist,
    make_radarr_clear_blacklist,
    make_radarr_system_status,
    make_radarr_health,
    make_radarr_disk_space,
    make_radarr_quality_profiles,
    make_radarr_root_folders,
    make_radarr_get_indexers,
    make_radarr_get_download_clients,
    make_sonarr_lookup,
    make_sonarr_add_series,
    make_sonarr_get_series,
    make_sonarr_update_series,
    make_sonarr_delete_series,
    make_sonarr_get_episodes,
    make_sonarr_monitor_episodes,
    make_sonarr_search_series,
    make_sonarr_search_missing,
    make_sonarr_get_queue,
    make_sonarr_get_wanted,
    make_sonarr_get_calendar,
    make_sonarr_system_status,
    make_sonarr_health,
    make_sonarr_disk_space,
    make_sonarr_quality_profiles,
    make_sonarr_root_folders,
    # Enhanced Sonarr Tools
    make_sonarr_monitor_season,
    make_sonarr_monitor_episodes_by_season,
    make_sonarr_search_season,
    make_sonarr_search_episode,
    make_sonarr_search_episodes,
    make_sonarr_get_series_summary,
    make_sonarr_get_season_summary,
    make_sonarr_get_season_details,
    make_sonarr_get_episode_file_info,
    make_sonarr_episode_fallback_search,
    make_sonarr_quality_fallback,
    make_read_household_preferences,
    make_search_household_preferences,
    make_update_household_preferences,
    make_query_household_preferences,
)


ToolCallable = Callable[[dict], Awaitable[dict]]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolCallable] = {}

    def register(self, name: str, fn: ToolCallable) -> None:
        self._tools[name] = fn

    def get(self, name: str) -> ToolCallable:
        return self._tools[name]

    def schema_map(self) -> Dict[str, str]:
        return {name: "JSON args per tool" for name in sorted(self._tools.keys())}


def _define_openai_tools() -> List[Dict[str, Any]]:
    def fn(name: str, description: str, params: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {"type": "object", "properties": params, "additionalProperties": False},
            },
        }

    return [
        fn("search_plex", "Search Plex library by title with advanced filtering options.", {
            "query": {"type": ["string", "null"], "description": "Search query (optional - if not provided, returns all movies)"},
            "limit": {"type": ["integer", "null"], "description": "Maximum number of results to return (default: 20)"},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]},
            "filters": {
                "type": ["object", "null"],
                "description": "Advanced filtering options (only available with standard/detailed response levels)",
                "properties": {
                    "year_min": {"type": ["integer", "null"], "description": "Minimum year filter"},
                    "year_max": {"type": ["integer", "null"], "description": "Maximum year filter"},
                    "genres": {"type": ["array", "null"], "items": {"type": "string"}, "description": "List of genres (any match is sufficient)"},
                    "actors": {"type": ["array", "null"], "items": {"type": "string"}, "description": "List of actors (any match is sufficient)"},
                    "directors": {"type": ["array", "null"], "items": {"type": "string"}, "description": "List of directors (any match is sufficient)"},
                    "content_rating": {"type": ["string", "null"], "description": "Content rating filter (e.g., 'PG-13', 'R')"},
                    "rating_min": {"type": ["number", "null"], "description": "Minimum rating filter (0-10)"},
                    "rating_max": {"type": ["number", "null"], "description": "Maximum rating filter (0-10)"},
                    "sort_by": {"type": ["string", "null"], "description": "Sort field (title, year, rating, addedAt, etc.)", "default": "title"},
                    "sort_order": {"type": ["string", "null"], "description": "Sort order (asc, desc)", "default": "asc"}
                }
            }
        }),
        fn("set_plex_rating", "Set a rating (1-10) for a Plex item by ratingKey.", {
            "rating_key": {"type": "integer"},
            "rating": {"type": "integer", "minimum": 1, "maximum": 10},
        }),
        
        # Enhanced Plex Tools
        fn("get_plex_library_sections", "Get available Plex library sections and their counts.", {}),
        fn("get_plex_recently_added", "Get recently added items from a Plex library section.", {
            "section_type": {"type": ["string", "null"], "description": "Library section type (movie, show, default: movie)"},
            "limit": {"type": ["integer", "null"], "description": "Maximum number of results (default: 20)"},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("get_plex_on_deck", "Get items that are 'on deck' (next to watch) in Plex.", {
            "limit": {"type": ["integer", "null"], "description": "Maximum number of results (default: 20)"},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("get_plex_continue_watching", "Get items that can be continued (partially watched) in Plex.", {
            "limit": {"type": ["integer", "null"], "description": "Maximum number of results (default: 20)"},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("get_plex_unwatched", "Get unwatched items from a Plex library section.", {
            "section_type": {"type": ["string", "null"], "description": "Library section type (movie, show, default: movie)"},
            "limit": {"type": ["integer", "null"], "description": "Maximum number of results (default: 20)"},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("get_plex_collections", "Get collections from a Plex library section.", {
            "section_type": {"type": ["string", "null"], "description": "Library section type (movie, show, default: movie)"},
            "limit": {"type": ["integer", "null"], "description": "Maximum number of results (default: 50)"},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("get_plex_playlists", "Get available Plex playlists.", {
            "limit": {"type": ["integer", "null"], "description": "Maximum number of results (default: 50)"},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("get_plex_similar_items", "Get similar items to a specific Plex item.", {
            "rating_key": {"type": "integer", "description": "Plex item rating key"},
            "limit": {"type": ["integer", "null"], "description": "Maximum number of results (default: 10)"},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("get_plex_extras", "Get extras (deleted scenes, bonus features) for a Plex item.", {
            "rating_key": {"type": "integer", "description": "Plex item rating key"}
        }),
        fn("get_plex_playback_status", "Get current playback status across all Plex clients.", {
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("get_plex_watch_history", "Get watch history for a specific Plex item.", {
            "rating_key": {"type": "integer", "description": "Plex item rating key"},
            "limit": {"type": ["integer", "null"], "description": "Maximum number of results (default: 20)"}
        }),
        fn("get_plex_item_details", "Get comprehensive details for a specific Plex item.", {
            "rating_key": {"type": "integer", "description": "Plex item rating key"},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: detailed for full metadata)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        
        fn("tmdb_search", "Search TMDb for movies with optional filtering.", {
            "query": {"type": "string", "description": "Search query"},
            "year": {"type": ["integer", "null"], "description": "Filter by year"},
            "primary_release_year": {"type": ["integer", "null"], "description": "Filter by primary release year"},
            "language": {"type": ["string", "null"], "description": "Response language", "default": "en-US"},
            "page": {"type": ["integer", "null"], "description": "Page number", "default": 1},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("tmdb_recommendations", "Get TMDb recommendations for a movie.", {
            "tmdb_id": {"type": "integer", "description": "TMDb movie ID"},
            "language": {"type": ["string", "null"], "description": "Response language", "default": "en-US"},
            "page": {"type": ["integer", "null"], "description": "Page number", "default": 1},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        
        # Enhanced TMDb Tools for Advanced Discovery
        fn("tmdb_discover_movies", "Advanced movie discovery with comprehensive filtering options.", {
            "sort_by": {"type": ["string", "null"], "description": "Sort field (popularity.desc, vote_average.desc, release_date.desc, etc.)", "default": "popularity.desc"},
            "year": {"type": ["integer", "null"], "description": "Filter by year"},
            "primary_release_year": {"type": ["integer", "null"], "description": "Filter by primary release year"},
            "with_genres": {"type": ["array", "null"], "items": {"type": "integer"}, "description": "List of genre IDs to include"},
            "without_genres": {"type": ["array", "null"], "items": {"type": "integer"}, "description": "List of genre IDs to exclude"},
            "with_cast": {"type": ["array", "null"], "items": {"type": "integer"}, "description": "List of person IDs (actors) to include"},
            "with_crew": {"type": ["array", "null"], "items": {"type": "integer"}, "description": "List of person IDs (crew) to include"},
            "with_keywords": {"type": ["array", "null"], "items": {"type": "integer"}, "description": "List of keyword IDs to include"},
            "with_runtime_gte": {"type": ["integer", "null"], "description": "Minimum runtime in minutes"},
            "with_runtime_lte": {"type": ["integer", "null"], "description": "Maximum runtime in minutes"},
            "with_original_language": {"type": ["string", "null"], "description": "Original language code (e.g., 'en', 'es')"},
            "language": {"type": ["string", "null"], "description": "Response language", "default": "en-US"},
            "page": {"type": ["integer", "null"], "description": "Page number", "default": 1},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("tmdb_discover_tv", "Advanced TV series discovery with comprehensive filtering options.", {
            "sort_by": {"type": ["string", "null"], "description": "Sort field (popularity.desc, vote_average.desc, first_air_date.desc, etc.)", "default": "popularity.desc"},
            "first_air_date_year": {"type": ["integer", "null"], "description": "Filter by first air date year"},
            "with_genres": {"type": ["array", "null"], "items": {"type": "integer"}, "description": "List of genre IDs to include"},
            "without_genres": {"type": ["array", "null"], "items": {"type": "integer"}, "description": "List of genre IDs to exclude"},
            "with_cast": {"type": ["array", "null"], "items": {"type": "integer"}, "description": "List of person IDs (actors) to include"},
            "with_crew": {"type": ["array", "null"], "items": {"type": "integer"}, "description": "List of person IDs (crew) to include"},
            "with_keywords": {"type": ["array", "null"], "items": {"type": "integer"}, "description": "List of keyword IDs to include"},
            "with_runtime_gte": {"type": ["integer", "null"], "description": "Minimum runtime in minutes"},
            "with_runtime_lte": {"type": ["integer", "null"], "description": "Maximum runtime in minutes"},
            "with_original_language": {"type": ["string", "null"], "description": "Original language code (e.g., 'en', 'es')"},
            "language": {"type": ["string", "null"], "description": "Response language", "default": "en-US"},
            "page": {"type": ["integer", "null"], "description": "Page number", "default": 1},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("tmdb_trending", "Get trending movies, TV shows, or people.", {
            "media_type": {"type": ["string", "null"], "description": "Media type (all, movie, tv, person)", "default": "all"},
            "time_window": {"type": ["string", "null"], "description": "Time window (day, week)", "default": "week"},
            "language": {"type": ["string", "null"], "description": "Response language", "default": "en-US"},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("tmdb_popular_movies", "Get popular movies.", {
            "language": {"type": ["string", "null"], "description": "Response language", "default": "en-US"},
            "page": {"type": ["integer", "null"], "description": "Page number", "default": 1},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("tmdb_top_rated_movies", "Get top rated movies.", {
            "language": {"type": ["string", "null"], "description": "Response language", "default": "en-US"},
            "page": {"type": ["integer", "null"], "description": "Page number", "default": 1},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("tmdb_upcoming_movies", "Get upcoming movie releases.", {
            "language": {"type": ["string", "null"], "description": "Response language", "default": "en-US"},
            "page": {"type": ["integer", "null"], "description": "Page number", "default": 1},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("tmdb_now_playing_movies", "Get movies currently in theaters.", {
            "language": {"type": ["string", "null"], "description": "Response language", "default": "en-US"},
            "page": {"type": ["integer", "null"], "description": "Page number", "default": 1},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("tmdb_popular_tv", "Get popular TV series.", {
            "language": {"type": ["string", "null"], "description": "Response language", "default": "en-US"},
            "page": {"type": ["integer", "null"], "description": "Page number", "default": 1},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("tmdb_top_rated_tv", "Get top rated TV series.", {
            "language": {"type": ["string", "null"], "description": "Response language", "default": "en-US"},
            "page": {"type": ["integer", "null"], "description": "Page number", "default": 1},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("tmdb_on_the_air_tv", "Get TV series currently on the air.", {
            "language": {"type": ["string", "null"], "description": "Response language", "default": "en-US"},
            "page": {"type": ["integer", "null"], "description": "Page number", "default": 1},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("tmdb_airing_today_tv", "Get TV series airing today.", {
            "language": {"type": ["string", "null"], "description": "Response language", "default": "en-US"},
            "page": {"type": ["integer", "null"], "description": "Page number", "default": 1},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("tmdb_movie_details", "Get comprehensive movie details including credits, videos, images.", {
            "movie_id": {"type": "integer", "description": "TMDb movie ID"},
            "language": {"type": ["string", "null"], "description": "Response language", "default": "en-US"},
            "append_to_response": {"type": ["string", "null"], "description": "Additional data to include (e.g., 'credits,videos,images')"},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: detailed for full metadata)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("tmdb_tv_details", "Get comprehensive TV series details.", {
            "tv_id": {"type": "integer", "description": "TMDb TV series ID"},
            "language": {"type": ["string", "null"], "description": "Response language", "default": "en-US"},
            "append_to_response": {"type": ["string", "null"], "description": "Additional data to include (e.g., 'credits,videos,images')"},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: detailed for full metadata)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("tmdb_similar_movies", "Get similar movies to a specific movie.", {
            "movie_id": {"type": "integer", "description": "TMDb movie ID"},
            "language": {"type": ["string", "null"], "description": "Response language", "default": "en-US"},
            "page": {"type": ["integer", "null"], "description": "Page number", "default": 1},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("tmdb_similar_tv", "Get similar TV series to a specific series.", {
            "tv_id": {"type": "integer", "description": "TMDb TV series ID"},
            "language": {"type": ["string", "null"], "description": "Response language", "default": "en-US"},
            "page": {"type": ["integer", "null"], "description": "Page number", "default": 1},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("tmdb_search_tv", "Search for TV series.", {
            "query": {"type": "string", "description": "Search query"},
            "first_air_date_year": {"type": ["integer", "null"], "description": "Filter by first air date year"},
            "language": {"type": ["string", "null"], "description": "Response language", "default": "en-US"},
            "page": {"type": ["integer", "null"], "description": "Page number", "default": 1},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("tmdb_search_multi", "Search across movies, TV shows, and people.", {
            "query": {"type": "string", "description": "Search query"},
            "language": {"type": ["string", "null"], "description": "Response language", "default": "en-US"},
            "page": {"type": ["integer", "null"], "description": "Page number", "default": 1},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("tmdb_search_person", "Search for people (actors, directors, etc.).", {
            "query": {"type": "string", "description": "Search query"},
            "language": {"type": ["string", "null"], "description": "Response language", "default": "en-US"},
            "page": {"type": ["integer", "null"], "description": "Page number", "default": 1},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("tmdb_genres", "Get available genres for movies or TV.", {
            "media_type": {"type": ["string", "null"], "description": "Media type (movie or tv)", "default": "movie"},
            "language": {"type": ["string", "null"], "description": "Response language", "default": "en-US"}
        }),
        fn("tmdb_collection_details", "Get details about a movie collection/franchise.", {
            "collection_id": {"type": "integer", "description": "TMDb collection ID"},
            "language": {"type": ["string", "null"], "description": "Response language", "default": "en-US"}
        }),
        fn("tmdb_watch_providers_movie", "Get where a movie can be watched (streaming, rental, etc.).", {
            "movie_id": {"type": "integer", "description": "TMDb movie ID"},
            "language": {"type": ["string", "null"], "description": "Response language", "default": "en-US"}
        }),
        fn("tmdb_watch_providers_tv", "Get where a TV series can be watched.", {
            "tv_id": {"type": "integer", "description": "TMDb TV series ID"},
            "language": {"type": ["string", "null"], "description": "Response language", "default": "en-US"}
        }),
        
        # Radarr Tools
        fn("radarr_lookup", "Lookup a movie in Radarr by search term.", {"term": {"type": "string"}}),
        fn("radarr_add_movie", "Add a movie to Radarr by TMDb id.", {
            "tmdb_id": {"type": "integer"},
            "quality_profile_id": {"type": ["integer", "null"]},
            "root_folder_path": {"type": ["string", "null"]},
            "monitored": {"type": ["boolean", "null"]},
            "search_now": {"type": ["boolean", "null"]},
        }),
        fn("radarr_get_movies", "Get all movies or a specific movie from Radarr.", {
            "movie_id": {"type": ["integer", "null"], "description": "Optional movie ID to get specific movie"}
        }),
        fn("radarr_update_movie", "Update movie settings in Radarr.", {
            "movie_id": {"type": "integer"},
            "update_data": {"type": "object", "description": "Object containing fields to update"}
        }),
        fn("radarr_delete_movie", "Delete a movie from Radarr.", {
            "movie_id": {"type": "integer"},
            "delete_files": {"type": ["boolean", "null"], "description": "Whether to delete movie files"},
            "add_import_list_exclusion": {"type": ["boolean", "null"], "description": "Whether to add to import list exclusions"}
        }),
        fn("radarr_search_movie", "Trigger a search for a specific movie in Radarr.", {
            "movie_id": {"type": "integer"}
        }),
        fn("radarr_search_missing", "Search for all missing movies in Radarr.", {}),
        fn("radarr_search_cutoff", "Search for movies that don't meet quality cutoff in Radarr.", {}),
        fn("radarr_get_queue", "Get the current download queue from Radarr.", {}),
        fn("radarr_get_wanted", "Get list of wanted (missing) movies from Radarr.", {
            "page": {"type": ["integer", "null"], "description": "Page number (default: 1)"},
            "page_size": {"type": ["integer", "null"], "description": "Page size (default: 20)"},
            "sort_key": {"type": ["string", "null"], "description": "Sort key (default: releaseDate)"},
            "sort_dir": {"type": ["string", "null"], "description": "Sort direction: asc/desc (default: desc)"}
        }),
        fn("radarr_get_calendar", "Get calendar of upcoming movie releases from Radarr.", {
            "start_date": {"type": ["string", "null"], "description": "Start date (ISO format)"},
            "end_date": {"type": ["string", "null"], "description": "End date (ISO format)"}
        }),
        fn("radarr_get_blacklist", "Get blacklisted items from Radarr.", {
            "page": {"type": ["integer", "null"], "description": "Page number (default: 1)"},
            "page_size": {"type": ["integer", "null"], "description": "Page size (default: 20)"}
        }),
        fn("radarr_clear_blacklist", "Clear all blacklisted items in Radarr.", {}),
        fn("radarr_system_status", "Get system status from Radarr.", {}),
        fn("radarr_health", "Get health status from Radarr.", {}),
        fn("radarr_disk_space", "Get disk space information from Radarr.", {}),
        fn("radarr_quality_profiles", "Get quality profiles from Radarr.", {}),
        fn("radarr_root_folders", "Get root folders from Radarr.", {}),
        fn("radarr_get_indexers", "Get indexers from Radarr.", {}),
        fn("radarr_get_download_clients", "Get download clients from Radarr.", {}),
        
        # Sonarr Tools
        fn("sonarr_lookup", "Lookup a series in Sonarr by search term.", {"term": {"type": "string"}}),
        fn("sonarr_add_series", "Add a series to Sonarr by TVDb id.", {
            "tvdb_id": {"type": "integer"},
            "quality_profile_id": {"type": ["integer", "null"]},
            "root_folder_path": {"type": ["string", "null"]},
            "monitored": {"type": ["boolean", "null"]},
            "search_for_missing": {"type": ["boolean", "null"]},
            "season_folder": {"type": ["boolean", "null"], "description": "Whether to create season folders"},
            "seasons_to_monitor": {"type": ["array", "null"], "items": {"type": "integer"}, "description": "Specific seasons to monitor (e.g., [1, 2, 3])"},
            "episodes_to_monitor": {"type": ["array", "null"], "items": {"type": "integer"}, "description": "Specific episode IDs to monitor"},
            "monitor_new_episodes": {"type": ["boolean", "null"], "description": "Whether to monitor new episodes as they air"}
        }),
        fn("sonarr_get_series", "Get all series or a specific series from Sonarr.", {
            "series_id": {"type": ["integer", "null"], "description": "Optional series ID to get specific series"}
        }),
        fn("sonarr_update_series", "Update series settings in Sonarr.", {
            "series_id": {"type": "integer"},
            "update_data": {"type": "object", "description": "Object containing fields to update"}
        }),
        fn("sonarr_delete_series", "Delete a series from Sonarr.", {
            "series_id": {"type": "integer"},
            "delete_files": {"type": ["boolean", "null"], "description": "Whether to delete series files"},
            "add_import_list_exclusion": {"type": ["boolean", "null"], "description": "Whether to add to import list exclusions"}
        }),
        fn("sonarr_get_episodes", "Get episodes from Sonarr.", {
            "series_id": {"type": ["integer", "null"], "description": "Optional series ID to get episodes for"},
            "episode_ids": {"type": ["array", "null"], "items": {"type": "integer"}, "description": "Optional list of episode IDs"}
        }),
        fn("sonarr_monitor_episodes", "Set monitoring status for episodes in Sonarr.", {
            "episode_ids": {"type": "array", "items": {"type": "integer"}, "description": "List of episode IDs"},
            "monitored": {"type": "boolean", "description": "Whether episodes should be monitored"}
        }),
        fn("sonarr_search_series", "Trigger a search for a specific series in Sonarr.", {
            "series_id": {"type": "integer"}
        }),
        fn("sonarr_search_missing", "Search for all missing episodes in Sonarr.", {}),
        fn("sonarr_get_queue", "Get the current download queue from Sonarr.", {}),
        fn("sonarr_get_wanted", "Get list of wanted (missing) episodes from Sonarr.", {
            "page": {"type": ["integer", "null"], "description": "Page number (default: 1)"},
            "page_size": {"type": ["integer", "null"], "description": "Page size (default: 20)"},
            "sort_key": {"type": ["string", "null"], "description": "Sort key (default: airDateUtc)"},
            "sort_dir": {"type": ["string", "null"], "description": "Sort direction: asc/desc (default: desc)"}
        }),
        fn("sonarr_get_calendar", "Get calendar of upcoming episode releases from Sonarr.", {
            "start_date": {"type": ["string", "null"], "description": "Start date (ISO format)"},
            "end_date": {"type": ["string", "null"], "description": "End date (ISO format)"}
        }),
        fn("sonarr_system_status", "Get system status from Sonarr.", {}),
        fn("sonarr_health", "Get health status from Sonarr.", {}),
        fn("sonarr_disk_space", "Get disk space information from Sonarr.", {}),
        fn("sonarr_quality_profiles", "Get quality profiles from Sonarr.", {}),
        fn("sonarr_root_folders", "Get root folders from Sonarr.", {}),
        
        # Enhanced Sonarr Tools
        fn("sonarr_monitor_season", "Monitor or unmonitor an entire season in Sonarr.", {
            "series_id": {"type": "integer", "description": "Series ID"},
            "season_number": {"type": "integer", "description": "Season number to monitor/unmonitor"},
            "monitored": {"type": "boolean", "description": "Whether the season should be monitored"}
        }),
        fn("sonarr_monitor_episodes_by_season", "Monitor or unmonitor all episodes in a specific season.", {
            "series_id": {"type": "integer", "description": "Series ID"},
            "season_number": {"type": "integer", "description": "Season number"},
            "monitored": {"type": "boolean", "description": "Whether episodes should be monitored"}
        }),
        fn("sonarr_search_season", "Search for all episodes in a specific season.", {
            "series_id": {"type": "integer", "description": "Series ID"},
            "season_number": {"type": "integer", "description": "Season number to search"}
        }),
        fn("sonarr_search_episode", "Search for a specific episode by ID.", {
            "episode_id": {"type": "integer", "description": "Episode ID"}
        }),
        fn("sonarr_search_episodes", "Search for multiple specific episodes by ID.", {
            "episode_ids": {"type": "array", "items": {"type": "integer"}, "description": "List of episode IDs to search for"}
        }),
        fn("sonarr_get_series_summary", "Get a concise summary of series status for efficient context usage.", {
            "series_id": {"type": "integer", "description": "Series ID"}
        }),
        fn("sonarr_get_season_summary", "Get a concise summary of season status for efficient context usage.", {
            "series_id": {"type": "integer", "description": "Series ID"},
            "season_number": {"type": "integer", "description": "Season number"}
        }),
        fn("sonarr_get_season_details", "Get detailed information about a specific season.", {
            "series_id": {"type": "integer", "description": "Series ID"},
            "season_number": {"type": "integer", "description": "Season number"}
        }),
        fn("sonarr_get_episode_file_info", "Get file information for a specific episode.", {
            "episode_id": {"type": "integer", "description": "Episode ID"}
        }),
        fn("sonarr_episode_fallback_search", "Handle episode-level search when season packs fail using sub-agent.", {
            "series_id": {"type": "integer", "description": "Series ID"},
            "season_number": {"type": "integer", "description": "Season number"},
            "series_title": {"type": "string", "description": "Series title for context"},
            "target_episodes": {"type": "array", "items": {"type": "integer"}, "description": "List of episode numbers to search for"}
        }),
        fn("sonarr_quality_fallback", "Handle quality fallback when preferred quality isn't available using sub-agent.", {
            "series_id": {"type": "integer", "description": "Series ID"},
            "target_quality": {"type": "string", "description": "Preferred quality profile"},
            "fallback_qualities": {"type": "array", "items": {"type": "string"}, "description": "List of fallback quality profiles to try"}
        }),
        
        fn("read_household_preferences", "Read the household preferences (optionally by keys or JSON path).", {
            "keys": {"type": ["array", "null"], "items": {"type": "string"}},
            "path": {"type": ["string", "null"], "description": "JSON path, e.g., profile.anchors.loved"},
            "compact": {"type": ["boolean", "null"], "description": "If true, return a compact string version"}
        }),
        fn("search_household_preferences", "Search preferences text for a query and return matched paths and snippets.", {
            "query": {"type": "string"},
            "limit": {"type": ["integer", "null"]}
        }),
        fn("update_household_preferences", "Update preferences via deep-merge patch, path set, list ops, or JSON Patch.", {
            "patch": {"type": ["object", "null"], "description": "Object to deep-merge into preferences"},
            "path": {"type": ["string", "null"], "description": "Dotted path for targeted update (e.g., 'likes.genres')"},
            "value": {"type": ["string", "number", "boolean", "object", "array", "null"], "description": "Value to set when using path"},
            "append": {"type": ["string", "number", "boolean", "object", "array", "null"], "description": "Append value to list at path (creates list if missing)"},
            "remove_value": {"type": ["string", "number", "boolean", "object", "array", "null"], "description": "Remove value from list at path (no-op if not present)"},
            "ops": {"type": ["array", "null"], "items": {"type": "object"}, "description": "JSON Patch operations: add/replace/remove with /path"}
        }),
        fn("query_household_preferences", "Query household preferences using GPT-5 and get a concise one-sentence answer.", {
            "query": {"type": "string", "description": "The question to ask about household preferences"}
        }),
    ]


def build_openai_tools_and_registry(project_root: Path, llm_client=None) -> Tuple[List[Dict[str, Any]], ToolRegistry]:
    tools = ToolRegistry()
    # Register implementations bound to this project root
    tools.register("search_plex", make_search_plex(project_root))
    tools.register("set_plex_rating", make_set_plex_rating(project_root))
    
    # Enhanced Plex tools
    tools.register("get_plex_library_sections", make_get_plex_library_sections(project_root))
    tools.register("get_plex_recently_added", make_get_plex_recently_added(project_root))
    tools.register("get_plex_on_deck", make_get_plex_on_deck(project_root))
    tools.register("get_plex_continue_watching", make_get_plex_continue_watching(project_root))
    tools.register("get_plex_unwatched", make_get_plex_unwatched(project_root))
    tools.register("get_plex_collections", make_get_plex_collections(project_root))
    tools.register("get_plex_playlists", make_get_plex_playlists(project_root))
    tools.register("get_plex_similar_items", make_get_plex_similar_items(project_root))
    tools.register("get_plex_extras", make_get_plex_extras(project_root))
    tools.register("get_plex_playback_status", make_get_plex_playback_status(project_root))
    tools.register("get_plex_watch_history", make_get_plex_watch_history(project_root))
    tools.register("get_plex_item_details", make_get_plex_item_details(project_root))
    
    tools.register("tmdb_search", make_tmdb_search(project_root))
    tools.register("tmdb_recommendations", make_tmdb_recommendations(project_root))
    
    # Enhanced TMDb Tools for Advanced Discovery
    tools.register("tmdb_discover_movies", make_tmdb_discover_movies(project_root))
    tools.register("tmdb_discover_tv", make_tmdb_discover_tv(project_root))
    tools.register("tmdb_trending", make_tmdb_trending(project_root))
    tools.register("tmdb_popular_movies", make_tmdb_popular_movies(project_root))
    tools.register("tmdb_top_rated_movies", make_tmdb_top_rated_movies(project_root))
    tools.register("tmdb_upcoming_movies", make_tmdb_upcoming_movies(project_root))
    tools.register("tmdb_now_playing_movies", make_tmdb_now_playing_movies(project_root))
    tools.register("tmdb_popular_tv", make_tmdb_popular_tv(project_root))
    tools.register("tmdb_top_rated_tv", make_tmdb_top_rated_tv(project_root))
    tools.register("tmdb_on_the_air_tv", make_tmdb_on_the_air_tv(project_root))
    tools.register("tmdb_airing_today_tv", make_tmdb_airing_today_tv(project_root))
    tools.register("tmdb_movie_details", make_tmdb_movie_details(project_root))
    tools.register("tmdb_tv_details", make_tmdb_tv_details(project_root))
    tools.register("tmdb_similar_movies", make_tmdb_similar_movies(project_root))
    tools.register("tmdb_similar_tv", make_tmdb_similar_tv(project_root))
    tools.register("tmdb_search_tv", make_tmdb_search_tv(project_root))
    tools.register("tmdb_search_multi", make_tmdb_search_multi(project_root))
    tools.register("tmdb_search_person", make_tmdb_search_person(project_root))
    tools.register("tmdb_genres", make_tmdb_genres(project_root))
    tools.register("tmdb_collection_details", make_tmdb_collection_details(project_root))
    tools.register("tmdb_watch_providers_movie", make_tmdb_watch_providers_movie(project_root))
    tools.register("tmdb_watch_providers_tv", make_tmdb_watch_providers_tv(project_root))
    
    # Radarr tools
    tools.register("radarr_lookup", make_radarr_lookup(project_root))
    tools.register("radarr_add_movie", make_radarr_add_movie(project_root))
    tools.register("radarr_get_movies", make_radarr_get_movies(project_root))
    tools.register("radarr_update_movie", make_radarr_update_movie(project_root))
    tools.register("radarr_delete_movie", make_radarr_delete_movie(project_root))
    tools.register("radarr_search_movie", make_radarr_search_movie(project_root))
    tools.register("radarr_search_missing", make_radarr_search_missing(project_root))
    tools.register("radarr_search_cutoff", make_radarr_search_cutoff(project_root))
    tools.register("radarr_get_queue", make_radarr_get_queue(project_root))
    tools.register("radarr_get_wanted", make_radarr_get_wanted(project_root))
    tools.register("radarr_get_calendar", make_radarr_get_calendar(project_root))
    tools.register("radarr_get_blacklist", make_radarr_get_blacklist(project_root))
    tools.register("radarr_clear_blacklist", make_radarr_clear_blacklist(project_root))
    tools.register("radarr_system_status", make_radarr_system_status(project_root))
    tools.register("radarr_health", make_radarr_health(project_root))
    tools.register("radarr_disk_space", make_radarr_disk_space(project_root))
    tools.register("radarr_quality_profiles", make_radarr_quality_profiles(project_root))
    tools.register("radarr_root_folders", make_radarr_root_folders(project_root))
    tools.register("radarr_get_indexers", make_radarr_get_indexers(project_root))
    tools.register("radarr_get_download_clients", make_radarr_get_download_clients(project_root))
    
    # Sonarr tools
    tools.register("sonarr_lookup", make_sonarr_lookup(project_root))
    tools.register("sonarr_add_series", make_sonarr_add_series(project_root))
    tools.register("sonarr_get_series", make_sonarr_get_series(project_root))
    tools.register("sonarr_update_series", make_sonarr_update_series(project_root))
    tools.register("sonarr_delete_series", make_sonarr_delete_series(project_root))
    tools.register("sonarr_get_episodes", make_sonarr_get_episodes(project_root))
    tools.register("sonarr_monitor_episodes", make_sonarr_monitor_episodes(project_root))
    tools.register("sonarr_search_series", make_sonarr_search_series(project_root))
    tools.register("sonarr_search_missing", make_sonarr_search_missing(project_root))
    tools.register("sonarr_get_queue", make_sonarr_get_queue(project_root))
    tools.register("sonarr_get_wanted", make_sonarr_get_wanted(project_root))
    tools.register("sonarr_get_calendar", make_sonarr_get_calendar(project_root))
    tools.register("sonarr_system_status", make_sonarr_system_status(project_root))
    tools.register("sonarr_health", make_sonarr_health(project_root))
    tools.register("sonarr_disk_space", make_sonarr_disk_space(project_root))
    tools.register("sonarr_quality_profiles", make_sonarr_quality_profiles(project_root))
    tools.register("sonarr_root_folders", make_sonarr_root_folders(project_root))
    
    # Enhanced Sonarr Tools
    tools.register("sonarr_monitor_season", make_sonarr_monitor_season(project_root))
    tools.register("sonarr_monitor_episodes_by_season", make_sonarr_monitor_episodes_by_season(project_root))
    tools.register("sonarr_search_season", make_sonarr_search_season(project_root))
    tools.register("sonarr_search_episode", make_sonarr_search_episode(project_root))
    tools.register("sonarr_search_episodes", make_sonarr_search_episodes(project_root))
    tools.register("sonarr_get_series_summary", make_sonarr_get_series_summary(project_root))
    tools.register("sonarr_get_season_summary", make_sonarr_get_season_summary(project_root))
    tools.register("sonarr_get_season_details", make_sonarr_get_season_details(project_root))
    tools.register("sonarr_get_episode_file_info", make_sonarr_get_episode_file_info(project_root))
    tools.register("sonarr_episode_fallback_search", make_sonarr_episode_fallback_search(project_root))
    tools.register("sonarr_quality_fallback", make_sonarr_quality_fallback(project_root))
    
    tools.register("read_household_preferences", make_read_household_preferences(project_root))
    tools.register("search_household_preferences", make_search_household_preferences(project_root))
    tools.register("update_household_preferences", make_update_household_preferences(project_root))
    if llm_client:
        tools.register("query_household_preferences", make_query_household_preferences(project_root, llm_client))

    openai_tools = _define_openai_tools()
    return openai_tools, tools



