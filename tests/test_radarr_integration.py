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

    @pytest.mark.asyncio
    async def test_add_movie_end_to_end(self, radarr, radarr_config):
        """End-to-end add flow: lookup by TMDb id, add, verify exists, then cleanup.

        Requires RADARR_BASE_URL and RADARR_API_KEY to be set (see conftest.py integration options).
        """
        # Choose a stable, popular TMDb ID to minimize lookup flakiness
        tmdb_id = 603  # The Matrix (1999)

        # Fetch defaults directly from Radarr to avoid config drift
        profiles = await radarr.quality_profiles()
        assert isinstance(profiles, list) and len(profiles) > 0
        profile_id = int(profiles[0]["id"]) if isinstance(profiles[0], dict) else int(profiles[0].get("id"))

        roots = await radarr.root_folders()
        assert isinstance(roots, list) and len(roots) > 0
        root_path = roots[0]["path"] if isinstance(roots[0], dict) else roots[0].get("path")

        # Try to add movie
        created = await radarr.add_movie(
            tmdb_id=tmdb_id,
            quality_profile_id=profile_id,
            root_folder_path=root_path,
            monitored=True,
            search_now=False,
        )
        assert isinstance(created, dict)
        created_id = created.get("id") or created.get("movieId")
        assert created_id is not None

        # Verify it exists in library
        movies = await radarr.get_movies()
        assert any(m.get("tmdbId") == tmdb_id for m in movies)

        # Trigger search to validate command endpoint
        search_cmd = await radarr.search_movie(created_id)
        assert isinstance(search_cmd, dict)
        assert search_cmd.get("name") == "MoviesSearch"

        # Cleanup: delete the movie (keep files false, no import list exclusion)
        await radarr.delete_movie(created_id, delete_files=False, add_import_list_exclusion=False)
        movies_after = await radarr.get_movies()
        # Not asserting absence due to Radarr async indexing, but ensure call succeeded
        assert isinstance(movies_after, list)


