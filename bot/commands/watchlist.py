from __future__ import annotations

import discord
from discord import app_commands

from config.loader import load_settings, load_runtime_config
from integrations.radarr_client import RadarrClient
from integrations.sonarr_client import SonarrClient


def register(client: discord.Client) -> None:
    tree = client.tree

    group = app_commands.Group(name="watchlist", description="Manage Radarr/Sonarr watchlists")

    @group.command(name="addmovie", description="Add a movie to Radarr by TMDb id")
    @app_commands.describe(tmdb_id="TMDb ID", profile_id="Quality profile id (optional)", root="Root folder path (optional)")
    async def addmovie(interaction: discord.Interaction, tmdb_id: int, profile_id: int | None = None, root: str | None = None) -> None:
        await interaction.response.defer(ephemeral=True)
        settings = load_settings(client.project_root)  # type: ignore[attr-defined]
        config = load_runtime_config(client.project_root)  # type: ignore[attr-defined]
        profile = profile_id or config.get("radarr", {}).get("qualityProfileId")
        folder = root or config.get("radarr", {}).get("rootFolderPath")
        if not profile or not folder:
            await interaction.followup.send(
                f"Radarr configuration missing. Profile: {profile}, Folder: {folder}. "
                "Set defaults in config/config.yaml or pass them as arguments.", 
                ephemeral=True
            )
            return
        try:
            radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key or "")
            data = await radarr.add_movie(tmdb_id=tmdb_id, quality_profile_id=int(profile), root_folder_path=str(folder))
            await radarr.close()
            await interaction.followup.send(f"Added TMDb {tmdb_id} to Radarr.", ephemeral=True)
        except Exception as e:  # noqa: BLE001
            await interaction.followup.send(f"Radarr add failed: {e}", ephemeral=True)

    @group.command(name="addseries", description="Add a series to Sonarr by TVDb id")
    @app_commands.describe(tvdb_id="TVDb ID", profile_id="Quality profile id (optional)", root="Root folder path (optional)")
    async def addseries(interaction: discord.Interaction, tvdb_id: int, profile_id: int | None = None, root: str | None = None) -> None:
        await interaction.response.defer(ephemeral=True)
        settings = load_settings(client.project_root)  # type: ignore[attr-defined]
        config = load_runtime_config(client.project_root)  # type: ignore[attr-defined]
        profile = profile_id or config.get("sonarr", {}).get("qualityProfileId")
        folder = root or config.get("sonarr", {}).get("rootFolderPath")
        if not profile or not folder:
            await interaction.followup.send(
                f"Sonarr configuration missing. Profile: {profile}, Folder: {folder}. "
                "Set defaults in config/config.yaml or pass them as arguments.", 
                ephemeral=True
            )
            return
        try:
            sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
            data = await sonarr.add_series(tvdb_id=tvdb_id, quality_profile_id=int(profile), root_folder_path=str(folder))
            await sonarr.close()
            await interaction.followup.send(f"Added TVDb {tvdb_id} to Sonarr.", ephemeral=True)
        except Exception as e:  # noqa: BLE001
            await interaction.followup.send(f"Sonarr add failed: {e}", ephemeral=True)

    tree.add_command(group)


