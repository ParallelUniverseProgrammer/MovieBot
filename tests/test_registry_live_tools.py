import pytest
from pathlib import Path
import asyncio

from bot.tools.registry import build_openai_tools_and_registry


@pytest.mark.integration
class TestRegistryLiveTools:
    """Smoke tests to ensure all registered tools are callable against live services.

    These do not assert strict content, only that calls succeed and return JSON-serializable data.
    """

    @pytest.fixture(scope="class")
    def registry(self):
        project_root = Path(__file__).parent.parent
        _, reg = build_openai_tools_and_registry(project_root)
        return reg

    @pytest.mark.asyncio
    async def test_plex_tools_smoke(self, registry, integration_requirements_met):
        # Minimal calls using defaults; they should not raise
        for name, args in [
            ("get_plex_library_sections", {}),
            ("get_plex_recently_added", {}),
            ("get_plex_on_deck", {}),
            ("get_plex_continue_watching", {}),
            ("get_plex_unwatched", {}),
            ("get_plex_collections", {}),
            ("get_plex_playlists", {}),
            ("get_plex_playback_status", {}),
            ("get_plex_movies_4k_or_hdr", {}),
        ]:
            tool = registry.get(name)
            out = await tool(args)
            assert isinstance(out, dict)

    @pytest.mark.asyncio
    async def test_plex_tools_item_specific_smoke(self, registry, integration_requirements_met):
        # Try to fetch a recent item then call item-specific tools
        recent = await registry.get("get_plex_recently_added")({"limit": 1})
        items = recent.get("items") or []
        if not items:
            pytest.skip("No recent items to test item-specific tools")
        rating_key = items[0].get("ratingKey")
        for name, args in [
            ("get_plex_item_details", {"rating_key": rating_key}),
            ("get_plex_similar_items", {"rating_key": rating_key}),
            ("get_plex_extras", {"rating_key": rating_key}),
            ("get_plex_watch_history", {"rating_key": rating_key}),
        ]:
            tool = registry.get(name)
            out = await tool(args)
            assert isinstance(out, dict)

    @pytest.mark.asyncio
    async def test_radarr_tools_smoke(self, registry, radarr_config):
        # System/info endpoints
        for name, args in [
            ("radarr_system_status", {}),
            ("radarr_health", {}),
            ("radarr_disk_space", {}),
            ("radarr_quality_profiles", {}),
            ("radarr_root_folders", {}),
            ("radarr_get_queue", {}),
            ("radarr_get_wanted", {}),
            ("radarr_get_blacklist", {}),
            ("radarr_get_indexers", {}),
            ("radarr_get_download_clients", {}),
        ]:
            tool = registry.get(name)
            out = await tool(args)
            assert isinstance(out, dict)

    @pytest.mark.asyncio
    async def test_radarr_add_movie_tool_end_to_end(self, registry, radarr_config):
        """Exercise the radarr_add_movie tool end-to-end against live Radarr.

        Validates that the tool accepts explicit params and that the added
        movie can be confirmed via the Radarr client, then removed.
        """
        reg = registry
        assert "radarr_add_movie" in reg.schema_map()

        from integrations.radarr_client import RadarrClient
        rc = RadarrClient(radarr_config["url"], radarr_config["api_key"])
        profiles = await rc.quality_profiles()
        roots = await rc.root_folders()
        if not profiles or not roots:
            pytest.skip("Radarr profiles or roots missing")
        profile_id = int(profiles[0]["id"]) if isinstance(profiles[0], dict) else int(profiles[0].get("id"))
        root_path = roots[0]["path"] if isinstance(roots[0], dict) else roots[0].get("path")

        tmdb_id = 603
        add_args = {
            "tmdb_id": tmdb_id,
            "quality_profile_id": profile_id,
            "root_folder_path": root_path,
            "monitored": True,
            "search_now": False,
        }
        result = await reg.get("radarr_add_movie")(add_args)
        assert isinstance(result, dict)
        created_id = result.get("id") or result.get("movieId")
        assert created_id is not None

        movies = await rc.get_movies()
        assert any(m.get("tmdbId") == tmdb_id for m in movies)
        await rc.delete_movie(created_id, delete_files=False, add_import_list_exclusion=False)
        await rc.close()

    @pytest.mark.asyncio
    async def test_sonarr_tools_smoke(self, registry, sonarr_config):
        for name, args in [
            ("sonarr_system_status", {}),
            ("sonarr_health", {}),
            ("sonarr_disk_space", {}),
            ("sonarr_quality_profiles", {}),
            ("sonarr_root_folders", {}),
            ("sonarr_get_queue", {}),
            ("sonarr_get_wanted", {}),
            ("sonarr_get_calendar", {}),
        ]:
            tool = registry.get(name)
            out = await tool(args)
            assert isinstance(out, dict)


