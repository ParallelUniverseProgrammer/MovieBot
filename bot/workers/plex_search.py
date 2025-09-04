from __future__ import annotations

from typing import Any, Dict, List, Optional
from pathlib import Path
import asyncio

from config.loader import load_settings
from integrations.plex_client import PlexClient, ResponseLevel


class PlexSearchWorker:
    """Specialized worker for executing Plex library searches with normalization.

    This worker centralizes argument normalization, sensible defaults, and
    forwards the request to PlexClient.search_movies_filtered on a thread pool
    to avoid blocking the event loop.
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.settings = load_settings(project_root)
        # Reuse a single PlexClient instance for better performance
        self._plex_client: Optional[PlexClient] = None

    def _get_plex_client(self) -> PlexClient:
        """Get or create a reusable PlexClient instance."""
        if self._plex_client is None:
            self._plex_client = PlexClient(
                self.settings.plex_base_url, 
                self.settings.plex_token or ""
            )
        return self._plex_client

    async def search(
        self,
        *,
        query: Optional[str] = None,
        limit: Optional[int] = 20,
        response_level: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Search movies with advanced filters and sort options.

        Args are shaped like the search_plex tool:
        - query: Optional title substring
        - limit: Max items
        - response_level: one of minimal|compact|standard|detailed
        - filters: {year_min, year_max, genres, actors, directors,
                    content_rating, rating_min, rating_max, sort_by, sort_order}
        """
        query_str = (query or "").strip()
        f: Dict[str, Any] = dict(filters or {})

        # Normalize list-like filters; accept str and coerce into single-item lists
        for k in ("genres", "actors", "directors"):
            v = f.get(k)
            if isinstance(v, str) and v.strip():
                f[k] = [v.strip()]

        # Defaults and coercions
        sort_by = f.get("sort_by", "title")
        sort_order = f.get("sort_order", "asc")

        # Map response level to enum if provided
        resp_level: Optional[ResponseLevel] = None
        if isinstance(response_level, str) and response_level.strip():
            resp_level = ResponseLevel(response_level.strip())

        plex = self._get_plex_client()

        results: List[Dict[str, Any]] = await asyncio.to_thread(
            plex.search_movies_filtered,
            query_str or None,
            year_min=f.get("year_min"),
            year_max=f.get("year_max"),
            genres=f.get("genres"),
            actors=f.get("actors"),
            directors=f.get("directors"),
            content_rating=f.get("content_rating"),
            rating_min=f.get("rating_min"),
            rating_max=f.get("rating_max"),
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit or 20,
            response_level=resp_level,
        )

        return {
            "items": results,
            "total_found": len(results),
            "filters_applied": f,
            "query": query_str,
            "response_level": resp_level.value if resp_level else "compact",
        }


