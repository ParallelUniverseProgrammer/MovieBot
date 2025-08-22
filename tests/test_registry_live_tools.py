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


