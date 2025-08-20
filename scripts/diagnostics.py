from __future__ import annotations

import asyncio
from pathlib import Path

from config.loader import load_settings, load_runtime_config
from integrations.plex_client import PlexClient
from integrations.radarr_client import RadarrClient
from integrations.sonarr_client import SonarrClient
from integrations.tmdb_client import TMDbClient


async def diagnostics() -> int:
    project_root = Path(__file__).resolve().parents[1]
    settings = load_settings(project_root)
    config = load_runtime_config(project_root)

    print("Checking Plex...")
    try:
        plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
        _ = plex.plex.friendlyName  # type: ignore[attr-defined]
        print("- OK")
    except Exception as e:  # noqa: BLE001
        print(f"- FAILED: {e}")

    print("Checking Radarr...")
    try:
        radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key or "")
        status = await radarr.system_status()
        print(f"- OK: {status.get('version')}")
        await radarr.close()
    except Exception as e:  # noqa: BLE001
        print(f"- FAILED: {e}")

    print("Checking Sonarr...")
    try:
        sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
        status = await sonarr.system_status()
        print(f"- OK: {status.get('version')}")
        await sonarr.close()
    except Exception as e:  # noqa: BLE001
        print(f"- FAILED: {e}")

    print("Checking TMDb...")
    try:
        tmdb = TMDbClient(settings.tmdb_api_key or "")
        data = await tmdb.search_movie("Inception")
        total = data.get("total_results")
        print(f"- OK: search results {total}")
        await tmdb.close()
    except Exception as e:  # noqa: BLE001
        print(f"- FAILED: {e}")

    print("\nDefaults in config/config.yaml:")
    print(f"- Radarr profile id: {config.get('radarr', {}).get('qualityProfileId')}")
    print(f"- Radarr root: {config.get('radarr', {}).get('rootFolderPath')}")
    print(f"- Sonarr profile id: {config.get('sonarr', {}).get('qualityProfileId')}")
    print(f"- Sonarr root: {config.get('sonarr', {}).get('rootFolderPath')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(diagnostics()))


