from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


def _ensure_project_root_on_path() -> Path:
    """Ensure project root is on sys.path for absolute package imports (config, integrations, etc.)."""
    this_file = Path(__file__).resolve()
    project_root = this_file.parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    return project_root


@dataclass
class Candidate:
    id: int
    title: str
    release_year: Optional[int]
    vote_count: int
    vote_average: float


def _to_int_year(date_str: Optional[str]) -> Optional[int]:
    if not date_str:
        return None
    try:
        return int(str(date_str)[:4])
    except Exception:
        return None


def _select_best_candidate(results: Dict[str, Any]) -> Optional[Candidate]:
    items = []
    for item in results.get("results", []):
        if not item:
            continue
        title = (item.get("title") or "").strip()
        if not title:
            continue
        items.append(
            Candidate(
                id=int(item.get("id")),
                title=title,
                release_year=_to_int_year(item.get("release_date")),
                vote_count=int(item.get("vote_count") or 0),
                vote_average=float(item.get("vote_average") or 0.0),
            )
        )

    if not items:
        return None

    # Sort by: vote_count desc, vote_average desc, release_year desc
    items.sort(key=lambda c: (c.vote_count, c.vote_average, c.release_year or 0), reverse=True)
    return items[0]


def _parse_title_and_year(raw_query: str) -> tuple[str, Optional[int]]:
    q = raw_query.strip()
    if q.endswith(")") and "(" in q:
        try:
            open_idx = q.rfind("(")
            year_str = q[open_idx + 1 : -1]
            year = int(year_str)
            title = q[:open_idx].strip()
            return title, year
        except Exception:
            return q, None
    return q, None


async def run_add(query: str) -> int:
    project_root = _ensure_project_root_on_path()

    # Lazy imports after sys.path adjustment
    from config.loader import load_settings, load_runtime_config
    from integrations.tmdb_client import TMDbClient, TMDbResponseLevel
    from integrations.radarr_client import RadarrClient

    settings = load_settings(project_root)
    config = load_runtime_config(project_root)

    # Validate required config
    profile_id = config.get("radarr", {}).get("qualityProfileId")
    root_folder = config.get("radarr", {}).get("rootFolderPath")
    if not settings.tmdb_api_key:
        print("TMDb API key missing in .env (TMDB_API_KEY)")
        return 2
    if not settings.radarr_api_key:
        print("Radarr API key missing in .env (RADARR_API_KEY)")
        return 2
    if not profile_id or not root_folder:
        print("Radarr defaults missing in config/config.yaml (qualityProfileId/rootFolderPath)")
        return 2

    # 1) Search TMDb like the bot would (compact response)
    tmdb = TMDbClient(settings.tmdb_api_key)
    try:
        clean_title, parsed_year = _parse_title_and_year(query)
        data = await tmdb.search_movie(
            query=clean_title,
            year=parsed_year,
            primary_release_year=parsed_year,
            response_level=TMDbResponseLevel.COMPACT,
        )
        # Fallback without year if no results
        if not data.get("results"):
            data = await tmdb.search_movie(
                query=clean_title,
                response_level=TMDbResponseLevel.COMPACT,
            )
        cand = _select_best_candidate(data)
        if not cand:
            print(f"No TMDb results for '{query}'")
            return 3
        print(f"Selected: {cand.title} ({cand.release_year or '????'}) [TMDb {cand.id}]")
    finally:
        try:
            await tmdb.close()
        except Exception:
            pass

    # 2) Add to Radarr via tmdbId with defaults; let client enrich if needed
    radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key or "")
    try:
        resp = await radarr.add_movie(
            tmdb_id=int(cand.id),
            quality_profile_id=int(profile_id),
            root_folder_path=str(root_folder),
            monitored=True,
            search_now=True,
        )
    except Exception as e:  # noqa: BLE001
        print(f"Radarr add failed: {e}")
        try:
            await radarr.close()
        finally:
            return 4

    try:
        await radarr.close()
    except Exception:
        pass

    # Print a concise summary of Radarr's response
    title = (resp.get("title") or "").strip() or cand.title
    year = resp.get("year") or cand.release_year
    movie_id = resp.get("id")
    monitored = resp.get("monitored")
    print(f"Radarr response: id={movie_id}, title={title} ({year}), monitored={monitored}")
    return 0


if __name__ == "__main__":
    # Simple CLI: pass query via env or argv, default to 'Scooby Doo'
    q = os.environ.get("QUERY") or (sys.argv[1] if len(sys.argv) > 1 else "Scooby Doo")
    raise SystemExit(asyncio.run(run_add(q)))


