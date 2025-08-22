import pytest
from integrations.sonarr_client import SonarrClient


@pytest.mark.integration
class TestSonarrIntegration:
    """Integration tests against a live Sonarr server."""

    @pytest.fixture(scope="class")
    def sonarr(self, sonarr_config):
        client = SonarrClient(sonarr_config["url"], sonarr_config["api_key"])
        yield client
        # Close async client
        import asyncio
        asyncio.get_event_loop().run_until_complete(client.close())

    @pytest.mark.asyncio
    async def test_system_status(self, sonarr):
        status = await sonarr.system_status()
        assert isinstance(status, dict)
        assert "version" in status

    @pytest.mark.asyncio
    async def test_quality_profiles_and_root_folders(self, sonarr):
        profiles = await sonarr.quality_profiles()
        folders = await sonarr.root_folders()
        assert isinstance(profiles, list)
        assert isinstance(folders, list)

    @pytest.mark.asyncio
    async def test_queue_and_wanted(self, sonarr):
        queue = await sonarr.get_queue()
        wanted = await sonarr.get_wanted(page=1, page_size=5)
        assert isinstance(queue, dict)
        assert isinstance(wanted, dict)

    @pytest.mark.asyncio
    async def test_lookup_flow(self, sonarr):
        results = await sonarr.lookup("Breaking Bad")
        assert isinstance(results, list)


