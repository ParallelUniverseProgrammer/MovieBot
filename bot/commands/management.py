from __future__ import annotations

import discord
from discord import app_commands
from typing import Optional

from config.loader import load_settings, load_runtime_config
from integrations.radarr_client import RadarrClient
from integrations.sonarr_client import SonarrClient


def register(client: discord.Client) -> None:
    tree = client.tree
    
    # Management group for Radarr and Sonarr
    management_group = app_commands.Group(name="manage", description="Manage your media downloads")

    @management_group.command(name="addmovie", description="Add a movie to Radarr by TMDb ID")
    @app_commands.describe(
        tmdb_id="TMDb movie ID (from discover commands)",
        profile_id="Quality profile ID (optional)",
        root="Root folder path (optional)"
    )
    async def add_movie(
        interaction: discord.Interaction, 
        tmdb_id: int, 
        profile_id: Optional[int] = None, 
        root: Optional[str] = None
    ):
        await interaction.response.defer(ephemeral=True)
        
        try:
            settings = load_settings(client.project_root)
            config = load_runtime_config(client.project_root)
            
            # Get defaults from config
            profile = profile_id or config.get("radarr", {}).get("qualityProfileId")
            folder = root or config.get("radarr", {}).get("rootFolderPath")
            
            if not profile or not folder:
                await interaction.followup.send(
                    f"⚠️ Radarr configuration missing. Profile: {profile}, Folder: {folder}. "
                    "Set defaults in config/config.yaml or pass them as arguments.", 
                    ephemeral=True
                )
                return
            
            radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key or "")
            
            # First lookup the movie to get details
            lookup_result = await radarr.lookup(term=str(tmdb_id))
            if not lookup_result:
                await interaction.followup.send(f"❌ Movie with TMDb ID {tmdb_id} not found", ephemeral=True)
                await radarr.close()
                return
            
            # Add the movie
            result = await radarr.add_movie(
                tmdb_id=tmdb_id, 
                quality_profile_id=int(profile), 
                root_folder_path=str(folder)
            )
            
            await radarr.close()
            
            movie_title = lookup_result.get('title', f'TMDb ID {tmdb_id}')
            await interaction.followup.send(
                f"✅ Added **{movie_title}** to Radarr!\n"
                f"Quality Profile: {profile}\n"
                f"Folder: {folder}", 
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to add movie: {str(e)}", ephemeral=True)

    @management_group.command(name="addseries", description="Add a TV series to Sonarr by TVDb ID")
    @app_commands.describe(
        tvdb_id="TVDb series ID (from discover commands)",
        profile_id="Quality profile ID (optional)",
        root="Root folder path (optional)"
    )
    async def add_series(
        interaction: discord.Interaction, 
        tvdb_id: int, 
        profile_id: Optional[int] = None, 
        root: Optional[str] = None
    ):
        await interaction.response.defer(ephemeral=True)
        
        try:
            settings = load_settings(client.project_root)
            config = load_runtime_config(client.project_root)
            
            # Get defaults from config
            profile = profile_id or config.get("sonarr", {}).get("qualityProfileId")
            folder = root or config.get("sonarr", {}).get("rootFolderPath")
            
            if not profile or not folder:
                await interaction.followup.send(
                    f"⚠️ Sonarr configuration missing. Profile: {profile}, Folder: {folder}. "
                    "Set defaults in config/config.yaml or pass them as arguments.", 
                    ephemeral=True
                )
                return
            
            sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
            
            # First lookup the series to get details
            lookup_result = await sonarr.lookup(term=str(tvdb_id))
            if not lookup_result:
                await interaction.followup.send(f"❌ Series with TVDb ID {tvdb_id} not found", ephemeral=True)
                await sonarr.close()
                return
            
            # Add the series
            result = await sonarr.add_series(
                tvdb_id=tvdb_id, 
                quality_profile_id=int(profile), 
                root_folder_path=str(folder)
            )
            
            await sonarr.close()
            
            series_title = lookup_result.get('title', f'TVDb ID {tvdb_id}')
            await interaction.followup.send(
                f"✅ Added **{series_title}** to Sonarr!\n"
                f"Quality Profile: {profile}\n"
                f"Folder: {folder}", 
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to add series: {str(e)}", ephemeral=True)

    @management_group.command(name="queue", description="Show current download queue")
    @app_commands.describe(service="Which service to check (radarr, sonarr, or both)")
    async def show_queue(interaction: discord.Interaction, service: str = "both"):
        await interaction.response.defer(ephemeral=True)
        
        if service not in ["radarr", "sonarr", "both"]:
            service = "both"
        
        lines = []
        
        try:
            settings = load_settings(client.project_root)
            
            if service in ["radarr", "both"]:
                try:
                    radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key or "")
                    radarr_queue = await radarr.get_queue()
                    await radarr.close()
                    
                    if radarr_queue:
                        lines.append("**Radarr Queue:**")
                        for item in radarr_queue[:10]:  # Limit to 10 items
                            title = item.get('title', 'Unknown')
                            status = item.get('trackedDownloadStatus', 'Unknown')
                            progress = item.get('trackedDownloadState', 'Unknown')
                            lines.append(f"• {title} — {status} ({progress})")
                    else:
                        lines.append("**Radarr Queue:** Empty")
                except Exception as e:
                    lines.append(f"**Radarr Queue:** Error: {str(e)}")
            
            if service in ["sonarr", "both"]:
                try:
                    sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
                    sonarr_queue = await sonarr.get_queue()
                    await sonarr.close()
                    
                    if lines:
                        lines.append("")
                    if sonarr_queue:
                        lines.append("**Sonarr Queue:**")
                        for item in sonarr_queue[:10]:  # Limit to 10 items
                            title = item.get('series', {}).get('title', 'Unknown')
                            episode = item.get('episode', {}).get('title', 'Unknown')
                            status = item.get('trackedDownloadStatus', 'Unknown')
                            lines.append(f"• {title} - {episode} — {status}")
                    else:
                        lines.append("**Sonarr Queue:** Empty")
                except Exception as e:
                    lines.append(f"**Sonarr Queue:** Error: {str(e)}")
            
            if not lines:
                lines.append("No queue information available")
            
            text = "\n".join(lines)
            await interaction.followup.send(text[:1900], ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to get queue: {str(e)}", ephemeral=True)

    @management_group.command(name="status", description="Show system status")
    @app_commands.describe(service="Which service to check (radarr, sonarr, or both)")
    async def system_status(interaction: discord.Interaction, service: str = "both"):
        await interaction.response.defer(ephemeral=True)
        
        if service not in ["radarr", "sonarr", "both"]:
            service = "both"
        
        lines = []
        
        try:
            settings = load_settings(client.project_root)
            
            if service in ["radarr", "both"]:
                try:
                    radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key or "")
                    status = await radarr.system_status()
                    health = await radarr.health()
                    await radarr.close()
                    
                    lines.append("**Radarr Status:**")
                    lines.append(f"• Version: {status.get('version', 'Unknown')}")
                    lines.append(f"• Start Time: {status.get('startTime', 'Unknown')}")
                    
                    if health:
                        lines.append("• Health: ✅ Good")
                    else:
                        lines.append("• Health: ⚠️ Issues detected")
                        
                except Exception as e:
                    lines.append(f"**Radarr Status:** Error: {str(e)}")
            
            if service in ["sonarr", "both"]:
                try:
                    sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
                    status = await sonarr.system_status()
                    health = await sonarr.health()
                    await sonarr.close()
                    
                    if lines:
                        lines.append("")
                    lines.append("**Sonarr Status:**")
                    lines.append(f"• Version: {status.get('version', 'Unknown')}")
                    lines.append(f"• Start Time: {status.get('startTime', 'Unknown')}")
                    
                    if health:
                        lines.append("• Health: ✅ Good")
                    else:
                        lines.append("• Health: ⚠️ Issues detected")
                        
                except Exception as e:
                    lines.append(f"**Sonarr Status:** Error: {str(e)}")
            
            if not lines:
                lines.append("No status information available")
            
            text = "\n".join(lines)
            await interaction.followup.send(text[:1900], ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to get status: {str(e)}", ephemeral=True)

    @management_group.command(name="wanted", description="Show wanted/missing content")
    @app_commands.describe(
        service="Which service to check (radarr, sonarr, or both)",
        limit="Maximum results to show (default: 10)"
    )
    async def show_wanted(
        interaction: discord.Interaction, 
        service: str = "both",
        limit: Optional[int] = 10
    ):
        await interaction.response.defer(ephemeral=True)
        
        if service not in ["radarr", "sonarr", "both"]:
            service = "both"
        
        lines = []
        
        try:
            settings = load_settings(client.project_root)
            
            if service in ["radarr", "both"]:
                try:
                    radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key or "")
                    wanted = await radarr.get_wanted()
                    await radarr.close()
                    
                    if wanted and wanted.get('records'):
                        lines.append("**Radarr Wanted (Missing Movies):**")
                        for movie in wanted['records'][:limit//2]:
                            title = movie.get('title', 'Unknown')
                            year = movie.get('year', 'Unknown')
                            lines.append(f"• {title} ({year})")
                    else:
                        lines.append("**Radarr Wanted:** No missing movies")
                except Exception as e:
                    lines.append(f"**Radarr Wanted:** Error: {str(e)}")
            
            if service in ["sonarr", "both"]:
                try:
                    sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key or "")
                    wanted = await sonarr.get_wanted()
                    await sonarr.close()
                    
                    if lines:
                        lines.append("")
                    if wanted and wanted.get('records'):
                        lines.append("**Sonarr Wanted (Missing Episodes):**")
                        for episode in wanted['records'][:limit//2]:
                            series = episode.get('series', {}).get('title', 'Unknown')
                            episode_title = episode.get('episode', {}).get('title', 'Unknown')
                            season = episode.get('episode', {}).get('seasonNumber', 'Unknown')
                            lines.append(f"• {series} S{season} - {episode_title}")
                    else:
                        lines.append("**Sonarr Wanted:** No missing episodes")
                except Exception as e:
                    lines.append(f"**Sonarr Wanted:** Error: {str(e)}")
            
            if not lines:
                lines.append("No wanted information available")
            
            text = "\n".join(lines)
            await interaction.followup.send(text[:1900], ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to get wanted items: {str(e)}", ephemeral=True)

    tree.add_command(management_group)
