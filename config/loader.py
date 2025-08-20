from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv


@dataclass
class Settings:
    discord_token: Optional[str]
    openai_api_key: Optional[str]
    plex_base_url: str
    plex_token: Optional[str]
    radarr_base_url: str
    radarr_api_key: Optional[str]
    sonarr_base_url: str
    sonarr_api_key: Optional[str]
    tmdb_api_key: Optional[str]
    discord_development_guild_id: Optional[str]
    application_id: Optional[str]


def load_settings(project_root: Path) -> Settings:
    env_path = project_root / ".env"
    load_dotenv(env_path)

    return Settings(
        discord_token=os.getenv("DISCORD_TOKEN"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        plex_base_url=os.getenv("PLEX_BASE_URL", "http://localhost:32400"),
        plex_token=os.getenv("PLEX_TOKEN"),
        radarr_base_url=os.getenv("RADARR_BASE_URL", "http://localhost:7878"),
        radarr_api_key=os.getenv("RADARR_API_KEY"),
        sonarr_base_url=os.getenv("SONARR_BASE_URL", "http://localhost:8989"),
        sonarr_api_key=os.getenv("SONARR_API_KEY"),
        tmdb_api_key=os.getenv("TMDB_API_KEY"),
        discord_development_guild_id=os.getenv("DISCORD_GUILD_ID"),
        application_id=os.getenv("APPLICATION_ID"),
    )


def load_runtime_config(project_root: Path) -> dict:
    config_dir = project_root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    if not config_path.exists():
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def is_config_complete(settings: Settings, runtime_config: dict) -> bool:
    required_env = [
        settings.discord_token,
        settings.openai_api_key,
        settings.plex_token,
        settings.radarr_api_key,
        settings.sonarr_api_key,
        settings.tmdb_api_key,
    ]
    if any(v is None or str(v).strip() == "" for v in required_env):
        return False

    # Require Radarr/Sonarr defaults to be present for smoother UX
    radarr_ok = bool(runtime_config.get("radarr", {}).get("qualityProfileId")) and bool(
        runtime_config.get("radarr", {}).get("rootFolderPath")
    )
    sonarr_ok = bool(runtime_config.get("sonarr", {}).get("qualityProfileId")) and bool(
        runtime_config.get("sonarr", {}).get("rootFolderPath")
    )
    return radarr_ok and sonarr_ok

