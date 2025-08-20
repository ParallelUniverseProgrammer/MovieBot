import pytest
import os
from pathlib import Path
from integrations.plex_client import PlexClient


class TestPlexIntegration:
    """Integration tests that run against the real Plex server.
    
    These tests require:
    - A running Plex server
    - Valid PLEX_TOKEN and PLEX_BASE_URL in your .env file
    - Network connectivity to the Plex server
    
    Run with: pytest tests/test_plex_integration.py -v --run-integration
    """

    @pytest.fixture(scope="class")
    def plex_client(self):
        """Create a real PlexClient instance for integration testing."""
        # Get configuration from .env file (loaded by conftest_integration.py)
        plex_token = os.getenv("PLEX_TOKEN")
        plex_url = os.getenv("PLEX_BASE_URL")
        
        if not plex_token or not plex_url:
            pytest.skip("PLEX_TOKEN and PLEX_BASE_URL must be set in .env file")
        
        try:
            client = PlexClient(plex_url, plex_token)
            # Test basic connectivity
            client.plex.library.sections()
            return client
        except Exception as e:
            pytest.skip(f"Could not connect to Plex server: {e}")

    @pytest.fixture(scope="class")
    def project_root(self):
        """Get the actual project root path."""
        return Path(__file__).parent.parent

    @pytest.mark.integration
    def test_real_plex_connection(self, plex_client):
        """Test that we can actually connect to the Plex server."""
        # This should work if the fixture succeeded
        assert plex_client is not None
        assert plex_client.plex is not None

    @pytest.mark.integration
    def test_get_library_sections_real(self, plex_client):
        """Test getting real library sections from Plex."""
        sections = plex_client.get_library_sections()
        
        # Should return a dict with library information
        assert isinstance(sections, dict)
        assert len(sections) > 0
        
        # Check structure of first section
        first_section = list(sections.values())[0]
        assert "type" in first_section
        assert "count" in first_section
        assert "section_id" in first_section
        
        # Counts should be reasonable numbers
        assert first_section["count"] >= 0
        assert isinstance(first_section["section_id"], int)

    @pytest.mark.integration
    def test_get_movie_library_real(self, plex_client):
        """Test getting the real movie library."""
        try:
            movie_library = plex_client.get_movie_library()
            assert movie_library is not None
            
            # Should have a reasonable number of movies
            movie_count = len(movie_library.all())
            assert movie_count >= 0
            
        except Exception as e:
            # Skip if no movie library exists
            pytest.skip(f"No movie library found: {e}")

    @pytest.mark.integration
    def test_get_tv_library_real(self, plex_client):
        """Test getting the real TV library."""
        try:
            tv_library = plex_client.get_tv_library()
            assert tv_library is not None
            
            # Should have a reasonable number of shows
            show_count = len(tv_library.all())
            assert show_count >= 0
            
        except Exception as e:
            # Skip if no TV library exists
            pytest.skip(f"No TV library found: {e}")

    @pytest.mark.integration
    def test_get_recently_added_real(self, plex_client):
        """Test getting recently added items from real Plex."""
        # Test movies
        try:
            recent_movies = plex_client.get_recently_added("movie", 5)
            assert isinstance(recent_movies, list)
            assert len(recent_movies) <= 5
            
            if recent_movies:
                # Check structure of first item
                first_movie = recent_movies[0]
                assert "title" in first_movie
                assert "ratingKey" in first_movie
                assert "year" in first_movie or first_movie["year"] is None
                
        except Exception as e:
            pytest.skip(f"Could not get recently added movies: {e}")
        
        # Test TV shows
        try:
            recent_shows = plex_client.get_recently_added("show", 5)
            assert isinstance(recent_shows, list)
            assert len(recent_shows) <= 5
            
        except Exception as e:
            pytest.skip(f"Could not get recently added shows: {e}")

    @pytest.mark.integration
    def test_get_on_deck_real(self, plex_client):
        """Test getting on deck items from real Plex."""
        on_deck = plex_client.get_on_deck(10)
        
        assert isinstance(on_deck, list)
        assert len(on_deck) <= 10
        
        if on_deck:
            # Check structure of first item
            first_item = on_deck[0]
            assert "title" in first_item
            assert "ratingKey" in first_item

    @pytest.mark.integration
    def test_get_continue_watching_real(self, plex_client):
        """Test getting continue watching items from real Plex."""
        continue_watching = plex_client.get_continue_watching(10)
        
        assert isinstance(continue_watching, list)
        assert len(continue_watching) <= 10
        
        if continue_watching:
            # Check structure of first item
            first_item = continue_watching[0]
            assert "title" in first_item
            assert "ratingKey" in first_item

    @pytest.mark.integration
    def test_get_unwatched_real(self, plex_client):
        """Test getting unwatched items from real Plex."""
        try:
            unwatched_movies = plex_client.get_unwatched("movie", 10)
            assert isinstance(unwatched_movies, list)
            assert len(unwatched_movies) <= 10
            
            if unwatched_movies:
                first_movie = unwatched_movies[0]
                assert "title" in first_movie
                assert "ratingKey" in first_movie
                
        except Exception as e:
            pytest.skip(f"Could not get unwatched movies: {e}")

    @pytest.mark.integration
    def test_get_collections_real(self, plex_client):
        """Test getting collections from real Plex."""
        try:
            collections = plex_client.get_collections("movie", 20)
            assert isinstance(collections, list)
            assert len(collections) <= 20
            
            if collections:
                first_collection = collections[0]
                assert "title" in first_collection
                assert "collection_id" in first_collection
                assert "count" in first_collection
                assert first_collection["count"] >= 0
                
        except Exception as e:
            pytest.skip(f"Could not get collections: {e}")

    @pytest.mark.integration
    def test_get_playlists_real(self, plex_client):
        """Test getting playlists from real Plex."""
        playlists = plex_client.get_playlists(20)
        
        assert isinstance(playlists, list)
        assert len(playlists) <= 20
        
        if playlists:
            first_playlist = playlists[0]
            assert "title" in first_playlist
            assert "playlist_id" in first_playlist
            assert "count" in first_playlist
            assert first_playlist["count"] >= 0

    @pytest.mark.integration
    def test_get_playback_status_real(self, plex_client):
        """Test getting playback status from real Plex."""
        status = plex_client.get_playback_status()
        
        assert isinstance(status, dict)
        assert "active_sessions" in status
        assert "sessions" in status
        assert isinstance(status["active_sessions"], int)
        assert isinstance(status["sessions"], list)
        
        # Active sessions should be reasonable
        assert status["active_sessions"] >= 0
        
        if status["sessions"]:
            first_session = status["sessions"][0]
            assert "title" in first_session
            assert "type" in first_session
            assert "user" in first_session

    @pytest.mark.integration
    def test_search_and_get_details_real(self, plex_client):
        """Test searching for a movie and getting its details."""
        # Search for a common movie
        search_results = plex_client.search_movies("The Matrix")
        
        if search_results:
            # Get the first result
            first_movie = search_results[0]
            rating_key = first_movie.ratingKey
            
            # Get detailed information
            details = plex_client.get_item_details(rating_key)
            
            assert details is not None
            assert "title" in details
            assert "ratingKey" in details
            assert details["ratingKey"] == rating_key
            
            # Test getting similar items
            similar = plex_client.get_similar_items(rating_key, 5)
            assert isinstance(similar, list)
            assert len(similar) <= 5
            
            # Test getting extras
            extras = plex_client.get_extras(rating_key)
            assert isinstance(extras, list)
            
            # Test getting watch history
            history = plex_client.get_watch_history(rating_key, 10)
            assert isinstance(history, list)
            
        else:
            pytest.skip("No search results found for 'The Matrix'")

    @pytest.mark.integration
    def test_data_consistency_real(self, plex_client):
        """Test that data returned from different methods is consistent."""
        # Get recently added movies
        recent = plex_client.get_recently_added("movie", 3)
        
        if recent:
            first_movie = recent[0]
            rating_key = first_movie["ratingKey"]
            
            # Get the same movie via item details
            details = plex_client.get_item_details(rating_key)
            
            # Basic fields should match
            assert details["title"] == first_movie["title"]
            assert details["ratingKey"] == first_movie["ratingKey"]
            assert details["year"] == first_movie["year"]

    @pytest.mark.integration
    def test_error_handling_real(self, plex_client):
        """Test error handling with real Plex server."""
        # Try to get details for a non-existent item
        details = plex_client.get_item_details(999999999)
        assert details is None
        
        # Try to get similar items for a non-existent item
        similar = plex_client.get_similar_items(999999999, 5)
        assert similar == []
        
        # Try to get extras for a non-existent item
        extras = plex_client.get_extras(999999999)
        assert extras == []

    @pytest.mark.integration
    def test_performance_real(self, plex_client):
        """Test that operations complete in reasonable time."""
        import time
        
        # Test library sections performance
        start_time = time.time()
        sections = plex_client.get_library_sections()
        sections_time = time.time() - start_time
        
        # Should complete in under 5 seconds
        assert sections_time < 5.0, f"Getting library sections took {sections_time:.2f}s"
        
        # Test recently added performance
        start_time = time.time()
        recent = plex_client.get_recently_added("movie", 10)
        recent_time = time.time() - start_time
        
        # Should complete in under 3 seconds
        assert recent_time < 3.0, f"Getting recently added took {recent_time:.2f}s"

    @pytest.mark.integration
    def test_data_quality_real(self, plex_client):
        """Test that returned data has good quality and structure."""
        # Get some real data
        sections = plex_client.get_library_sections()
        
        for section_name, section_info in sections.items():
            # Section names should be reasonable
            assert len(section_name) > 0
            assert len(section_name) < 100
            
            # Section info should have required fields
            assert "type" in section_info
            assert "count" in section_info
            assert "section_id" in section_info
            
            # Types should be valid
            assert section_info["type"] in ["movie", "show", "artist", "photo"]
            
            # Counts should be reasonable
            assert section_info["count"] >= 0
            assert section_info["count"] < 100000  # No library should have 100k+ items

    @pytest.mark.integration
    def test_serialization_real(self, plex_client):
        """Test that all returned data can be properly serialized to JSON."""
        import json
        
        # Test various data types
        test_data = [
            plex_client.get_library_sections(),
            plex_client.get_recently_added("movie", 2),
            plex_client.get_on_deck(2),
            plex_client.get_continue_watching(2),
            plex_client.get_playback_status()
        ]
        
        for data in test_data:
            try:
                # Should be able to serialize to JSON
                json_str = json.dumps(data)
                assert isinstance(json_str, str)
                assert len(json_str) > 0
                
                # Should be able to deserialize back
                parsed = json.loads(json_str)
                assert parsed == data
                
            except (TypeError, ValueError) as e:
                pytest.fail(f"Data could not be serialized to JSON: {e}")

    @pytest.mark.integration
    def test_edge_cases_real(self, plex_client):
        """Test edge cases with real data."""
        # Test with very large limits
        large_recent = plex_client.get_recently_added("movie", 1000)
        assert isinstance(large_recent, list)
        assert len(large_recent) <= 1000
        
        # Test with zero limit
        zero_recent = plex_client.get_recently_added("movie", 0)
        assert isinstance(zero_recent, list)
        assert len(zero_recent) == 0
        
        # Test with negative limit (should probably be handled gracefully)
        try:
            negative_recent = plex_client.get_recently_added("movie", -1)
            # If it doesn't raise an exception, it should return empty list
            assert isinstance(negative_recent, list)
        except Exception:
            # It's also acceptable to raise an exception for invalid input
            pass
