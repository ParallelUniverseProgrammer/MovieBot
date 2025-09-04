from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Callable
from pathlib import Path
import asyncio
import xml.etree.ElementTree as ET

import httpx

from config.loader import load_settings
from integrations.plex_client import PlexClient, ResponseLevel
from integrations.ttl_cache import shared_cache


class PlexWorker:
    """Unified Plex worker with short TTL caching and in-flight coalescing.

    Notes:
    - Uses PlexClient for most calls via thread pool to avoid blocking
    - Uses a shared AsyncClient for direct HTTP (4K/HDR list)
    - Respects response_level for payload shaping
    - Provides small TTL caches for low-latency repeated reads
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.settings = load_settings(project_root)
        self.plex = PlexClient(self.settings.plex_base_url, self.settings.plex_token or "")
        self._http: Optional[httpx.AsyncClient] = None
        self._inflight: Dict[str, asyncio.Future] = {}

    # -------------------- plumbing --------------------
    def _resp_level(self, value: Optional[str]) -> Optional[ResponseLevel]:
        if not value:
            return None
        try:
            return ResponseLevel(value)
        except Exception:
            return None

    async def _to_thread(self, fn: Callable, *args, **kwargs):
        return await asyncio.to_thread(fn, *args, **kwargs)

    def _cache_key(self, method: str, *args: Any, **kwargs: Any) -> str:
        return f"plex:{method}:{repr(args)}:{repr(sorted(kwargs.items()))}"

    def _get_cache(self, key: str) -> Any:
        return shared_cache.get(key)

    def _set_cache(self, key: str, value: Any, ttl: int) -> None:
        shared_cache.set(key, value, ttl)

    async def _coalesce(self, key: str, coro_factory: Callable[[], asyncio.Future]) -> Any:
        fut = self._inflight.get(key)
        if fut:
            return await fut
        loop = asyncio.get_running_loop()
        fut = loop.create_task(coro_factory())
        self._inflight[key] = fut
        try:
            return await fut
        finally:
            self._inflight.pop(key, None)

    def _http_client(self) -> httpx.AsyncClient:
        if not self._http:
            self._http = httpx.AsyncClient(timeout=httpx.Timeout(3.0, connect=2.0))
        return self._http

    # -------------------- library --------------------
    async def get_library_sections(self, *, bypass_cache: bool = False) -> Dict[str, Any]:
        key = self._cache_key("sections")
        if not bypass_cache:
            cached = self._get_cache(key)
            if cached is not None:
                return {"sections": cached}
        sections = await self._to_thread(self.plex.get_library_sections)
        self._set_cache(key, sections, ttl=600)
        return {"sections": sections}

    # -------------------- lists & discovery --------------------
    async def get_recently_added(self, *, section_type: str, limit: int, response_level: Optional[str], bypass_cache: bool = False) -> Dict[str, Any]:
        rl = self._resp_level(response_level)
        key = self._cache_key("recently_added", section_type, limit, rl.value if rl else None)
        if not bypass_cache:
            cached = self._get_cache(key)
            if cached is not None:
                return cached
        items = await self._to_thread(self.plex.get_recently_added, section_type, limit, rl)
        out = {"items": items, "section_type": section_type, "limit": limit, "total_found": len(items), "response_level": rl.value if rl else "compact"}
        self._set_cache(key, out, ttl=30)
        return out

    async def get_on_deck(self, *, limit: int, response_level: Optional[str], bypass_cache: bool = False) -> Dict[str, Any]:
        rl = self._resp_level(response_level)
        key = self._cache_key("on_deck", limit, rl.value if rl else None)
        if not bypass_cache:
            cached = self._get_cache(key)
            if cached is not None:
                return cached
        items = await self._to_thread(self.plex.get_on_deck, limit, rl)
        out = {"items": items, "limit": limit, "total_found": len(items), "response_level": rl.value if rl else "compact"}
        self._set_cache(key, out, ttl=30)
        return out

    async def get_continue_watching(self, *, limit: int, response_level: Optional[str], bypass_cache: bool = False) -> Dict[str, Any]:
        rl = self._resp_level(response_level)
        key = self._cache_key("continue_watching", limit, rl.value if rl else None)
        if not bypass_cache:
            cached = self._get_cache(key)
            if cached is not None:
                return cached
        items = await self._to_thread(self.plex.get_continue_watching, limit, rl)
        out = {"items": items, "limit": limit, "total_found": len(items), "response_level": rl.value if rl else "compact"}
        self._set_cache(key, out, ttl=30)
        return out

    async def get_unwatched(self, *, section_type: str, limit: int, response_level: Optional[str], bypass_cache: bool = False) -> Dict[str, Any]:
        rl = self._resp_level(response_level)
        key = self._cache_key("unwatched", section_type, limit, rl.value if rl else None)
        if not bypass_cache:
            cached = self._get_cache(key)
            if cached is not None:
                return cached
        
        # Use coalescing to prevent duplicate requests
        async def _fetch_unwatched():
            return await self._to_thread(self.plex.get_unwatched, section_type, limit, rl)
        
        items = await self._coalesce(f"unwatched:{key}", _fetch_unwatched)
        out = {"items": items, "section_type": section_type, "limit": limit, "total_found": len(items), "response_level": rl.value if rl else "compact"}
        
        # Increase cache TTL for unwatched items as they change less frequently
        self._set_cache(key, out, ttl=120)  # 2 minutes instead of 30 seconds
        return out

    async def get_collections(self, *, section_type: str, limit: int, response_level: Optional[str], bypass_cache: bool = False) -> Dict[str, Any]:
        rl = self._resp_level(response_level)
        key = self._cache_key("collections", section_type, limit, rl.value if rl else None)
        if not bypass_cache:
            cached = self._get_cache(key)
            if cached is not None:
                return cached
        collections = await self._to_thread(self.plex.get_collections, section_type, limit, rl)
        out = {"collections": collections, "section_type": section_type, "limit": limit, "total_found": len(collections), "response_level": rl.value if rl else "compact"}
        self._set_cache(key, out, ttl=300)
        return out

    async def get_playlists(self, *, limit: int, response_level: Optional[str], bypass_cache: bool = False) -> Dict[str, Any]:
        rl = self._resp_level(response_level)
        key = self._cache_key("playlists", limit, rl.value if rl else None)
        if not bypass_cache:
            cached = self._get_cache(key)
            if cached is not None:
                return cached
        playlists = await self._to_thread(self.plex.get_playlists, limit, rl)
        out = {"playlists": playlists, "limit": limit, "total_found": len(playlists), "response_level": rl.value if rl else "compact"}
        self._set_cache(key, out, ttl=300)
        return out

    # -------------------- items --------------------
    async def get_similar_items(self, *, rating_key: int, limit: int, response_level: Optional[str], bypass_cache: bool = False) -> Dict[str, Any]:
        rl = self._resp_level(response_level)
        key = self._cache_key("similar", rating_key, limit, rl.value if rl else None)
        if not bypass_cache:
            cached = self._get_cache(key)
            if cached is not None:
                return cached
        items = await self._to_thread(self.plex.get_similar_items, int(rating_key), int(limit), rl)
        out = {"items": items, "rating_key": int(rating_key), "limit": int(limit), "total_found": len(items), "response_level": rl.value if rl else "compact"}
        self._set_cache(key, out, ttl=120)
        return out

    async def get_extras(self, *, rating_key: int, bypass_cache: bool = False) -> Dict[str, Any]:
        key = self._cache_key("extras", rating_key)
        if not bypass_cache:
            cached = self._get_cache(key)
            if cached is not None:
                return cached
        extras = await self._to_thread(self.plex.get_extras, int(rating_key))
        out = {"extras": extras, "rating_key": int(rating_key), "total_found": len(extras)}
        self._set_cache(key, out, ttl=120)
        return out

    async def get_item_details(self, *, rating_key: int, response_level: Optional[str], bypass_cache: bool = False) -> Dict[str, Any]:
        rl = self._resp_level(response_level)
        key = self._cache_key("item_details", rating_key, rl.value if rl else None)
        if not bypass_cache:
            cached = self._get_cache(key)
            if cached is not None:
                return cached
        item = await self._to_thread(self.plex.get_item_details, int(rating_key), rl)
        out = {"item": item, "response_level": rl.value if rl else "detailed"} if item else {"error": "Item not found", "rating_key": int(rating_key)}
        self._set_cache(key, out, ttl=120)
        return out

    async def set_rating(self, *, rating_key: int, rating: int) -> Dict[str, Any]:
        await self._to_thread(self.plex.set_rating, int(rating_key), int(rating))
        # no cache for mutations
        return {"ok": True}

    # -------------------- playback & history --------------------
    async def get_playback_status(self, *, response_level: Optional[str], bypass_cache: bool = False) -> Dict[str, Any]:
        rl = self._resp_level(response_level)
        key = self._cache_key("playback_status", rl.value if rl else None)
        if not bypass_cache:
            cached = self._get_cache(key)
            if cached is not None:
                return cached
        status = await self._to_thread(self.plex.get_playback_status, rl)
        out = {**status, "response_level": rl.value if rl else "compact"}
        self._set_cache(key, out, ttl=10)
        return out

    async def get_watch_history(self, *, rating_key: int, limit: int, bypass_cache: bool = False) -> Dict[str, Any]:
        key = self._cache_key("watch_history", rating_key, limit)
        if not bypass_cache:
            cached = self._get_cache(key)
            if cached is not None:
                return cached
        history = await self._to_thread(self.plex.get_watch_history, int(rating_key), int(limit))
        out = {"history": history, "rating_key": int(rating_key), "limit": int(limit), "total_found": len(history)}
        self._set_cache(key, out, ttl=60)
        return out

    # -------------------- batch operations --------------------
    async def get_library_overview(self, *, response_level: Optional[str] = None, bypass_cache: bool = False) -> Dict[str, Any]:
        """Get a comprehensive library overview with all common data in one optimized call."""
        rl = self._resp_level(response_level)
        key = self._cache_key("library_overview", rl.value if rl else None)
        if not bypass_cache:
            cached = self._get_cache(key)
            if cached is not None:
                return cached
        
        # Fetch multiple data types in parallel for better performance
        async def _fetch_overview():
            tasks = [
                self._to_thread(self.plex.get_library_sections),
                self._to_thread(self.plex.get_recently_added, "movie", 10, rl),
                self._to_thread(self.plex.get_recently_added, "show", 10, rl),
                self._to_thread(self.plex.get_unwatched, "movie", 10, rl),
                self._to_thread(self.plex.get_unwatched, "show", 10, rl),
                self._to_thread(self.plex.get_on_deck, 10, rl),
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            return {
                "sections": results[0] if not isinstance(results[0], Exception) else {},
                "recent_movies": results[1] if not isinstance(results[1], Exception) else [],
                "recent_shows": results[2] if not isinstance(results[2], Exception) else [],
                "unwatched_movies": results[3] if not isinstance(results[3], Exception) else [],
                "unwatched_shows": results[4] if not isinstance(results[4], Exception) else [],
                "on_deck": results[5] if not isinstance(results[5], Exception) else [],
                "response_level": rl.value if rl else "compact"
            }
        
        overview = await self._coalesce(f"overview:{key}", _fetch_overview)
        self._set_cache(key, overview, ttl=60)  # 1 minute cache for overview
        return overview

    # -------------------- 4K/HDR via HTTP --------------------
    def _parse_videos(self, xml_text: str, response_level: Optional[ResponseLevel]) -> List[Dict[str, Any]]:
        root = ET.fromstring(xml_text)
        items: List[Dict[str, Any]] = []
        for v in root.findall('.//Video'):
            title = v.get('title')
            year = v.get('year')
            rating_key = v.get('ratingKey')
            media_type = v.get('type')

            video_resolution = v.get('videoResolution') or v.get('resolution')
            video_codec: Optional[str] = None
            audio_codec: Optional[str] = None
            has_hdr = False

            def _as_int(val: Optional[str]) -> Optional[int]:
                if val and str(val).isdigit():
                    try:
                        return int(val)
                    except Exception:
                        return None
                return None

            for m in v.findall('Media'):
                if not video_resolution:
                    video_resolution = m.get('videoResolution') or m.get('resolution')
                if not video_codec:
                    video_codec = m.get('videoCodec')
                if not audio_codec:
                    audio_codec = m.get('audioCodec')
                if not video_resolution:
                    width = _as_int(m.get('width'))
                    height = _as_int(m.get('height'))
                    if width and height:
                        if width >= 3800 or height >= 2000:
                            video_resolution = '4k'
                        elif height >= 1000 or width >= 1700:
                            video_resolution = '1080'
                        elif height and height >= 700:
                            video_resolution = '720'
                vdr = (m.get('videoDynamicRange') or '').upper()
                if any(tag in vdr for tag in ('HDR', 'DOLBY VISION', 'HLG', 'PQ', 'HDR10')):
                    has_hdr = True
                hdr_attr = (m.get('hdr') or '').lower()
                if hdr_attr in {'1', 'true', 'yes'}:
                    has_hdr = True
                for s in m.findall('.//Stream'):
                    attvals = ' '.join([str(vv).lower() for vv in s.attrib.values()])
                    if any(k in attvals for k in ['hdr', 'dolby vision', 'dovi', 'hlg', 'pq', 'smpte2084', 'hdr10']):
                        has_hdr = True

            item: Dict[str, Any] = {
                'title': title,
                'year': int(year) if year and year.isdigit() else None,
                'ratingKey': int(rating_key) if rating_key and rating_key.isdigit() else rating_key,
                'type': media_type,
            }
            if response_level in [ResponseLevel.STANDARD, ResponseLevel.DETAILED, None]:
                item['videoResolution'] = video_resolution
                item['hasHDR'] = has_hdr
                if video_codec:
                    item['videoCodec'] = video_codec
                if audio_codec:
                    item['audioCodec'] = audio_codec
            items.append(item)
        return items

    async def get_movies_4k_or_hdr(self, *, limit: int, section_id: Optional[str], or_semantics: bool, response_level: Optional[str], bypass_cache: bool = False) -> Dict[str, Any]:
        rl = self._resp_level(response_level)
        key = self._cache_key("movies_4k_hdr", limit, section_id, or_semantics, rl.value if rl else None)
        if not bypass_cache:
            cached = self._get_cache(key)
            if cached is not None:
                return cached

        # Discover movie section id if not provided
        sid = section_id
        if not sid:
            sections = await self._to_thread(self.plex.get_library_sections)
            chosen = None
            for _title, info in sections.items():
                if info.get('type') == 'movie':
                    chosen = info.get('section_id')
                    break
            if not chosen and sections:
                chosen = next(iter(sections.values())).get('section_id')
            if not chosen:
                raise ValueError('No Plex library sections available')
            sid = str(chosen)
        else:
            sid = str(sid)

        base_url = self.settings.plex_base_url.rstrip('/')
        token = self.settings.plex_token or ''
        if not token:
            raise ValueError('PLEX_TOKEN is missing. Set it in your .env via the setup wizard.')

        async def _fetch(params: Dict[str, Any]) -> List[Dict[str, Any]]:
            qp: Dict[str, Any] = {
                'X-Plex-Token': token,
                'X-Plex-Container-Start': '0',
                'X-Plex-Container-Size': str(limit),
                'type': '1',
            }
            qp.update(params)
            url = f"{base_url}/library/sections/{sid}/all"
            client = self._http_client()
            r = await client.get(url, params=qp, headers={'Accept': 'application/xml'})
            r.raise_for_status()
            return self._parse_videos(r.text, rl)

        attempts: List[Tuple[Dict[str, Any], int, Optional[str]]] = []
        items: List[Dict[str, Any]] = []

        async def _run():
            nonlocal items
            # Try OR variants first if requested
            if or_semantics:
                variants = [
                    {'or': '1', 'resolution': '4k', 'hdr': '1'},
                    {'or': '1', 'videoResolution': '4k', 'hdr': '1'},
                    {'or': '1', 'resolution': '4k', 'hdr': 'true'},
                    {'or': '1', 'videoResolution': '4k', 'hdr': 'true'},
                ]
                for p in variants:
                    try:
                        res = await _fetch(p)
                        attempts.append((p, len(res), None))
                        if res:
                            items = res
                            break
                    except Exception as e:
                        attempts.append((p, 0, str(e)))

            # If still empty, union fallbacks
            if not items:
                unions: Dict[Any, Dict[str, Any]] = {}
                fallbacks = [
                    {'resolution': '4k'},
                    {'videoResolution': '4k'},
                    {'hdr': '1'},
                    {'hdr': 'true'},
                ]
                for p in fallbacks:
                    try:
                        res = await _fetch(p)
                        attempts.append((p, len(res), None))
                        for it in res:
                            rk = it.get('ratingKey')
                            unions[rk] = it
                        if len(unions) >= limit:
                            break
                    except Exception as e:
                        attempts.append((p, 0, str(e)))
                items = list(unions.values())[:limit]

            return {
                'items': items,
                'total_found': len(items),
                'section_id': sid,
                'attempts': attempts,
                'response_level': rl.value if rl else 'compact',
            }

        # coalesce concurrent identical calls
        out = await self._coalesce(key, _run)
        self._set_cache(key, out, ttl=60)
        return out


