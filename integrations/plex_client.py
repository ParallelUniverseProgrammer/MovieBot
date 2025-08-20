from __future__ import annotations

from typing import Any, List, Dict, Optional
from urllib.parse import urlparse

from plexapi.server import PlexServer
from plexapi.library import MovieSection, ShowSection


class PlexClient:
    """Thin wrapper around python-plexapi for minimal operations."""

    def __init__(self, base_url: str, token: str):
        if not token or token.strip() == "":
            raise ValueError("PLEX_TOKEN is missing. Set it in your .env via the setup wizard.")
        normalized = self._normalize_base_url(base_url)
        self.plex: PlexServer = PlexServer(normalized, token)

    @staticmethod
    def _normalize_base_url(raw: str) -> str:
        if not raw:
            return "http://localhost:32400"
        raw = raw.strip()
        parsed = urlparse(raw)
        # Accept only http/https schemes; repair common mistakes
        if parsed.scheme in ("http", "https"):
            netloc = parsed.netloc or parsed.path  # handle cases like http://localhost
            if ":" not in netloc and netloc in ("localhost", "127.0.0.1") and parsed.scheme == "http":
                return f"http://{netloc}:32400"
            return raw
        # If it looks like TOKEN://host -> keep host, fix scheme
        if parsed.netloc:
            host = parsed.netloc
            if ":" not in host and host in ("localhost", "127.0.0.1"):
                return f"http://{host}:32400"
            return f"http://{host}"
        # If no scheme, treat as host[:port]
        if raw.startswith("localhost") or raw.startswith("127.0.0.1"):
            return raw if ":" in raw else f"http://{raw}:32400"
        return f"http://{raw}"

    def _get_section_title(self, section_type: str) -> str:
        """Map section type to actual section title in Plex."""
        # Get available sections to find the correct title
        sections = self.plex.library.sections()
        
        # Look for a section that matches the type
        for section in sections:
            if section.type.lower() == section_type.lower():
                return section.title
        
        # Fallback to common mappings
        if section_type.lower() == "movie":
            return "Movies"
        elif section_type.lower() == "show":
            return "TV Shows"
        
        # If no match found, return the original with title case
        return section_type.title()

    def search_movies(self, query: str) -> List[Any]:
        return self.plex.search(query, mediatype="movie")

    def set_rating(self, rating_key: int, rating_1_to_10: int) -> None:
        # There isn't a direct method by ratingKey, so fetch the item and rate
        item = self.plex.fetchItem(rating_key)
        item.rate(rating_1_to_10)

    # New methods for enhanced integration

    def get_library_sections(self) -> Dict[str, Any]:
        """Get available library sections and their counts."""
        sections = {}
        for section in self.plex.library.sections():
            sections[section.title] = {
                "type": section.type,
                "count": section.totalViewSize(),  # Call the method to get the value
                "section_id": section.key
            }
        return sections

    def get_movie_library(self) -> MovieSection:
        """Get the movie library section."""
        return self.plex.library.section("Movies")

    def get_tv_library(self) -> ShowSection:
        """Get the TV shows library section."""
        return self.plex.library.section("TV Shows")

    def get_recently_added(self, section_type: str = "movie", limit: int = 20) -> List[Dict[str, Any]]:
        """Get recently added items from specified library."""
        try:
            # Map section type to actual section title
            section_title = self._get_section_title(section_type)
            section = self.plex.library.section(section_title)
            recent = section.recentlyAdded(maxresults=limit)
            return self._serialize_items(recent)
        except Exception:
            return []

    def get_on_deck(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get items that are 'on deck' (next to watch)."""
        try:
            on_deck = self.plex.library.onDeck(maxresults=limit)
            return self._serialize_items(on_deck)
        except Exception:
            return []

    def get_continue_watching(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get items that can be continued (partially watched)."""
        try:
            # This gets items that have been started but not finished
            continue_watching = self.plex.library.continueWatching(maxresults=limit)
            return self._serialize_items(continue_watching)
        except Exception:
            return []

    def get_unwatched(self, section_type: str = "movie", limit: int = 20) -> List[Dict[str, Any]]:
        """Get unwatched items from specified library."""
        try:
            section_title = self._get_section_title(section_type)
            section = self.plex.library.section(section_title)
            # Get all items and filter for unwatched ones
            all_items = section.all()
            unwatched = [item for item in all_items if not getattr(item, 'isWatched', False)][:limit]
            return self._serialize_items(unwatched)
        except Exception:
            return []

    def get_collections(self, section_type: str = "movie", limit: int = 50) -> List[Dict[str, Any]]:
        """Get collections from specified library."""
        try:
            section_title = self._get_section_title(section_type)
            section = self.plex.library.section(section_title)
            collections = section.collections(maxresults=limit)
            return [{
                "title": collection.title,
                "summary": getattr(collection, "summary", None),
                "count": len(collection.items()),
                "collection_id": collection.ratingKey
            } for collection in collections]
        except Exception:
            return []

    def get_playlists(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get available playlists."""
        try:
            playlists = self.plex.playlists(maxresults=limit)
            return [{
                "title": playlist.title,
                "summary": getattr(playlist, "summary", None),
                "count": len(playlist.items()),
                "playlist_id": playlist.ratingKey,
                "duration": getattr(playlist, "duration", None)
            } for playlist in playlists]
        except Exception:
            return []

    def get_similar_items(self, rating_key: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get similar items to a specific movie/show."""
        try:
            item = self.plex.fetchItem(rating_key)
            similar = item.similar(maxresults=limit)
            return self._serialize_items(similar)
        except Exception:
            return []

    def get_extras(self, rating_key: int) -> List[Dict[str, Any]]:
        """Get extras (deleted scenes, bonus features) for an item."""
        try:
            item = self.plex.fetchItem(rating_key)
            extras = item.extras()
            return [{
                "title": extra.title,
                "type": getattr(extra, "extraType", None),
                "duration": getattr(extra, "duration", None),
                "extra_id": extra.ratingKey
            } for extra in extras]
        except Exception:
            return []

    def get_playback_status(self) -> Dict[str, Any]:
        """Get current playback status across all clients."""
        try:
            sessions = self.plex.sessions()
            return {
                "active_sessions": len(sessions),
                "sessions": [{
                    "title": session.title,
                    "type": session.type,
                    "user": getattr(session, "username", "Unknown"),
                    "progress": getattr(session, "progress", 0),
                    "duration": getattr(session, "duration", 0),
                    "client": getattr(session, "player", {}).get("product", "Unknown")
                } for session in sessions]
            }
        except Exception:
            return {"active_sessions": 0, "sessions": []}

    def get_watch_history(self, rating_key: int, limit: int = 20) -> List[Dict[str, Any]]:
        """Get watch history for a specific item."""
        try:
            item = self.plex.fetchItem(rating_key)
            history = item.history(maxresults=limit)
            return [{
                "viewed_at": history_item.viewedAt.isoformat() if hasattr(history_item, "viewedAt") else None,
                "user": getattr(history_item, "user", {}).get("title", "Unknown"),
                "duration": getattr(history_item, "duration", None)
            } for history_item in history]
        except Exception:
            return []

    def get_item_details(self, rating_key: int) -> Optional[Dict[str, Any]]:
        """Get comprehensive details for a specific item."""
        try:
            item = self.plex.fetchItem(rating_key)
            return self._serialize_item(item)
        except Exception:
            return None

    def _serialize_items(self, items: List[Any]) -> List[Dict[str, Any]]:
        """Serialize a list of Plex items to dictionaries."""
        return [self._serialize_item(item) for item in items]

    def _serialize_item(self, item: Any) -> Dict[str, Any]:
        """Serialize a single Plex item to a dictionary."""
        return {
            "title": getattr(item, "title", None),
            "year": getattr(item, "year", None),
            "ratingKey": getattr(item, "ratingKey", None),
            "rating": getattr(item, "rating", None),
            "contentRating": getattr(item, "contentRating", None),
            "duration": getattr(item, "duration", None),
            "genres": [genre.tag for genre in getattr(item, "genres", [])] if hasattr(item, "genres") else [],
            "actors": [actor.tag for actor in getattr(item, "actors", [])] if hasattr(item, "actors") else [],
            "directors": [director.tag for director in getattr(item, "directors", [])] if hasattr(item, "directors") else [],
            "summary": getattr(item, "summary", None),
            "tagline": getattr(item, "tagline", None),
            "studio": getattr(item, "studio", None),
            "addedAt": self._serialize_datetime(getattr(item, "addedAt", None)),
            "updatedAt": self._serialize_datetime(getattr(item, "updatedAt", None)),
            "viewCount": getattr(item, "viewCount", 0),
            "lastViewedAt": self._serialize_datetime(getattr(item, "lastViewedAt", None)),
            "type": getattr(item, "type", None),
            "guid": getattr(item, "guid", None)
        }

    def _serialize_datetime(self, value):
        """Safely serialize datetime objects and other types to JSON-compatible format."""
        if value is None:
            return None
        
        # Handle datetime objects
        if hasattr(value, 'isoformat'):
            return value.isoformat()
        
        # Handle other potentially problematic types
        if hasattr(value, '__str__'):
            return str(value)
        
        return value


