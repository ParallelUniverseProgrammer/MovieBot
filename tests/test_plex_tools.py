import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import asyncio
from bot.tools.tool_impl import (
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
)


class TestPlexTools:
    """Test suite for Plex tool implementations."""

    @pytest.fixture
    def project_root(self):
        """Create a mock project root path."""
        return Path("/mock/project/root")

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = Mock()
        settings.plex_base_url = "http://localhost:32400"
        settings.plex_token = "test_token_123"
        return settings

    @pytest.fixture
    def mock_plex_client(self):
        """Create a mock PlexClient."""
        client = Mock()
        return client

    @pytest.fixture
    def mock_load_settings(self, mock_settings):
        """Mock the load_settings function."""
        with patch('bot.tools.tool_impl.load_settings') as mock_load:
            mock_load.return_value = mock_settings
            yield mock_load

    @pytest.mark.asyncio
    async def test_get_plex_library_sections(self, project_root, mock_load_settings, mock_plex_client):
        """Test get_plex_library_sections tool."""
        with patch('bot.tools.tool_impl.PlexClient') as mock_plex_class:
            mock_plex_class.return_value = mock_plex_client
            
            # Mock the expected return data
            expected_sections = {
                "Movies": {"type": "movie", "count": 150, "section_id": "1"},
                "TV Shows": {"type": "show", "count": 75, "section_id": "2"}
            }
            mock_plex_client.get_library_sections.return_value = expected_sections

            # Create and call the tool
            tool = make_get_plex_library_sections(project_root)
            result = await tool({})

            # Verify the result
            assert result == {"sections": expected_sections}
            mock_plex_class.assert_called_once_with("http://localhost:32400", "test_token_123")
            mock_plex_client.get_library_sections.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_plex_recently_added(self, project_root, mock_load_settings, mock_plex_client):
        """Test get_plex_recently_added tool."""
        with patch('bot.tools.tool_impl.PlexClient') as mock_plex_class:
            mock_plex_class.return_value = mock_plex_client
            
            # Mock the expected return data
            expected_items = [
                {"title": "New Movie 1", "year": 2023, "ratingKey": 1001},
                {"title": "New Movie 2", "year": 2022, "ratingKey": 1002}
            ]
            mock_plex_client.get_recently_added.return_value = expected_items

            # Test with default parameters
            tool = make_get_plex_recently_added(project_root)
            result = await tool({})

            assert result == {
                "items": expected_items,
                "section_type": "movie",
                "limit": 20,
                "total_found": 2
            }
            mock_plex_client.get_recently_added.assert_called_once_with("movie", 20)

            # Test with custom parameters
            result = await tool({
                "section_type": "show",
                "limit": 15
            })

            assert result == {
                "items": expected_items,
                "section_type": "show",
                "limit": 15,
                "total_found": 2
            }
            mock_plex_client.get_recently_added.assert_called_with("show", 15)

    @pytest.mark.asyncio
    async def test_get_plex_on_deck(self, project_root, mock_load_settings, mock_plex_client):
        """Test get_plex_on_deck tool."""
        with patch('bot.tools.tool_impl.PlexClient') as mock_plex_class:
            mock_plex_class.return_value = mock_plex_client
            
            expected_items = [
                {"title": "On Deck Movie 1", "year": 2023, "ratingKey": 2001},
                {"title": "On Deck Movie 2", "year": 2022, "ratingKey": 2002}
            ]
            mock_plex_client.get_on_deck.return_value = expected_items

            tool = make_get_plex_on_deck(project_root)
            result = await tool({"limit": 25})

            assert result == {
                "items": expected_items,
                "limit": 25,
                "total_found": 2
            }
            mock_plex_client.get_on_deck.assert_called_once_with(25)

    @pytest.mark.asyncio
    async def test_get_plex_continue_watching(self, project_root, mock_load_settings, mock_plex_client):
        """Test get_plex_continue_watching tool."""
        with patch('bot.tools.tool_impl.PlexClient') as mock_plex_class:
            mock_plex_class.return_value = mock_plex_client
            
            expected_items = [
                {"title": "Continue Movie 1", "year": 2023, "ratingKey": 3001},
                {"title": "Continue Movie 2", "year": 2022, "ratingKey": 3002}
            ]
            mock_plex_client.get_continue_watching.return_value = expected_items

            tool = make_get_plex_continue_watching(project_root)
            result = await tool({"limit": 30})

            assert result == {
                "items": expected_items,
                "limit": 30,
                "total_found": 2
            }
            mock_plex_client.get_continue_watching.assert_called_once_with(30)

    @pytest.mark.asyncio
    async def test_get_plex_unwatched(self, project_root, mock_load_settings, mock_plex_client):
        """Test get_plex_unwatched tool."""
        with patch('bot.tools.tool_impl.PlexClient') as mock_plex_class:
            mock_plex_class.return_value = mock_plex_client
            
            expected_items = [
                {"title": "Unwatched Movie 1", "year": 2023, "ratingKey": 4001},
                {"title": "Unwatched Movie 2", "year": 2022, "ratingKey": 4002}
            ]
            mock_plex_client.get_unwatched.return_value = expected_items

            tool = make_get_plex_unwatched(project_root)
            result = await tool({
                "section_type": "show",
                "limit": 35
            })

            assert result == {
                "items": expected_items,
                "section_type": "show",
                "limit": 35,
                "total_found": 2
            }
            mock_plex_client.get_unwatched.assert_called_once_with("show", 35)

    @pytest.mark.asyncio
    async def test_get_plex_collections(self, project_root, mock_load_settings, mock_plex_client):
        """Test get_plex_collections tool."""
        with patch('bot.tools.tool_impl.PlexClient') as mock_plex_class:
            mock_plex_class.return_value = mock_plex_client
            
            expected_collections = [
                {
                    "title": "Action Movies",
                    "summary": "Explosive action films",
                    "count": 25,
                    "collection_id": "5001"
                },
                {
                    "title": "Comedy Collection",
                    "summary": "Funny films",
                    "count": 15,
                    "collection_id": "5002"
                }
            ]
            mock_plex_client.get_collections.return_value = expected_collections

            tool = make_get_plex_collections(project_root)
            result = await tool({
                "section_type": "movie",
                "limit": 40
            })

            assert result == {
                "collections": expected_collections,
                "section_type": "movie",
                "limit": 40,
                "total_found": 2
            }
            mock_plex_client.get_collections.assert_called_once_with("movie", 40)

    @pytest.mark.asyncio
    async def test_get_plex_playlists(self, project_root, mock_load_settings, mock_plex_client):
        """Test get_plex_playlists tool."""
        with patch('bot.tools.tool_impl.PlexClient') as mock_plex_class:
            mock_plex_class.return_value = mock_plex_client
            
            expected_playlists = [
                {
                    "title": "Weekend Watchlist",
                    "summary": "Movies for the weekend",
                    "count": 8,
                    "playlist_id": "6001",
                    "duration": 960
                },
                {
                    "title": "Quick Movies",
                    "summary": "Short films",
                    "count": 5,
                    "playlist_id": "6002",
                    "duration": 450
                }
            ]
            mock_plex_client.get_playlists.return_value = expected_playlists

            tool = make_get_plex_playlists(project_root)
            result = await tool({"limit": 45})

            assert result == {
                "playlists": expected_playlists,
                "limit": 45,
                "total_found": 2
            }
            mock_plex_client.get_playlists.assert_called_once_with(45)

    @pytest.mark.asyncio
    async def test_get_plex_similar_items(self, project_root, mock_load_settings, mock_plex_client):
        """Test get_plex_similar_items tool."""
        with patch('bot.tools.tool_impl.PlexClient') as mock_plex_class:
            mock_plex_class.return_value = mock_plex_client
            
            expected_items = [
                {"title": "Similar Movie 1", "year": 2023, "ratingKey": 7001},
                {"title": "Similar Movie 2", "year": 2022, "ratingKey": 7002}
            ]
            mock_plex_client.get_similar_items.return_value = expected_items

            tool = make_get_plex_similar_items(project_root)
            result = await tool({
                "rating_key": 12345,
                "limit": 12
            })

            assert result == {
                "items": expected_items,
                "rating_key": 12345,
                "limit": 12,
                "total_found": 2
            }
            mock_plex_client.get_similar_items.assert_called_once_with(12345, 12)

    @pytest.mark.asyncio
    async def test_get_plex_extras(self, project_root, mock_load_settings, mock_plex_client):
        """Test get_plex_extras tool."""
        with patch('bot.tools.tool_impl.PlexClient') as mock_plex_class:
            mock_plex_class.return_value = mock_plex_client
            
            expected_extras = [
                {
                    "title": "Deleted Scene 1",
                    "type": "scene",
                    "duration": 120,
                    "extra_id": "8001"
                },
                {
                    "title": "Behind the Scenes",
                    "type": "behindTheScenes",
                    "duration": 300,
                    "extra_id": "8002"
                }
            ]
            mock_plex_client.get_extras.return_value = expected_extras

            tool = make_get_plex_extras(project_root)
            result = await tool({"rating_key": 12345})

            assert result == {
                "extras": expected_extras,
                "rating_key": 12345,
                "total_found": 2
            }
            mock_plex_client.get_extras.assert_called_once_with(12345)

    @pytest.mark.asyncio
    async def test_get_plex_playback_status(self, project_root, mock_load_settings, mock_plex_client):
        """Test get_plex_playback_status tool."""
        with patch('bot.tools.tool_impl.PlexClient') as mock_plex_class:
            mock_plex_class.return_value = mock_plex_client
            
            expected_status = {
                "active_sessions": 2,
                "sessions": [
                    {
                        "title": "Currently Playing Movie",
                        "type": "movie",
                        "user": "user1",
                        "progress": 3600,
                        "duration": 7200,
                        "client": "Plex Web"
                    }
                ]
            }
            mock_plex_client.get_playback_status.return_value = expected_status

            tool = make_get_plex_playback_status(project_root)
            result = await tool({})

            assert result == expected_status
            mock_plex_client.get_playback_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_plex_watch_history(self, project_root, mock_load_settings, mock_plex_client):
        """Test get_plex_watch_history tool."""
        with patch('bot.tools.tool_impl.PlexClient') as mock_plex_class:
            mock_plex_class.return_value = mock_plex_client
            
            expected_history = [
                {
                    "viewed_at": "2023-12-01T20:00:00+00:00",
                    "user": "user1",
                    "duration": 7200
                },
                {
                    "viewed_at": "2023-11-15T19:30:00+00:00",
                    "user": "user2",
                    "duration": 7200
                }
            ]
            mock_plex_client.get_watch_history.return_value = expected_history

            tool = make_get_plex_watch_history(project_root)
            result = await tool({
                "rating_key": 12345,
                "limit": 18
            })

            assert result == {
                "history": expected_history,
                "rating_key": 12345,
                "limit": 18,
                "total_found": 2
            }
            mock_plex_client.get_watch_history.assert_called_once_with(12345, 18)

    @pytest.mark.asyncio
    async def test_get_plex_item_details(self, project_root, mock_load_settings, mock_plex_client):
        """Test get_plex_item_details tool."""
        with patch('bot.tools.tool_impl.PlexClient') as mock_plex_class:
            mock_plex_class.return_value = mock_plex_client
            
            expected_item = {
                "title": "Detailed Movie",
                "year": 2023,
                "ratingKey": 12345,
                "rating": 8.5,
                "contentRating": "PG-13",
                "duration": 7200,
                "genres": ["Action", "Adventure"],
                "actors": ["Actor 1", "Actor 2"],
                "directors": ["Director 1"],
                "summary": "A test movie summary",
                "tagline": "A test tagline",
                "studio": "Test Studio",
                "addedAt": "2023-11-01T12:00:00+00:00",
                "updatedAt": "2023-11-15T14:30:00+00:00",
                "viewCount": 3,
                "lastViewedAt": "2023-12-01T20:00:00+00:00",
                "type": "movie",
                "guid": "plex://movie/12345"
            }
            mock_plex_client.get_item_details.return_value = expected_item

            tool = make_get_plex_item_details(project_root)
            result = await tool({"rating_key": 12345})

            assert result == {"item": expected_item}
            mock_plex_client.get_item_details.assert_called_once_with(12345)

    @pytest.mark.asyncio
    async def test_get_plex_item_details_not_found(self, project_root, mock_load_settings, mock_plex_client):
        """Test get_plex_item_details tool when item is not found."""
        with patch('bot.tools.tool_impl.PlexClient') as mock_plex_class:
            mock_plex_class.return_value = mock_plex_client
            
            mock_plex_client.get_item_details.return_value = None

            tool = make_get_plex_item_details(project_root)
            result = await tool({"rating_key": 99999})

            assert result == {
                "error": "Item not found",
                "rating_key": 99999
            }
            mock_plex_client.get_item_details.assert_called_once_with(99999)

    @pytest.mark.asyncio
    async def test_tool_parameter_validation(self, project_root, mock_load_settings, mock_plex_client):
        """Test that tools properly validate and handle parameters."""
        with patch('bot.tools.tool_impl.PlexClient') as mock_plex_class:
            mock_plex_class.return_value = mock_plex_client
            
            # Test that tools handle missing parameters gracefully
            mock_plex_client.get_recently_added.return_value = []
            
            tool = make_get_plex_recently_added(project_root)
            result = await tool({})  # No parameters

            # Should use defaults
            assert result["section_type"] == "movie"
            assert result["limit"] == 20
            mock_plex_client.get_recently_added.assert_called_once_with("movie", 20)

    @pytest.mark.asyncio
    async def test_tool_error_handling(self, project_root, mock_load_settings):
        """Test that tools handle PlexClient initialization errors gracefully."""
        with patch('bot.tools.tool_impl.PlexClient') as mock_plex_class:
            # Simulate an error during PlexClient initialization
            mock_plex_class.side_effect = Exception("Connection failed")
            
            tool = make_get_plex_library_sections(project_root)
            
            # Should raise the exception
            with pytest.raises(Exception, match="Connection failed"):
                await tool({})

    @pytest.mark.asyncio
    async def test_tool_async_behavior(self, project_root, mock_load_settings, mock_plex_client):
        """Test that tools properly handle async behavior."""
        with patch('bot.tools.tool_impl.PlexClient') as mock_plex_class:
            mock_plex_class.return_value = mock_plex_client
            
            # Mock async behavior
            mock_plex_client.get_library_sections.return_value = {"Movies": {"count": 100}}
            
            tool = make_get_plex_library_sections(project_root)
            
            # Tool should be awaitable
            import asyncio
            if asyncio.iscoroutinefunction(tool):
                result = await tool({})
                assert result == {"sections": {"Movies": {"count": 100}}}
            else:
                pytest.fail("Tool should be an async function")
