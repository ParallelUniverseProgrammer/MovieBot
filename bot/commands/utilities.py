from __future__ import annotations

import discord
from discord import app_commands
from typing import Optional

from config.loader import load_settings


def register(client: discord.Client) -> None:
    tree = client.tree
    
    # Utilities group for helpful tools
    utils_group = app_commands.Group(name="utils", description="Utility commands and helpers")

    @utils_group.command(name="ping", description="Check if the bot is responsive")
    async def ping(interaction: discord.Interaction):
        await interaction.response.send_message("🏓 Pong! Bot is online and responsive.", ephemeral=True)

    @utils_group.command(name="help", description="Show available commands and their usage")
    async def show_help(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        help_text = """**🎬 MovieBot Commands**

**📺 Media Management (`/media`)**
• `/media search` - Search your Plex library
• `/media rate` - Rate movies/shows (1-10)
• `/media recent` - Show recently added content
• `/media ondeck` - Show what's next to watch
• `/media continue` - Show content to continue watching
• `/media unwatched` - Show unwatched content

**🔍 Discovery (`/discover`)**
• `/discover search` - Search TMDb for new content
• `/discover trending` - Show trending content
• `/discover popular` - Show popular content
• `/discover upcoming` - Show upcoming releases
• `/discover nowplaying` - Show movies in theaters

**⚙️ Management (`/manage`)**
• `/manage addmovie` - Add movie to Radarr
• `/manage addseries` - Add series to Sonarr
• `/manage queue` - Show download queue
• `/manage status` - Show system status
• `/manage wanted` - Show missing content

**⚙️ Preferences (`/prefs`)**
• `/prefs show` - Show household preferences
• `/prefs set` - Set preference values
• `/prefs add` - Add to list preferences
• `/prefs remove` - Remove from list preferences
• `/prefs search` - Search preferences
• `/prefs reset` - Reset all preferences

**🛠️ Utilities (`/utils`)**
• `/utils ping` - Check bot responsiveness
• `/utils help` - Show this help message
• `/utils info` - Show bot and system info

**💬 AI Chat**
• Mention the bot or DM it to start a conversation
• The bot can use all available tools to help you

**💡 Tips:**
• Use `/discover search` to find TMDb IDs for adding content
• Use `/media search` to find Plex rating keys for rating
• Set up default quality profiles in config/config.yaml
• Use `/prefs` to teach the bot about your household's taste

Need help with a specific command? Just ask!"""
        
        await interaction.followup.send(help_text[:1900], ephemeral=True)

    @utils_group.command(name="info", description="Show bot and system information")
    async def show_info(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            settings = load_settings(client.project_root)
            
            info_lines = [
                "**🤖 Bot Information**",
                f"• Project Root: {client.project_root}",
                "",
                "**🔑 API Keys Status**",
                f"• Discord Token: {'✅ Configured' if settings.discord_token else '❌ Missing'}",
                f"• Plex Token: {'✅ Configured' if settings.plex_token else '❌ Missing'}",
                f"• TMDb API Key: {'✅ Configured' if settings.tmdb_api_key else '❌ Missing'}",
                f"• Radarr API Key: {'✅ Configured' if settings.radarr_api_key else '❌ Missing'}",
                f"• Sonarr API Key: {'✅ Configured' if settings.sonarr_api_key else '❌ Missing'}",
                "",
                "**🌐 Service URLs**",
                f"• Plex: {settings.plex_base_url or 'Not configured'}",
                f"• Radarr: {settings.radarr_base_url or 'Not configured'}",
                f"• Sonarr: {settings.sonarr_base_url or 'Not configured'}",
                "",
                "**💡 Next Steps**",
                "• Configure missing API keys in your .env file",
                "• Set up service URLs if not configured",
                "• Use `/utils help` for command usage",
                "• Mention the bot to start chatting!"
            ]
            
            info_text = "\n".join(info_lines)
            await interaction.followup.send(info_text[:1900], ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to get info: {str(e)}", ephemeral=True)

    @utils_group.command(name="status", description="Quick health check of all services")
    async def quick_status(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            settings = load_settings(client.project_root)
            
            status_lines = ["**🔍 Quick Status Check**"]
            
            # Check Plex
            if settings.plex_base_url and settings.plex_token:
                try:
                    from integrations.plex_client import PlexClient
                    plex = PlexClient(settings.plex_base_url, settings.plex_token)
                    # Try to get library sections as a health check
                    sections = plex.get_library_sections()
                    if sections:
                        status_lines.append("• Plex: ✅ Connected and responsive")
                    else:
                        status_lines.append("• Plex: ⚠️ Connected but no libraries found")
                except Exception:
                    status_lines.append("• Plex: ❌ Connection failed")
            else:
                status_lines.append("• Plex: ⚠️ Not configured")
            
            # Check TMDb
            if settings.tmdb_api_key:
                try:
                    from integrations.tmdb_client import TMDbClient
                    tmdb = TMDbClient(settings.tmdb_api_key)
                    # Try a simple API call
                    await tmdb.popular_movies()
                    await tmdb.close()
                    status_lines.append("• TMDb: ✅ API working")
                except Exception:
                    status_lines.append("• TMDb: ❌ API error")
            else:
                status_lines.append("• TMDb: ⚠️ Not configured")
            
            # Check Radarr
            if settings.radarr_base_url and settings.radarr_api_key:
                try:
                    from integrations.radarr_client import RadarrClient
                    radarr = RadarrClient(settings.radarr_base_url, settings.radarr_api_key)
                    await radarr.system_status()
                    await radarr.close()
                    status_lines.append("• Radarr: ✅ Connected and responsive")
                except Exception:
                    status_lines.append("• Radarr: ❌ Connection failed")
            else:
                status_lines.append("• Radarr: ⚠️ Not configured")
            
            # Check Sonarr
            if settings.sonarr_base_url and settings.sonarr_api_key:
                try:
                    from integrations.sonarr_client import SonarrClient
                    sonarr = SonarrClient(settings.sonarr_base_url, settings.sonarr_api_key)
                    await sonarr.system_status()
                    await sonarr.close()
                    status_lines.append("• Sonarr: ✅ Connected and responsive")
                except Exception:
                    status_lines.append("• Sonarr: ❌ Connection failed")
            else:
                status_lines.append("• Sonarr: ⚠️ Not configured")
            
            status_lines.append("")
            status_lines.append("**💡 Note:** This is a basic connectivity check.")
            status_lines.append("Use `/manage status` for detailed system information.")
            
            status_text = "\n".join(status_lines)
            await interaction.followup.send(status_text[:1900], ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Status check failed: {str(e)}", ephemeral=True)

    tree.add_command(utils_group)
