from __future__ import annotations

import discord
from discord import app_commands
from typing import Optional

from config.loader import load_settings
from integrations.plex_client import PlexClient


def register(client: discord.Client) -> None:
    tree = client.tree
    
    # Media group for Plex and media management
    media_group = app_commands.Group(name="media", description="Manage your media library")

    @media_group.command(name="search", description="Search your Plex library for movies and shows")
    @app_commands.describe(
        query="What to search for (leave empty to see all)",
        limit="Maximum results to show (default: 10)",
        detail="How much detail to show"
    )
    async def search_media(
        interaction: discord.Interaction, 
        query: Optional[str] = None, 
        limit: Optional[int] = 10,
        detail: Optional[str] = "compact"
    ):
        await interaction.response.defer(ephemeral=True)
        
        if detail not in ["minimal", "compact", "standard", "detailed"]:
            detail = "compact"
        
        try:
            settings = load_settings(client.project_root)
            plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
            
            if query:
                results = plex.search_movies(query)
                if not results:
                    await interaction.followup.send(f"No results found for '{query}'", ephemeral=True)
                    return
                
                # Format results based on detail level
                if detail == "minimal":
                    lines = [f"• {m.title} ({getattr(m, 'year', '?')})" for m in results[:limit]]
                elif detail == "compact":
                    lines = [f"• {m.title} ({getattr(m, 'year', '?')}) — ID: {getattr(m, 'ratingKey', 'N/A')}" for m in results[:limit]]
                else:
                    lines = []
                    for m in results[:limit]:
                        rating = getattr(m, 'rating', 'N/A')
                        duration = getattr(m, 'duration', 'N/A')
                        lines.append(f"• {m.title} ({getattr(m, 'year', '?')}) — Rating: {rating}, Duration: {duration}min, ID: {getattr(m, 'ratingKey', 'N/A')}")
                
                text = f"**Results for '{query}':**\n" + "\n".join(lines)
            else:
                # Show recent additions
                results = plex.get_recently_added()
                lines = [f"• {m.title} ({getattr(m, 'year', '?')}) — Added recently" for m in results[:limit]]
                text = f"**Recently Added (showing {min(len(results), limit)}):**\n" + "\n".join(lines)
            
            await interaction.followup.send(text[:1900], ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"Search failed: {str(e)}", ephemeral=True)

    @media_group.command(name="rate", description="Rate a movie or show (1-10)")
    @app_commands.describe(
        rating_key="Plex rating key (from search results)",
        rating="Your rating from 1-10"
    )
    async def rate_media(interaction: discord.Interaction, rating_key: int, rating: int):
        await interaction.response.defer(ephemeral=True)
        
        if rating < 1 or rating > 10:
            await interaction.followup.send("Rating must be between 1 and 10", ephemeral=True)
            return
        
        try:
            settings = load_settings(client.project_root)
            plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
            plex.set_rating(rating_key, rating)
            await interaction.followup.send(f"✅ Rated item {rating_key} with {rating}/10", ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"Failed to set rating: {str(e)}", ephemeral=True)

    @media_group.command(name="recent", description="Show recently added content")
    @app_commands.describe(
        limit="Number of items to show (default: 10)",
        media_type="Type of media (movie, show, or all)"
    )
    async def recent_media(
        interaction: discord.Interaction, 
        limit: Optional[int] = 10,
        media_type: Optional[str] = "movie"
    ):
        await interaction.response.defer(ephemeral=True)
        
        try:
            settings = load_settings(client.project_root)
            plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
            
            results = plex.get_recently_added()
            if media_type != "all":
                results = [r for r in results if getattr(r, 'type', '').lower() == media_type.lower()]
            
            lines = [f"• {m.title} ({getattr(m, 'year', '?')}) — {getattr(m, 'type', 'unknown')}" for m in results[:limit]]
            text = f"**Recently Added {media_type.title()}s:**\n" + "\n".join(lines)
            
            await interaction.followup.send(text[:1900], ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"Failed to get recent items: {str(e)}", ephemeral=True)

    @media_group.command(name="ondeck", description="Show what's next on your watchlist")
    @app_commands.describe(limit="Number of items to show (default: 10)")
    async def on_deck(interaction: discord.Interaction, limit: Optional[int] = 10):
        await interaction.response.defer(ephemeral=True)
        
        try:
            settings = load_settings(client.project_root)
            plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
            
            results = plex.get_on_deck()
            lines = [f"• {m.title} ({getattr(m, 'year', '?')}) — Next episode: {getattr(m, 'viewOffset', 'N/A')}" for m in results[:limit]]
            text = f"**On Deck (Next to Watch):**\n" + "\n".join(lines)
            
            await interaction.followup.send(text[:1900], ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"Failed to get on deck items: {str(e)}", ephemeral=True)

    @media_group.command(name="continue", description="Show content you can continue watching")
    @app_commands.describe(limit="Number of items to show (default: 10)")
    async def continue_watching(interaction: discord.Interaction, limit: Optional[int] = 10):
        await interaction.response.defer(ephemeral=True)
        
        try:
            settings = load_settings(client.project_root)
            plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
            
            results = plex.get_continue_watching()
            lines = [f"• {m.title} ({getattr(m, 'year', '?')}) — Progress: {getattr(m, 'viewOffset', 'N/A')}" for m in results[:limit]]
            text = f"**Continue Watching:**\n" + "\n".join(lines)
            
            await interaction.followup.send(text[:1900], ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"Failed to get continue watching items: {str(e)}", ephemeral=True)

    @media_group.command(name="unwatched", description="Show unwatched content")
    @app_commands.describe(
        limit="Number of items to show (default: 10)",
        media_type="Type of media (movie, show, or all)"
    )
    async def unwatched_media(
        interaction: discord.Interaction, 
        limit: Optional[int] = 10,
        media_type: Optional[str] = "movie"
    ):
        await interaction.response.defer(ephemeral=True)
        
        try:
            settings = load_settings(client.project_root)
            plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
            
            results = plex.get_unwatched()
            if media_type != "all":
                results = [r for r in results if getattr(r, 'type', '').lower() == media_type.lower()]
            
            lines = [f"• {m.title} ({getattr(m, 'year', '?')}) — {getattr(m, 'type', 'unknown')}" for m in results[:limit]]
            text = f"**Unwatched {media_type.title()}s:**\n" + "\n".join(lines)
            
            await interaction.followup.send(text[:1900], ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"Failed to get unwatched items: {str(e)}", ephemeral=True)

    tree.add_command(media_group)
