from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Tuple
from pathlib import Path
import json
import asyncio

from .tool_impl import (
    make_search_plex,
    # Enhanced Sonarr Tools
    make_sonarr_episode_fallback_search,
    make_sonarr_quality_fallback,
    make_read_household_preferences,
    make_search_household_preferences,
    make_update_household_preferences,
    make_query_household_preferences,
    make_smart_recommendations,
    make_intelligent_search,
)
from .tool_impl_plex import (
    make_get_plex_movies_4k_or_hdr,
    make_set_plex_rating,
    make_get_plex_collections,
    make_get_plex_playlists,
    make_get_plex_similar_items,
    make_get_plex_extras,
    make_get_plex_playback_status,
    make_get_plex_watch_history,
    make_get_plex_item_details,
    make_plex_library_overview,
)
from .tool_impl_tmdb import (
    make_tmdb_search,
    make_tmdb_recommendations,
    make_tmdb_upcoming_movies,
    make_tmdb_now_playing_movies,
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
    make_tmdb_discovery_suite,
)
from .tool_impl_radarr import (
    make_radarr_lookup,
    make_radarr_add_movie,
    make_radarr_get_movies,
    make_radarr_update_movie,
    make_radarr_delete_movie,
    make_radarr_search_movie,
    make_radarr_search_missing,
    make_radarr_search_cutoff,
    make_radarr_get_blacklist,
    make_radarr_clear_blacklist,
    make_radarr_quality_profiles,
    make_radarr_root_folders,
    make_radarr_get_indexers,
    make_radarr_get_download_clients,
    # Enhanced Radarr Sub-Agent Tools
    make_radarr_movie_addition_fallback,
    make_radarr_activity_check,
    make_radarr_quality_fallback,
    # Bundled Tools
    make_system_health_overview,
    make_radarr_activity_overview,
)
from .tool_impl_sonarr import (
    make_sonarr_lookup,
    make_sonarr_add_series,
    make_sonarr_get_series,
    make_sonarr_update_series,
    make_sonarr_delete_series,
    make_sonarr_get_episodes,
    make_sonarr_monitor_episodes,
    make_sonarr_search_series,
    make_sonarr_search_missing,
    make_sonarr_quality_profiles,
    make_sonarr_root_folders,
    make_sonarr_monitor_season,
    make_sonarr_monitor_episodes_by_season,
    make_sonarr_search_season,
    make_sonarr_search_episode,
    make_sonarr_search_episodes,
    make_sonarr_get_series_summary,
    make_sonarr_get_season_summary,
    make_sonarr_get_season_details,
    make_sonarr_get_episode_file_info,
    make_sonarr_activity_overview,
)
from .result_cache import make_fetch_cached_result


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
        fn("fetch_cached_result", "Fetch a previously cached tool result by ref id with optional field projection and slicing.", {
            "ref_id": {"type": "string"},
            "fields": {"type": ["array", "null"], "items": {"type": "string"}},
            "start": {"type": ["integer", "null"]},
            "count": {"type": ["integer", "null"]}
        }),
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
        fn("get_plex_movies_4k_or_hdr", "List movies in Plex that are 4K or HDR (live HTTP query with OR fallbacks).", {
            "limit": {"type": ["integer", "null"], "description": "Maximum results (default: 30)"},
            "section_id": {"type": ["string", "integer", "null"], "description": "Plex library section id (auto-detected if omitted)"},
            "or_semantics": {"type": ["boolean", "null"], "description": "Attempt OR filter in single request before fallbacks (default: true)"},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, detailed (default: compact)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("set_plex_rating", "Set a rating (1-10) for a Plex item by ratingKey.", {
            "rating_key": {"type": "integer"},
            "rating": {"type": "integer", "minimum": 1, "maximum": 10},
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
        
        fn("tmdb_search", "Search TMDb for movies with optional filtering and detailed information for top results.", {
            "query": {"type": "string", "description": "Search query"},
            "year": {"type": ["integer", "null"], "description": "Filter by year"},
            "primary_release_year": {"type": ["integer", "null"], "description": "Filter by primary release year"},
            "language": {"type": ["string", "null"], "description": "Response language", "default": "en-US"},
            "page": {"type": ["integer", "null"], "description": "Page number", "default": 1},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]},
            "include_details": {"type": ["boolean", "null"], "description": "Whether to include detailed information for top results (default: true)", "default": True},
            "max_details": {"type": ["integer", "null"], "description": "Maximum number of results to fetch details for (default: 5)", "default": 5}
        }),
        fn("tmdb_recommendations", "Get TMDb recommendations for a movie.", {
            "tmdb_id": {"type": "integer", "description": "TMDb movie ID"},
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
        fn("radarr_get_blacklist", "Get blacklisted items from Radarr.", {
            "page": {"type": ["integer", "null"], "description": "Page number (default: 1)"},
            "page_size": {"type": ["integer", "null"], "description": "Page size (default: 20)"}
        }),
        fn("radarr_clear_blacklist", "Clear all blacklisted items in Radarr.", {}),
        fn("radarr_quality_profiles", "Get quality profiles from Radarr.", {}),
        fn("radarr_root_folders", "Get root folders from Radarr.", {}),
        fn("radarr_get_indexers", "Get indexers from Radarr.", {}),
        fn("radarr_get_download_clients", "Get download clients from Radarr.", {}),
        
        # Enhanced Radarr Sub-Agent Tools
        fn("radarr_movie_addition_fallback", "Add a movie to Radarr with intelligent quality fallback when preferred quality isn't available.", {
            "tmdb_id": {"type": "integer", "description": "TMDb movie ID"},
            "movie_title": {"type": "string", "description": "Movie title for context"},
            "preferred_quality": {"type": ["string", "null"], "description": "Preferred quality profile name"},
            "fallback_qualities": {"type": ["array", "null"], "description": "List of fallback quality profiles to try", "items": {"type": "string"}},
            "provider": {"type": ["string", "null"], "description": "LLM provider override"},
            "api_key": {"type": ["string", "null"], "description": "LLM API key override"}
        }),
        fn("radarr_activity_check", "Check Radarr activity status including queue, wanted movies, and upcoming releases (READ-ONLY).", {
            "check_queue": {"type": ["boolean", "null"], "description": "Whether to check the download queue (default: true)"},
            "check_wanted": {"type": ["boolean", "null"], "description": "Whether to check wanted/missing movies (default: true)"},
            "check_calendar": {"type": ["boolean", "null"], "description": "Whether to check upcoming releases (default: false)"},
            "max_results": {"type": ["integer", "null"], "description": "Maximum number of results to return per category (default: 10)"},
            "provider": {"type": ["string", "null"], "description": "LLM provider override"},
            "api_key": {"type": ["string", "null"], "description": "LLM API key override"}
        }),
        fn("radarr_quality_fallback", "Update a movie's quality profile with fallback when preferred quality isn't available.", {
            "movie_id": {"type": "integer", "description": "Radarr movie ID"},
            "movie_title": {"type": "string", "description": "Movie title for context"},
            "target_quality": {"type": "string", "description": "Preferred quality profile name"},
            "fallback_qualities": {"type": "array", "description": "List of fallback quality profiles to try", "items": {"type": "string"}},
            "provider": {"type": ["string", "null"], "description": "LLM provider override"},
            "api_key": {"type": ["string", "null"], "description": "LLM API key override"}
        }),
        
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
            "value": {
                "description": "Value to set when using path",
                "anyOf": [
                    {"type": "string"},
                    {"type": "number"},
                    {"type": "boolean"},
                    {"type": "object"},
                    {"type": "array", "items": {}},
                    {"type": "null"}
                ]
            },
            "append": {
                "description": "Append value to list at path (creates list if missing)",
                "anyOf": [
                    {"type": "string"},
                    {"type": "number"},
                    {"type": "boolean"},
                    {"type": "object"},
                    {"type": "array", "items": {}},
                    {"type": "null"}
                ]
            },
            "remove_value": {
                "description": "Remove value from list at path (no-op if not present)",
                "anyOf": [
                    {"type": "string"},
                    {"type": "number"},
                    {"type": "boolean"},
                    {"type": "object"},
                    {"type": "array", "items": {}},
                    {"type": "null"}
                ]
            },
            "ops": {"type": ["array", "null"], "items": {"type": "object"}, "description": "JSON Patch operations: add/replace/remove with /path"}
        }),
        fn("query_household_preferences", "Query household preferences using GPT-5 and get a concise one-sentence answer.", {
            "query": {"type": "string", "description": "The question to ask about household preferences"}
        }),
        fn("smart_recommendations", "AI-powered recommendations using preferences and TMDb signals via a sub-agent.", {
            "seed_tmdb_id": {"type": ["integer", "null"], "description": "Seed TMDb movie id for recommendations (optional)"},
            "prompt": {"type": ["string", "null"], "description": "Optional freeform prompt to steer recommendations"},
            "max_results": {"type": ["integer", "null"], "description": "Maximum number of items to return (default 3)"},
            "media_type": {"type": ["string", "null"], "enum": ["movie", "tv", "all"], "description": "Media type focus (default movie)"}
        }),
        fn("intelligent_search", "Intelligent search that merges TMDb multi-search with Plex search via a sub-agent.", {
            "query": {"type": "string", "description": "Raw user query"},
            "limit": {"type": ["integer", "null"], "description": "Max results for Plex search (default 10)"},
            "response_level": {"type": ["string", "null"], "enum": ["minimal", "compact", "standard", "detailed"], "description": "Plex response granularity (default compact)"}
        }),
        
        # Bundled Tools
        fn("plex_library_overview", "Get comprehensive Plex library overview including recently added, on deck, continue watching, unwatched, and library sections in parallel.", {
            "section_type": {"type": ["string", "null"], "description": "Library section type (movie, show, default: movie)"},
            "limit": {"type": ["integer", "null"], "description": "Maximum number of results per category (default: 20)"},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]}
        }),
        fn("system_health_overview", "Get comprehensive system health overview across all services (Radarr, Sonarr, Plex) in parallel.", {}),
        fn("tmdb_discovery_suite", "Get comprehensive TMDb discovery across multiple methods (trending, popular, top rated, discover) in parallel.", {
            "discovery_types": {"type": ["array", "null"], "items": {"type": "string", "enum": ["trending", "popular", "top_rated", "discover"]}, "description": "Discovery methods to include (default: all)"},
            "language": {"type": ["string", "null"], "description": "Response language", "default": "en-US"},
            "page": {"type": ["integer", "null"], "description": "Page number", "default": 1},
            "response_level": {"type": ["string", "null"], "description": "Response detail level: minimal, compact, standard, or detailed (default: compact for efficiency)", "enum": ["minimal", "compact", "standard", "detailed"]},
            "sort_by": {"type": ["string", "null"], "description": "Sort field for discover methods (default: popularity.desc)"},
            "year": {"type": ["integer", "null"], "description": "Filter by year for discover methods"},
            "primary_release_year": {"type": ["integer", "null"], "description": "Filter by primary release year for discover methods"},
            "first_air_date_year": {"type": ["integer", "null"], "description": "Filter by first air date year for discover methods"},
            "with_genres": {"type": ["array", "null"], "items": {"type": "integer"}, "description": "List of genre IDs to include for discover methods"},
            "without_genres": {"type": ["array", "null"], "items": {"type": "integer"}, "description": "List of genre IDs to exclude for discover methods"},
            "with_cast": {"type": ["array", "null"], "items": {"type": "integer"}, "description": "List of person IDs (actors) to include for discover methods"},
            "with_crew": {"type": ["array", "null"], "items": {"type": "integer"}, "description": "List of person IDs (crew) to include for discover methods"},
            "with_keywords": {"type": ["array", "null"], "items": {"type": "integer"}, "description": "List of keyword IDs to include for discover methods"},
            "with_runtime_gte": {"type": ["integer", "null"], "description": "Minimum runtime in minutes for discover methods"},
            "with_runtime_lte": {"type": ["integer", "null"], "description": "Maximum runtime in minutes for discover methods"},
            "with_original_language": {"type": ["string", "null"], "description": "Original language code for discover methods"}
        }),
        fn("radarr_activity_overview", "Get comprehensive Radarr activity overview including queue, wanted movies, and calendar in parallel.", {
            "page": {"type": ["integer", "null"], "description": "Page number for wanted movies (default: 1)"},
            "page_size": {"type": ["integer", "null"], "description": "Page size for wanted movies (default: 20)"},
            "sort_key": {"type": ["string", "null"], "description": "Sort key for wanted movies (default: releaseDate)"},
            "sort_dir": {"type": ["string", "null"], "description": "Sort direction: asc/desc (default: desc)"},
            "start_date": {"type": ["string", "null"], "description": "Start date for calendar (ISO format)"},
            "end_date": {"type": ["string", "null"], "description": "End date for calendar (ISO format)"}
        }),
        fn("sonarr_activity_overview", "Get comprehensive Sonarr activity overview including queue, wanted episodes, and calendar in parallel.", {
            "page": {"type": ["integer", "null"], "description": "Page number for wanted episodes (default: 1)"},
            "page_size": {"type": ["integer", "null"], "description": "Page size for wanted episodes (default: 20)"},
            "sort_key": {"type": ["string", "null"], "description": "Sort key for wanted episodes (default: airDateUtc)"},
            "sort_dir": {"type": ["string", "null"], "description": "Sort direction: asc/desc (default: desc)"},
            "start_date": {"type": ["string", "null"], "description": "Start date for calendar (ISO format)"},
            "end_date": {"type": ["string", "null"], "description": "End date for calendar (ISO format)"}
        }),
    ]


def build_openai_tools_and_registry(project_root: Path, llm_client=None) -> Tuple[List[Dict[str, Any]], ToolRegistry]:
    tools = ToolRegistry()
    # Register implementations bound to this project root
    tools.register("search_plex", make_search_plex(project_root))
    tools.register("get_plex_movies_4k_or_hdr", make_get_plex_movies_4k_or_hdr(project_root))
    tools.register("set_plex_rating", make_set_plex_rating(project_root))
    
    tools.register("get_plex_collections", make_get_plex_collections(project_root))
    tools.register("get_plex_playlists", make_get_plex_playlists(project_root))
    tools.register("get_plex_similar_items", make_get_plex_similar_items(project_root))
    tools.register("get_plex_extras", make_get_plex_extras(project_root))
    tools.register("get_plex_playback_status", make_get_plex_playback_status(project_root))
    tools.register("get_plex_watch_history", make_get_plex_watch_history(project_root))
    tools.register("get_plex_item_details", make_get_plex_item_details(project_root))
    
    # Bundled Plex Tools
    tools.register("plex_library_overview", make_plex_library_overview(project_root))
    
    tools.register("tmdb_search", make_tmdb_search(project_root))
    tools.register("tmdb_recommendations", make_tmdb_recommendations(project_root))
    
    # Enhanced TMDb Tools for Advanced Discovery
    tools.register("tmdb_upcoming_movies", make_tmdb_upcoming_movies(project_root))
    tools.register("tmdb_now_playing_movies", make_tmdb_now_playing_movies(project_root))
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
    
    # Bundled TMDb Tools
    tools.register("tmdb_discovery_suite", make_tmdb_discovery_suite(project_root))
    
    # Radarr tools
    tools.register("radarr_lookup", make_radarr_lookup(project_root))
    tools.register("radarr_add_movie", make_radarr_add_movie(project_root))
    tools.register("radarr_get_movies", make_radarr_get_movies(project_root))
    tools.register("radarr_update_movie", make_radarr_update_movie(project_root))
    tools.register("radarr_delete_movie", make_radarr_delete_movie(project_root))
    tools.register("radarr_search_movie", make_radarr_search_movie(project_root))
    tools.register("radarr_search_missing", make_radarr_search_missing(project_root))
    tools.register("radarr_search_cutoff", make_radarr_search_cutoff(project_root))
    tools.register("radarr_get_blacklist", make_radarr_get_blacklist(project_root))
    tools.register("radarr_clear_blacklist", make_radarr_clear_blacklist(project_root))
    tools.register("radarr_quality_profiles", make_radarr_quality_profiles(project_root))
    tools.register("radarr_root_folders", make_radarr_root_folders(project_root))
    tools.register("radarr_get_indexers", make_radarr_get_indexers(project_root))
    tools.register("radarr_get_download_clients", make_radarr_get_download_clients(project_root))
    
    # Enhanced Radarr Sub-Agent Tools
    tools.register("radarr_movie_addition_fallback", make_radarr_movie_addition_fallback(project_root))
    tools.register("radarr_activity_check", make_radarr_activity_check(project_root))
    tools.register("radarr_quality_fallback", make_radarr_quality_fallback(project_root))
    
    # Bundled Radarr Tools
    tools.register("system_health_overview", make_system_health_overview(project_root))
    tools.register("radarr_activity_overview", make_radarr_activity_overview(project_root))
    
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
    
    # Bundled Sonarr Tools
    tools.register("sonarr_activity_overview", make_sonarr_activity_overview(project_root))
    
    tools.register("read_household_preferences", make_read_household_preferences(project_root))
    tools.register("search_household_preferences", make_search_household_preferences(project_root))
    tools.register("update_household_preferences", make_update_household_preferences(project_root))
    if llm_client:
        tools.register("query_household_preferences", make_query_household_preferences(project_root, llm_client))
    tools.register("smart_recommendations", make_smart_recommendations(project_root))
    tools.register("intelligent_search", make_intelligent_search(project_root))
    # Utility: fetch cached results
    tools.register("fetch_cached_result", make_fetch_cached_result(project_root))

    openai_tools = _define_openai_tools()
    return openai_tools, tools



