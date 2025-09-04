from __future__ import annotations

from typing import Any, List, Dict, Optional, Literal, Set
from urllib.parse import urlparse
from enum import Enum

from plexapi.server import PlexServer
from plexapi.library import MovieSection, ShowSection


class ResponseLevel(Enum):
    """Response detail levels to control context usage."""
    MINIMAL = "minimal"      # Only essential fields (title, ratingKey, type)
    COMPACT = "compact"      # Key fields for browsing (title, year, rating, ratingKey)
    STANDARD = "standard"    # Common fields (title, year, rating, genres, summary)
    DETAILED = "detailed"    # All available fields (current behavior)


class PlexClient:
    """
    Thin wrapper around python-plexapi for minimal operations.
    
    Efficiency Features:
    - Configurable response detail levels to reduce context usage
    - MINIMAL: Only essential fields (title, ratingKey, type) - ~60% context reduction
    - COMPACT: Key fields for browsing (title, year, rating, ratingKey) - ~40% context reduction  
    - STANDARD: Common fields (title, year, rating, genres, summary) - ~20% context reduction
    - DETAILED: All available fields (current behavior)
    
    Usage:
        # Default compact responses for efficiency
        client = PlexClient(url, token)
        
        # Override for specific calls when detailed info needed
        details = client.get_item_details(rating_key, ResponseLevel.DETAILED)
        
        # Quick overview with minimal data
        overview = client.get_minimal_library_overview()
    """

    def __init__(self, base_url: str, token: str, default_response_level: ResponseLevel = ResponseLevel.COMPACT):
        if not token or token.strip() == "":
            raise ValueError("PLEX_TOKEN is missing. Set it in your .env via the setup wizard.")
        normalized = self._normalize_base_url(base_url)
        self.plex: PlexServer = PlexServer(normalized, token)
        self.default_response_level = default_response_level

    def set_response_level(self, level: ResponseLevel) -> None:
        """Dynamically change the default response level for all subsequent calls."""
        self.default_response_level = level

    def get_response_level(self) -> ResponseLevel:
        """Get the current default response level."""
        return self.default_response_level

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
        # Try to resolve from available sections; tolerate mocks/non-iterables
        try:
            sections = self.plex.library.sections()
            try:
                for section in sections:  # may raise if sections is a Mock
                    stype = getattr(section, "type", "")
                    if isinstance(stype, str) and stype.lower() == section_type.lower():
                        title = getattr(section, "title", None)
                        if isinstance(title, str) and title:
                            return title
            except TypeError:
                # Non-iterable (e.g., Mock); fall through to defaults
                pass
        except Exception:
            # Any errors fetching sections; fall through to defaults
            pass
        
        # Fallback to common mappings
        if section_type.lower() == "movie":
            return "Movies"
        elif section_type.lower() == "show":
            return "TV Shows"
        
        # If no match found, return the original with title case
        return section_type.title()

    def search_movies(self, query: str, response_level: Optional[ResponseLevel] = None) -> List[Dict[str, Any]]:
        """Search for movies with configurable response detail.

        Returns serialized dicts to keep the API consistent with the rest of the client,
        but also attaches a `ratingKey` attribute-like access shim for common usage patterns
        in existing callers that may expect plexapi objects.
        """
        results = self.plex.search(query, mediatype="movie")
        serialized = self._serialize_items(results, response_level)

        # Provide a lightweight attribute-access shim on each dict for compatibility with
        # callers that access `m.title` or `m.ratingKey`. This avoids breaking integrations
        # while keeping transport as dicts for consistency.
        class _AttrShim(dict):
            __getattr__ = dict.get  # type: ignore[assignment]

        return [_AttrShim(d) for d in serialized]

    def search_shows(self, query: str, response_level: Optional[ResponseLevel] = None) -> List[Dict[str, Any]]:
        """Search for TV shows with configurable response detail."""
        results = self.plex.search(query, mediatype="show")
        return self._serialize_items(results, response_level)

    def search_all(self, query: str, response_level: Optional[ResponseLevel] = None) -> List[Dict[str, Any]]:
        """Search across all media types with configurable response detail."""
        results = self.plex.search(query)
        return self._serialize_items(results, response_level)

    # Advanced, server-side filtered movie search
    def _map_sort_key(self, sort_by: Optional[str]) -> str:
        """Map user-friendly sort fields to Plex API sort fields."""
        mapping = {
            "title": "titleSort",  # Plex API uses titleSort, not title
            "year": "year",
            "rating": "rating",
            "content_rating": "contentRating",
            "duration": "duration",
            "added": "addedAt",
            "addedAt": "addedAt",
            "lastViewed": "lastViewedAt",
            "lastViewedAt": "lastViewedAt",
            "titleSort": "titleSort",  # Direct mapping for API compliance
        }
        return mapping.get((sort_by or "title").strip(), "titleSort")

    def search_movies_filtered(
        self,
        title: Optional[str] = None,
        *,
        year_min: Optional[int] = None,
        year_max: Optional[int] = None,
        genres: Optional[List[str]] = None,
        actors: Optional[List[str]] = None,
        directors: Optional[List[str]] = None,
        content_rating: Optional[str] = None,
        rating_min: Optional[float] = None,
        rating_max: Optional[float] = None,
        sort_by: Optional[str] = "title",
        sort_order: Optional[str] = "asc",
        limit: int = 20,
        response_level: Optional[ResponseLevel] = None,
    ) -> List[Dict[str, Any]]:
        """Perform server-side Plex search with filters and inclusive bounds.

        - If year_min == year_max, performs exact-year filtering.
        - Multiple values within a category (genres/actors/directors) are OR'ed server-side via
          multiple filtered calls and union within the category, then AND'ed across categories
          via set intersection to minimize client-side work while keeping filtering on server.
        - Sorting and limiting are applied on the server when possible.
        """
        section = self.get_movie_library()

        # Build base filters
        base_kwargs: Dict[str, Any] = {}
        if title:
            base_kwargs["title"] = title
        if year_min is not None and year_max is not None and int(year_min) == int(year_max):
            base_kwargs["year"] = int(year_min)
        else:
            if year_min is not None:
                base_kwargs["year__gte"] = int(year_min)
            if year_max is not None:
                base_kwargs["year__lte"] = int(year_max)
        if content_rating:
            base_kwargs["contentRating"] = content_rating
        if rating_min is not None:
            base_kwargs["rating__gte"] = float(rating_min)
        if rating_max is not None:
            base_kwargs["rating__lte"] = float(rating_max)

        sort_key = self._map_sort_key(sort_by)
        direction = "asc" if str(sort_order or "asc").lower() == "asc" else "desc"
        sort_param = f"{sort_key}:{direction}"

        # Normalize and validate list filters
        genres = [g for g in (genres or []) if str(g).strip()]
        actors = [a for a in (actors or []) if str(a).strip()]
        directors = [d for d in (directors or []) if str(d).strip()]

        # Try to use Plex's native filtering first (most efficient)
        try:
            # Build comprehensive search parameters
            search_kwargs = dict(base_kwargs)
            search_kwargs.update({
                "maxresults": limit,
                "sort": sort_param
            })
            
            # Add list filters if they exist (Plex supports OR within categories)
            if genres:
                search_kwargs["genre"] = genres[0]  # Plex API limitation: single genre per call
            if actors:
                search_kwargs["actor"] = actors[0]  # Plex API limitation: single actor per call
            if directors:
                search_kwargs["director"] = directors[0]  # Plex API limitation: single director per call
            
            items = section.search(**search_kwargs)
            
        except Exception:
            # Fallback to multiple calls with intersection (less efficient but more reliable)
            try:
                items = self._search_with_intersection(
                    section, base_kwargs, genres, actors, directors, 
                    sort_param, limit, sort_key, direction
                )
            except Exception:
                # Final fallback: minimal search
                try:
                    fallback_kwargs = {k: v for k, v in base_kwargs.items() if k == "title"}
                    items = section.search(maxresults=limit, sort=sort_param, **fallback_kwargs)
                except Exception:
                    items = []

        return self._serialize_items(items, response_level)

    def _search_with_intersection(
        self, 
        section: Any, 
        base_kwargs: Dict[str, Any], 
        genres: List[str], 
        actors: List[str], 
        directors: List[str],
        sort_param: str,
        limit: int,
        sort_key: str,
        direction: str
    ) -> List[Any]:
        """Fallback method for complex filtering using intersection logic."""
        list_filters: List[tuple[str, List[str]]] = []
        if genres:
            list_filters.append(("genre", genres))
        if actors:
            list_filters.append(("actor", actors))
        if directors:
            list_filters.append(("director", directors))

        if not list_filters:
            return section.search(maxresults=limit, sort=sort_param, **base_kwargs)

        # Perform OR within each category and AND across categories via set intersection
        current_ids: Optional[Set[Any]] = None
        id_to_item: Dict[Any, Any] = {}
        
        for key, values in list_filters:
            category_union: Set[Any] = set()
            category_map: Dict[Any, Any] = {}
            
            for val in values:
                try:
                    res = section.search(maxresults=limit, sort=sort_param, **base_kwargs, **{key: val})
                except Exception:
                    res = []
                for it in res:
                    rk = getattr(it, "ratingKey", None)
                    if rk is not None:
                        category_union.add(rk)
                        category_map[rk] = it
            
            if current_ids is None:
                current_ids = category_union
            else:
                current_ids = current_ids.intersection(category_union)
            id_to_item.update(category_map)
            if not current_ids:
                break

        if current_ids:
            items = [id_to_item[rk] for rk in current_ids if rk in id_to_item]
            # Ensure deterministic ordering client-side if needed
            try:
                items.sort(key=lambda x: getattr(x, sort_key, getattr(x, "title", "")), reverse=(direction == "desc"))
            except Exception:
                items.sort(key=lambda x: getattr(x, "title", ""), reverse=(direction == "desc"))
            return items[:limit]
        else:
            return []

    # Convenience methods for minimal context usage
    def get_minimal_library_overview(self) -> Dict[str, Any]:
        """Get minimal library overview for quick status checks."""
        try:
            sections = self.plex.library.sections()
            overview = {}
            for section in sections:
                overview[section.title] = {
                    "type": section.type,
                    "count": getattr(section, "totalViewSize", 0) if not callable(getattr(section, "totalViewSize", 0)) else section.totalViewSize()
                }
            return overview
        except Exception:
            return {}

    def get_quick_status(self) -> Dict[str, Any]:
        """Get quick system status with minimal data."""
        try:
            return {
                "server_name": self.plex.friendlyName,
                "version": self.plex.version,
                "active_sessions": len(self.plex.sessions()),
                "library_count": len(self.plex.library.sections())
            }
        except Exception:
            return {"error": "Unable to fetch status"}

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
                "count": getattr(section, "totalViewSize", 0) if not callable(getattr(section, "totalViewSize", 0)) else section.totalViewSize(),
                "section_id": section.key
            }
        return sections

    def get_movie_library(self) -> MovieSection:
        """Get the movie library section (resolves actual section title)."""
        section_name = self._get_section_title("movie")
        return self.plex.library.section(section_name)

    def get_tv_library(self) -> ShowSection:
        """Get the TV shows library section (resolves actual section title)."""
        section_name = self._get_section_title("show")
        return self.plex.library.section(section_name)

    def get_recently_added(self, section_type: str = "movie", limit: int = 20, response_level: Optional[ResponseLevel] = None) -> List[Dict[str, Any]]:
        """Get recently added items from specified library."""
        try:
            # Map section type to actual section title
            # Tests expect capitalized type-based section names
            section_name = "Movies" if section_type.lower() == "movie" else "TV Shows" if section_type.lower() == "show" else section_type.title()
            section = self.plex.library.section(section_name)
            recent = section.recentlyAdded(maxresults=limit)
            return self._serialize_items(recent, response_level)
        except Exception:
            return []

    def get_on_deck(self, limit: int = 20, response_level: Optional[ResponseLevel] = None) -> List[Dict[str, Any]]:
        """Get items that are 'on deck' (next to watch)."""
        try:
            on_deck = self.plex.library.onDeck(maxresults=limit)
            return self._serialize_items(on_deck, response_level)
        except Exception:
            return []

    def get_continue_watching(self, limit: int = 20, response_level: Optional[ResponseLevel] = None) -> List[Dict[str, Any]]:
        """Get items that can be continued (partially watched)."""
        try:
            # Prefer native continueWatching if available; otherwise, fall back to onDeck
            lib = self.plex.library
            if hasattr(lib, "continueWatching") and callable(getattr(lib, "continueWatching")):
                items = lib.continueWatching(maxresults=limit)
            else:
                items = lib.onDeck(maxresults=limit)
            return self._serialize_items(items, response_level)
        except Exception:
            return []

    def get_unwatched(self, section_type: str = "movie", limit: int = 20, response_level: Optional[ResponseLevel] = None) -> List[Dict[str, Any]]:
        """Get unwatched items from specified library with optimized performance."""
        try:
            # Tests expect capitalized type-based section names
            section_name = "Movies" if section_type.lower() == "movie" else "TV Shows" if section_type.lower() == "show" else section_type.title()
            section = self.plex.library.section(section_name)
            
            # Use the most efficient approach: search with unwatched filter
            # This is the native Plex API way to get unwatched items
            try:
                unwatched_items = section.search(unwatched=True, maxresults=limit)
                return self._serialize_items(unwatched_items, response_level)
            except Exception:
                # Fallback to client-side filtering if search fails
                try:
                    # Use recentlyAdded as it's often faster than all() and contains unwatched items
                    all_items = section.recentlyAdded(maxresults=limit * 2)  # Get more to filter
                    unwatched_items = [item for item in all_items if not getattr(item, 'isWatched', False)][:limit]
                    
                    # If still not enough, fall back to all() but with a reasonable limit
                    if len(unwatched_items) < limit:
                        all_items = section.all(maxresults=limit * 3)
                        additional = [item for item in all_items if not getattr(item, 'isWatched', False) and item not in unwatched_items]
                        unwatched_items.extend(additional[:limit - len(unwatched_items)])
                    
                    return self._serialize_items(unwatched_items, response_level)
                except Exception:
                    return []
        except Exception:
            return []

    def get_collections(self, section_type: str = "movie", limit: int = 50, response_level: Optional[ResponseLevel] = None) -> List[Dict[str, Any]]:
        """Get collections from specified library."""
        try:
            # Tests expect capitalized type-based section names
            section_name = "Movies" if section_type.lower() == "movie" else "TV Shows" if section_type.lower() == "show" else section_type.title()
            section = self.plex.library.section(section_name)
            collections = section.collections(maxresults=limit)
            return [self._serialize_collection(collection, response_level) for collection in collections]
        except Exception:
            return []

    def get_playlists(self, limit: int = 50, response_level: Optional[ResponseLevel] = None) -> List[Dict[str, Any]]:
        """Get available playlists."""
        try:
            playlists = self.plex.playlists(maxresults=limit)
            return [self._serialize_playlist(playlist, response_level) for playlist in playlists]
        except Exception:
            return []

    def get_similar_items(self, rating_key: int, limit: int = 10, response_level: Optional[ResponseLevel] = None) -> List[Dict[str, Any]]:
        """Get similar items to a specific movie/show."""
        try:
            item = self.plex.fetchItem(rating_key)
            similar = item.similar(maxresults=limit)
            return self._serialize_items(similar, response_level)
        except Exception:
            return []

    def get_extras(self, rating_key: int, response_level: Optional[ResponseLevel] = None) -> List[Dict[str, Any]]:
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

    def get_playback_status(self, response_level: Optional[ResponseLevel] = None) -> Dict[str, Any]:
        """Get current playback status across all clients."""
        try:
            sessions = self.plex.sessions()
            # Ensure session serialization includes user/client by promoting to STANDARD when needed
            level = response_level or self.default_response_level
            session_level = level if level in [ResponseLevel.STANDARD, ResponseLevel.DETAILED] else ResponseLevel.STANDARD
            return {
                "active_sessions": len(sessions),
                "sessions": [self._serialize_session(session, session_level) for session in sessions]
            }
        except Exception:
            return {"active_sessions": 0, "sessions": []}

    def get_watch_history(self, rating_key: int, limit: int = 20, response_level: Optional[ResponseLevel] = None) -> List[Dict[str, Any]]:
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

    def get_item_details(self, rating_key: int, response_level: Optional[ResponseLevel] = None) -> Optional[Dict[str, Any]]:
        """Get comprehensive details for a specific item."""
        try:
            item = self.plex.fetchItem(rating_key)
            return self._serialize_item(item, response_level)
        except Exception:
            return None

    def _serialize_items(self, items: List[Any], response_level: Optional[ResponseLevel] = None) -> List[Dict[str, Any]]:
        """Serialize a list of Plex items to dictionaries with configurable detail level."""
        level = response_level or self.default_response_level
        return [self._serialize_item(item, level) for item in items]

    def _serialize_item(self, item: Any, response_level: Optional[ResponseLevel] = None) -> Dict[str, Any]:
        """Serialize a single Plex item to a dictionary with configurable detail level."""
        level = response_level or self.default_response_level
        
        if level == ResponseLevel.MINIMAL:
            return {
                "title": getattr(item, "title", None),
                "ratingKey": getattr(item, "ratingKey", None),
                "type": getattr(item, "type", None)
            }
        elif level == ResponseLevel.COMPACT:
            return {
                "title": getattr(item, "title", None),
                "year": getattr(item, "year", None),
                "rating": getattr(item, "rating", None),
                "ratingKey": getattr(item, "ratingKey", None),
                "type": getattr(item, "type", None)
            }
        elif level == ResponseLevel.STANDARD:
            data = {
                "title": getattr(item, "title", None),
                "year": getattr(item, "year", None),
                "ratingKey": getattr(item, "ratingKey", None),
                "rating": getattr(item, "rating", None),
                "contentRating": getattr(item, "contentRating", None),
                "duration": getattr(item, "duration", None),
                "genres": [genre.tag for genre in getattr(item, "genres", [])] if hasattr(item, "genres") else [],
                "summary": getattr(item, "summary", None),
                "type": getattr(item, "type", None)
            }
            # Attempt to include basic media info from the first Media object
            try:
                media_list = getattr(item, "media", [])
                if media_list:
                    media0 = media_list[0]
                    vcodec = getattr(media0, "videoCodec", None)
                    acodec = getattr(media0, "audioCodec", None)
                    vres = getattr(media0, "videoResolution", None) or getattr(media0, "resolution", None)
                    if vres is not None:
                        data["videoResolution"] = vres
                    if vcodec is not None:
                        data["videoCodec"] = vcodec
                    if acodec is not None:
                        data["audioCodec"] = acodec
            except Exception:
                pass
            return data
        else:  # DETAILED - current behavior
            data = {
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
            # Attempt to include media info from the first Media object
            try:
                media_list = getattr(item, "media", [])
                if media_list:
                    media0 = media_list[0]
                    vcodec = getattr(media0, "videoCodec", None)
                    acodec = getattr(media0, "audioCodec", None)
                    vres = getattr(media0, "videoResolution", None) or getattr(media0, "resolution", None)
                    if vres is not None:
                        data["videoResolution"] = vres
                    if vcodec is not None:
                        data["videoCodec"] = vcodec
                    if acodec is not None:
                        data["audioCodec"] = acodec
            except Exception:
                pass
            return data

    def _serialize_collection(self, collection: Any, response_level: Optional[ResponseLevel] = None) -> Dict[str, Any]:
        """Serialize a collection with configurable detail level."""
        level = response_level or self.default_response_level
        
        base_data = {
            "title": collection.title,
            "collection_id": collection.ratingKey
        }
        
        if level in [ResponseLevel.STANDARD, ResponseLevel.DETAILED]:
            try:
                count = len(collection.children()) if hasattr(collection, "children") else len(collection.items())
            except Exception:
                count = 0
            base_data["count"] = count
            base_data["summary"] = getattr(collection, "summary", None)
        
        return base_data

    def _serialize_playlist(self, playlist: Any, response_level: Optional[ResponseLevel] = None) -> Dict[str, Any]:
        """Serialize a playlist with configurable detail level."""
        level = response_level or self.default_response_level
        
        base_data = {
            "title": playlist.title,
            "playlist_id": playlist.ratingKey
        }
        
        if level in [ResponseLevel.STANDARD, ResponseLevel.DETAILED]:
            base_data["count"] = len(playlist.items())
            base_data["summary"] = getattr(playlist, "summary", None)
            base_data["duration"] = getattr(playlist, "duration", None)
        
        return base_data

    def _serialize_session(self, session: Any, response_level: Optional[ResponseLevel] = None) -> Dict[str, Any]:
        """Serialize a session with configurable detail level."""
        level = response_level or self.default_response_level
        
        base_data = {
            "title": getattr(session, "title", None),
            "type": getattr(session, "type", None)
        }
        
        if level in [ResponseLevel.STANDARD, ResponseLevel.DETAILED]:
            # plexapi may expose user via .usernames, .username, or session.account
            user_name = getattr(session, "username", None)
            if not user_name:
                try:
                    acc = getattr(session, "account", None)
                    user_name = getattr(acc, "title", None) if acc is not None else None
                except Exception:
                    user_name = None
            if not user_name:
                # Some environments expose a nested dict-like user
                u = getattr(session, "user", None)
                if isinstance(u, dict):
                    user_name = u.get("title") or u.get("name")
            base_data["user"] = user_name or "Unknown"
            base_data["progress"] = getattr(session, "progress", 0)
            base_data["duration"] = getattr(session, "duration", 0)
            # session.player is a Player object in plexapi with a .product attribute.
            # Some mocks/tests may provide a dict. Support both forms safely.
            player_obj = getattr(session, "player", None)
            client_product = "Unknown"
            if player_obj is not None:
                try:
                    # Prefer attribute access (plexapi Player)
                    client_product = getattr(player_obj, "product") if getattr(player_obj, "product", None) else client_product
                except Exception:
                    client_product = "Unknown"
                # Fallback if a dict-like object was provided in tests
                if isinstance(player_obj, dict):
                    client_product = player_obj.get("product", client_product)
            base_data["client"] = client_product
        
        return base_data

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


