from __future__ import annotations

import discord
from discord import app_commands
from typing import Optional, List, Dict, Any

from config.loader import load_settings
from integrations.plex_client import PlexClient
from ..discord_embeds import MovieBotEmbeds, ProgressIndicator


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
        
        # Create progress indicator
        progress_embed = MovieBotEmbeds.create_progress_embed(
            "Searching Plex Library",
            f"Looking for '{query or 'recent content'}'..." if query else "Getting recently added content...",
            progress=0.1,
            status="working"
        )
        await interaction.followup.send(embed=progress_embed, ephemeral=True)
        
        try:
            settings = load_settings(client.project_root)
            plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
            
            # Update progress
            progress_embed = MovieBotEmbeds.create_progress_embed(
                "Searching Plex Library",
                "Connecting to Plex server...",
                progress=0.3,
                status="working"
            )
            await interaction.edit_original_response(embed=progress_embed)
            
            if query:
                results = plex.search_movies(query)
                if not results:
                    error_embed = MovieBotEmbeds.create_error_embed(
                        "No Results Found",
                        f"No results found for '{query}' in your Plex library"
                    )
                    await interaction.edit_original_response(embed=error_embed)
                    return
                
                # Update progress
                progress_embed = MovieBotEmbeds.create_progress_embed(
                    "Searching Plex Library",
                    "Formatting search results...",
                    progress=0.7,
                    status="working"
                )
                await interaction.edit_original_response(embed=progress_embed)
                
                # Create embeds for results
                embeds = []
                for media in results[:5]:  # Limit to 5 for embed limits
                    embed = MovieBotEmbeds.create_plex_media_embed(media, "movie")
                    embeds.append(embed)
                
                # Send success status
                success_embed = MovieBotEmbeds.create_progress_embed(
                    "Search Complete",
                    f"Found {len(results)} results for '{query}'",
                    progress=1.0,
                    status="success"
                )
                await interaction.edit_original_response(embed=success_embed)
                
                # Send individual result embeds
                for embed in embeds:
                    await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                # Show recent additions
                results = plex.get_recently_added()
                
                # Update progress
                progress_embed = MovieBotEmbeds.create_progress_embed(
                    "Searching Plex Library",
                    "Formatting recent additions...",
                    progress=0.7,
                    status="working"
                )
                await interaction.edit_original_response(embed=progress_embed)
                
                # Create embeds for recent additions
                embeds = []
                for media in results[:5]:  # Limit to 5 for embed limits
                    embed = MovieBotEmbeds.create_plex_media_embed(media, "movie")
                    embed.title = f"🆕 {embed.title}"  # Add new indicator
                    embeds.append(embed)
                
                # Send success status
                success_embed = MovieBotEmbeds.create_progress_embed(
                    "Recent Additions Ready",
                    f"Found {len(results)} recently added items",
                    progress=1.0,
                    status="success"
                )
                await interaction.edit_original_response(embed=success_embed)
                
                # Send individual result embeds
                for embed in embeds:
                    await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            error_embed = MovieBotEmbeds.create_error_embed(
                "Search Failed",
                f"An error occurred while searching Plex: {str(e)}"
            )
            await interaction.edit_original_response(embed=error_embed)

    @media_group.command(name="rate", description="Rate a movie or show (1-10)")
    @app_commands.describe(
        rating_key="Plex rating key (from search results)",
        rating="Your rating from 1-10"
    )
    async def rate_media(interaction: discord.Interaction, rating_key: int, rating: int):
        await interaction.response.defer(ephemeral=True)
        
        if rating < 1 or rating > 10:
            error_embed = MovieBotEmbeds.create_error_embed(
                "Invalid Rating",
                "Rating must be between 1 and 10"
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)
            return
        
        # Create progress indicator
        progress_embed = MovieBotEmbeds.create_progress_embed(
            "Rating Media",
            f"Setting rating to {rating}/10...",
            progress=0.1,
            status="working"
        )
        await interaction.followup.send(embed=progress_embed, ephemeral=True)
        
        try:
            settings = load_settings(client.project_root)
            plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
            
            # Update progress
            progress_embed = MovieBotEmbeds.create_progress_embed(
                "Rating Media",
                "Connecting to Plex server...",
                progress=0.3,
                status="working"
            )
            await interaction.edit_original_response(embed=progress_embed)
            
            plex.set_rating(rating_key, rating)
            
            # Update progress
            progress_embed = MovieBotEmbeds.create_progress_embed(
                "Rating Media",
                "Rating saved successfully!",
                progress=1.0,
                status="success"
            )
            await interaction.edit_original_response(embed=progress_embed)
            
            # Send success message
            success_embed = MovieBotEmbeds.create_success_embed(
                "Rating Saved",
                f"Successfully rated item {rating_key} with {rating}/10 ⭐"
            )
            await interaction.followup.send(embed=success_embed, ephemeral=True)
            
        except Exception as e:
            error_embed = MovieBotEmbeds.create_error_embed(
                "Rating Failed",
                f"Failed to set rating: {str(e)}"
            )
            await interaction.edit_original_response(embed=error_embed)

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
