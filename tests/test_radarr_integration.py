import pytest
from integrations.radarr_client import RadarrClient


@pytest.mark.integration
class TestRadarrIntegration:
    """Integration tests against a live Radarr server."""

    @pytest.fixture(scope="class")
    def radarr(self, radarr_config):
        client = RadarrClient(radarr_config["url"], radarr_config["api_key"])
        yield client
        # Close async client
        import asyncio
        asyncio.get_event_loop().run_until_complete(client.close())

    @pytest.mark.asyncio
    async def test_system_status(self, radarr):
        status = await radarr.system_status()
        assert isinstance(status, dict)
        assert "version" in status

    @pytest.mark.asyncio
    async def test_quality_profiles_and_root_folders(self, radarr):
        profiles = await radarr.quality_profiles()
        folders = await radarr.root_folders()
        assert isinstance(profiles, list)
        assert isinstance(folders, list)

    @pytest.mark.asyncio
    async def test_queue_and_wanted(self, radarr):
        queue = await radarr.get_queue()
        wanted = await radarr.get_wanted(page=1, page_size=5)
        assert isinstance(queue, dict)
        assert isinstance(wanted, dict)

    @pytest.mark.asyncio
    async def test_lookup_search_flow(self, radarr):
        # Use a common title for lookup
        results = await radarr.lookup("Matrix")
        assert isinstance(results, list)
        # Not asserting non-empty to allow empty libraries


