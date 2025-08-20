import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from integrations.plex_client import PlexClient


class TestPlexClient:
    """Test suite for enhanced PlexClient functionality."""

    @pytest.fixture
    def mock_plex_server(self):
        """Create a mock PlexServer instance."""
        mock_server = Mock()
        mock_server.library = Mock()
        mock_server.playlists = Mock()
        mock_server.sessions = Mock()
        return mock_server

    @pytest.fixture
    def plex_client(self, mock_plex_server):
        """Create a PlexClient instance with mocked dependencies."""
        with patch('integrations.plex_client.PlexServer') as mock_plex_class:
            mock_plex_class.return_value = mock_plex_server
            client = PlexClient("http://localhost:32400", "test_token")
            return client

    def test_get_library_sections(self, plex_client, mock_plex_server):
        """Test getting library sections."""
        # Mock library sections
        mock_movies_section = Mock()
        mock_movies_section.title = "Movies"
        mock_movies_section.type = "movie"
        mock_movies_section.totalViewSize = 150
        mock_movies_section.key = "1"

        mock_tv_section = Mock()
        mock_tv_section.title = "TV Shows"
        mock_tv_section.type = "show"
        mock_tv_section.totalViewSize = 75
        mock_tv_section.key = "2"

        mock_plex_server.library.sections.return_value = [mock_movies_section, mock_tv_section]

        result = plex_client.get_library_sections()

        assert result == {
            "Movies": {
                "type": "movie",
                "count": 150,
                "section_id": "1"
            },
            "TV Shows": {
                "type": "show",
                "count": 75,
                "section_id": "2"
            }
        }

    def test_get_movie_library(self, plex_client, mock_plex_server):
        """Test getting movie library section."""
        mock_movie_section = Mock()
        mock_plex_server.library.section.return_value = mock_movie_section

        result = plex_client.get_movie_library()

        mock_plex_server.library.section.assert_called_once_with("Movies")
        assert result == mock_movie_section

    def test_get_tv_library(self, plex_client, mock_plex_server):
        """Test getting TV library section."""
        mock_tv_section = Mock()
        mock_plex_server.library.section.return_value = mock_tv_section

        result = plex_client.get_tv_library()

        mock_plex_server.library.section.assert_called_once_with("TV Shows")
        assert result == mock_tv_section

    def test_get_recently_added(self, plex_client, mock_plex_server):
        """Test getting recently added items."""
        # Mock section and items
        mock_section = Mock()
        mock_plex_server.library.section.return_value = mock_section

        mock_item1 = self._create_mock_movie("Test Movie 1", 2023)
        mock_item2 = self._create_mock_movie("Test Movie 2", 2022)
        mock_section.recentlyAdded.return_value = [mock_item1, mock_item2]

        result = plex_client.get_recently_added("movie", 10)

        mock_plex_server.library.section.assert_called_once_with("Movie")
        mock_section.recentlyAdded.assert_called_once_with(maxresults=10)
        assert len(result) == 2
        assert result[0]["title"] == "Test Movie 1"
        assert result[1]["title"] == "Test Movie 2"

    def test_get_recently_added_error_handling(self, plex_client, mock_plex_server):
        """Test error handling in get_recently_added."""
        mock_plex_server.library.section.side_effect = Exception("Section not found")

        result = plex_client.get_recently_added("movie", 10)

        assert result == []

    def test_get_on_deck(self, plex_client, mock_plex_server):
        """Test getting on deck items."""
        mock_item1 = self._create_mock_movie("On Deck Movie 1", 2023)
        mock_item2 = self._create_mock_movie("On Deck Movie 2", 2022)
        mock_plex_server.library.onDeck.return_value = [mock_item1, mock_item2]

        result = plex_client.get_on_deck(15)

        mock_plex_server.library.onDeck.assert_called_once_with(maxresults=15)
        assert len(result) == 2
        assert result[0]["title"] == "On Deck Movie 1"
        assert result[1]["title"] == "On Deck Movie 2"

    def test_get_continue_watching(self, plex_client, mock_plex_server):
        """Test getting continue watching items."""
        mock_item1 = self._create_mock_movie("Continue Movie 1", 2023)
        mock_item2 = self._create_mock_movie("Continue Movie 2", 2022)
        mock_plex_server.library.continueWatching.return_value = [mock_item1, mock_item2]

        result = plex_client.get_continue_watching(25)

        mock_plex_server.library.continueWatching.assert_called_once_with(maxresults=25)
        assert len(result) == 2
        assert result[0]["title"] == "Continue Movie 1"
        assert result[1]["title"] == "Continue Movie 2"

    def test_get_unwatched(self, plex_client, mock_plex_server):
        """Test getting unwatched items."""
        mock_section = Mock()
        mock_plex_server.library.section.return_value = mock_section

        mock_item1 = self._create_mock_movie("Unwatched Movie 1", 2023)
        mock_item2 = self._create_mock_movie("Unwatched Movie 2", 2022)
        mock_section.unwatched.return_value = [mock_item1, mock_item2]

        result = plex_client.get_unwatched("movie", 30)

        mock_plex_server.library.section.assert_called_once_with("Movie")
        mock_section.unwatched.assert_called_once_with(maxresults=30)
        assert len(result) == 2
        assert result[0]["title"] == "Unwatched Movie 1"
        assert result[1]["title"] == "Unwatched Movie 2"

    def test_get_collections(self, plex_client, mock_plex_server):
        """Test getting collections."""
        mock_section = Mock()
        mock_plex_server.library.section.return_value = mock_section

        mock_collection1 = Mock()
        mock_collection1.title = "Action Movies"
        mock_collection1.summary = "Explosive action films"
        mock_collection1.ratingKey = "1001"
        mock_collection1.children.return_value = [Mock(), Mock(), Mock()]  # 3 items

        mock_collection2 = Mock()
        mock_collection2.title = "Comedy Collection"
        mock_collection2.summary = "Funny films"
        mock_collection2.ratingKey = "1002"
        mock_collection2.children.return_value = [Mock()]  # 1 item

        mock_section.collections.return_value = [mock_collection1, mock_collection2]

        result = plex_client.get_collections("movie", 40)

        mock_plex_server.library.section.assert_called_once_with("Movie")
        mock_section.collections.assert_called_once_with(maxresults=40)
        assert len(result) == 2
        assert result[0]["title"] == "Action Movies"
        assert result[0]["count"] == 3
        assert result[1]["title"] == "Comedy Collection"
        assert result[1]["count"] == 1

    def test_get_playlists(self, plex_client, mock_plex_server):
        """Test getting playlists."""
        mock_playlist1 = Mock()
        mock_playlist1.title = "Weekend Watchlist"
        mock_playlist1.summary = "Movies for the weekend"
        mock_playlist1.ratingKey = "2001"
        mock_playlist1.items.return_value = [Mock(), Mock(), Mock(), Mock()]  # 4 items
        mock_playlist1.duration = 480  # 8 hours

        mock_playlist2 = Mock()
        mock_playlist2.title = "Quick Movies"
        mock_playlist2.summary = "Short films"
        mock_playlist2.ratingKey = "2002"
        mock_playlist2.items.return_value = [Mock()]  # 1 item
        mock_playlist2.duration = 90  # 1.5 hours

        mock_plex_server.playlists.return_value = [mock_playlist1, mock_playlist2]

        result = plex_client.get_playlists(45)

        mock_plex_server.playlists.assert_called_once_with(maxresults=45)
        assert len(result) == 2
        assert result[0]["title"] == "Weekend Watchlist"
        assert result[0]["count"] == 4
        assert result[0]["duration"] == 480
        assert result[1]["title"] == "Quick Movies"
        assert result[1]["count"] == 1
        assert result[1]["duration"] == 90

    def test_get_similar_items(self, plex_client, mock_plex_server):
        """Test getting similar items."""
        mock_item = Mock()
        mock_plex_server.fetchItem.return_value = mock_item

        mock_similar1 = self._create_mock_movie("Similar Movie 1", 2023)
        mock_similar2 = self._create_mock_movie("Similar Movie 2", 2022)
        mock_item.similar.return_value = [mock_similar1, mock_similar2]

        result = plex_client.get_similar_items(12345, 8)

        mock_plex_server.fetchItem.assert_called_once_with(12345)
        mock_item.similar.assert_called_once_with(maxresults=8)
        assert len(result) == 2
        assert result[0]["title"] == "Similar Movie 1"
        assert result[1]["title"] == "Similar Movie 2"

    def test_get_extras(self, plex_client, mock_plex_server):
        """Test getting extras for an item."""
        mock_item = Mock()
        mock_plex_server.fetchItem.return_value = mock_item

        mock_extra1 = Mock()
        mock_extra1.title = "Deleted Scene 1"
        mock_extra1.extraType = "scene"
        mock_extra1.duration = 120
        mock_extra1.ratingKey = "3001"

        mock_extra2 = Mock()
        mock_extra2.title = "Behind the Scenes"
        mock_extra2.extraType = "behindTheScenes"
        mock_extra2.duration = 300
        mock_extra2.ratingKey = "3002"

        mock_item.extras.return_value = [mock_extra1, mock_extra2]

        result = plex_client.get_extras(12345)

        mock_plex_server.fetchItem.assert_called_once_with(12345)
        mock_item.extras.assert_called_once()
        assert len(result) == 2
        assert result[0]["title"] == "Deleted Scene 1"
        assert result[0]["type"] == "scene"
        assert result[0]["duration"] == 120
        assert result[1]["title"] == "Behind the Scenes"
        assert result[1]["type"] == "behindTheScenes"
        assert result[1]["duration"] == 300

    def test_get_playback_status(self, plex_client, mock_plex_server):
        """Test getting playback status."""
        mock_session1 = Mock()
        mock_session1.title = "Currently Playing Movie"
        mock_session1.type = "movie"
        mock_session1.username = "user1"
        mock_session1.progress = 3600  # 1 hour in
        mock_session1.duration = 7200  # 2 hours total
        mock_session1.player = {"product": "Plex Web"}

        mock_session2 = Mock()
        mock_session2.title = "TV Show Episode"
        mock_session2.type = "episode"
        mock_session2.username = "user2"
        mock_session2.progress = 900  # 15 minutes in
        mock_session2.duration = 1800  # 30 minutes total
        mock_session2.player = {"product": "Plex Mobile"}

        mock_plex_server.sessions.return_value = [mock_session1, mock_session2]

        result = plex_client.get_playback_status()

        mock_plex_server.sessions.assert_called_once()
        assert result["active_sessions"] == 2
        assert len(result["sessions"]) == 2
        assert result["sessions"][0]["title"] == "Currently Playing Movie"
        assert result["sessions"][0]["user"] == "user1"
        assert result["sessions"][0]["progress"] == 3600
        assert result["sessions"][1]["title"] == "TV Show Episode"
        assert result["sessions"][1]["user"] == "user2"
        assert result["sessions"][1]["client"] == "Plex Mobile"

    def test_get_playback_status_no_sessions(self, plex_client, mock_plex_server):
        """Test getting playback status when no active sessions."""
        mock_plex_server.sessions.return_value = []

        result = plex_client.get_playback_status()

        assert result["active_sessions"] == 0
        assert result["sessions"] == []

    def test_get_watch_history(self, plex_client, mock_plex_server):
        """Test getting watch history for an item."""
        mock_item = Mock()
        mock_plex_server.fetchItem.return_value = mock_item

        mock_history1 = Mock()
        mock_history1.viewedAt = datetime(2023, 12, 1, 20, 0, 0, tzinfo=timezone.utc)
        mock_history1.user = {"title": "user1"}
        mock_history1.duration = 7200

        mock_history2 = Mock()
        mock_history2.viewedAt = datetime(2023, 11, 15, 19, 30, 0, tzinfo=timezone.utc)
        mock_history2.user = {"title": "user2"}
        mock_history2.duration = 7200

        mock_item.history.return_value = [mock_history1, mock_history2]

        result = plex_client.get_watch_history(12345, 15)

        mock_plex_server.fetchItem.assert_called_once_with(12345)
        mock_item.history.assert_called_once_with(maxresults=15)
        assert len(result) == 2
        assert result[0]["viewed_at"] == "2023-12-01T20:00:00+00:00"
        assert result[0]["user"] == "user1"
        assert result[0]["duration"] == 7200
        assert result[1]["viewed_at"] == "2023-11-15T19:30:00+00:00"
        assert result[1]["user"] == "user2"

    def test_get_item_details(self, plex_client, mock_plex_server):
        """Test getting comprehensive item details."""
        mock_item = self._create_mock_movie("Detailed Movie", 2023)
        mock_plex_server.fetchItem.return_value = mock_item

        result = plex_client.get_item_details(12345)

        mock_plex_server.fetchItem.assert_called_once_with(12345)
        assert result["title"] == "Detailed Movie"
        assert result["year"] == 2023
        assert result["ratingKey"] == 12345
        assert result["viewCount"] == 3
        assert result["type"] == "movie"

    def test_get_item_details_not_found(self, plex_client, mock_plex_server):
        """Test getting item details when item doesn't exist."""
        mock_plex_server.fetchItem.side_effect = Exception("Item not found")

        result = plex_client.get_item_details(99999)

        assert result is None

    def test_serialize_datetime(self, plex_client):
        """Test datetime serialization."""
        # Test with datetime
        dt = datetime(2023, 12, 1, 20, 0, 0, tzinfo=timezone.utc)
        result = plex_client._serialize_datetime(dt)
        assert result == "2023-12-01T20:00:00+00:00"

        # Test with None
        result = plex_client._serialize_datetime(None)
        assert result is None

        # Test with string
        result = plex_client._serialize_datetime("2023-12-01")
        assert result == "2023-12-01"

        # Test with number
        result = plex_client._serialize_datetime(12345)
        assert result == "12345"

    def _create_mock_movie(self, title, year):
        """Helper method to create a mock movie item."""
        mock_movie = Mock()
        mock_movie.title = title
        mock_movie.year = year
        mock_movie.ratingKey = 12345
        mock_movie.rating = 8.5
        mock_movie.contentRating = "PG-13"
        mock_movie.duration = 7200
        mock_movie.genres = [Mock(tag="Action"), Mock(tag="Adventure")]
        mock_movie.actors = [Mock(tag="Actor 1"), Mock(tag="Actor 2")]
        mock_movie.directors = [Mock(tag="Director 1")]
        mock_movie.summary = "A test movie summary"
        mock_movie.tagline = "A test tagline"
        mock_movie.studio = "Test Studio"
        mock_movie.addedAt = datetime(2023, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_movie.updatedAt = datetime(2023, 11, 15, 14, 30, 0, tzinfo=timezone.utc)
        mock_movie.viewCount = 3
        mock_movie.lastViewedAt = datetime(2023, 12, 1, 20, 0, 0, tzinfo=timezone.utc)
        mock_movie.type = "movie"
        mock_movie.guid = "plex://movie/12345"
        return mock_movie

    def test_serialize_items(self, plex_client):
        """Test serializing multiple items."""
        mock_item1 = self._create_mock_movie("Movie 1", 2023)
        mock_item2 = self._create_mock_movie("Movie 2", 2022)

        result = plex_client._serialize_items([mock_item1, mock_item2])

        assert len(result) == 2
        assert result[0]["title"] == "Movie 1"
        assert result[0]["year"] == 2023
        assert result[1]["title"] == "Movie 2"
        assert result[1]["year"] == 2022

    def test_error_handling_in_collections(self, plex_client, mock_plex_server):
        """Test error handling in get_collections."""
        mock_plex_server.library.section.side_effect = Exception("Section error")

        result = plex_client.get_collections("movie", 50)

        assert result == []

    def test_error_handling_in_playlists(self, plex_client, mock_plex_server):
        """Test error handling in get_playlists."""
        mock_plex_server.playlists.side_effect = Exception("Playlist error")

        result = plex_client.get_playlists(50)

        assert result == []

    def test_error_handling_in_similar_items(self, plex_client, mock_plex_server):
        """Test error handling in get_similar_items."""
        mock_plex_server.fetchItem.side_effect = Exception("Item not found")

        result = plex_client.get_similar_items(12345, 10)

        assert result == []

    def test_error_handling_in_extras(self, plex_client, mock_plex_server):
        """Test error handling in get_extras."""
        mock_plex_server.fetchItem.side_effect = Exception("Item not found")

        result = plex_client.get_extras(12345)

        assert result == []

    def test_error_handling_in_playback_status(self, plex_client, mock_plex_server):
        """Test error handling in get_playback_status."""
        mock_plex_server.sessions.side_effect = Exception("Sessions error")

        result = plex_client.get_playback_status()

        assert result == {"active_sessions": 0, "sessions": []}

    def test_error_handling_in_watch_history(self, plex_client, mock_plex_server):
        """Test error handling in get_watch_history."""
        mock_plex_server.fetchItem.side_effect = Exception("Item not found")

        result = plex_client.get_watch_history(12345, 20)

        assert result == []
