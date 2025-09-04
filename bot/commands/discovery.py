from __future__ import annotations

import discord
from discord import app_commands
from typing import Optional, List, Dict, Any

from config.loader import load_settings
from integrations.tmdb_client import TMDbClient
from ..discord_embeds import MovieBotEmbeds, ProgressIndicator


def register(client: discord.Client) -> None:
    tree = client.tree
    
    # Discovery group for finding new content
    discovery_group = app_commands.Group(name="discover", description="Discover new movies and TV shows")

    @discovery_group.command(name="search", description="Search TMDb for movies and shows")
    @app_commands.describe(
        query="What to search for",
        year="Filter by year (optional)",
        limit="Maximum results to show (default: 10)"
    )
    async def search_tmdb(
        interaction: discord.Interaction, 
        query: str, 
        year: Optional[int] = None,
        limit: Optional[int] = 10
    ):
        await interaction.response.defer(ephemeral=True)
        
        # Create progress indicator
        progress_embed = MovieBotEmbeds.create_progress_embed(
            "Searching TMDb",
            f"Looking for '{query}'...",
            progress=0.1,
            status="working"
        )
        progress_view = ProgressIndicator.create_progress_view(interaction)
        await interaction.followup.send(embed=progress_embed, view=progress_view, ephemeral=True)
        
        try:
            settings = load_settings(client.project_root)
            if not settings.tmdb_api_key:
                error_embed = MovieBotEmbeds.create_error_embed(
                    "Configuration Error",
                    "TMDb API key not configured"
                )
                await interaction.edit_original_response(embed=error_embed, view=None)
                return
            
            tmdb = TMDbClient(settings.tmdb_api_key)
            
            # Update progress
            progress_embed = MovieBotEmbeds.create_progress_embed(
                "Searching TMDb",
                "Searching for movies...",
                progress=0.3,
                status="working"
            )
            await interaction.edit_original_response(embed=progress_embed)
            
            # Search for movies
            movie_data = await tmdb.search_movie(query, year=year)
            movie_results = movie_data.get("results", [])[:limit//2]
            
            # Update progress
            progress_embed = MovieBotEmbeds.create_progress_embed(
                "Searching TMDb",
                "Searching for TV shows...",
                progress=0.6,
                status="working"
            )
            await interaction.edit_original_response(embed=progress_embed)
            
            # Search for TV shows
            tv_data = await tmdb.search_tv(query, first_air_date_year=year)
            tv_results = tv_data.get("results", [])[:limit//2]
            
            # Update progress
            progress_embed = MovieBotEmbeds.create_progress_embed(
                "Searching TMDb",
                "Formatting results...",
                progress=0.9,
                status="working"
            )
            await interaction.edit_original_response(embed=progress_embed)
            
            # Create results embeds
            embeds = []
            
            if movie_results:
                for movie in movie_results[:5]:  # Limit to 5 movies for embed limits
                    embed = MovieBotEmbeds.create_movie_embed(movie)
                    embeds.append(embed)
            
            if tv_results:
                for show in tv_results[:5]:  # Limit to 5 shows for embed limits
                    embed = MovieBotEmbeds.create_tv_embed(show)
                    embeds.append(embed)
            
            if not embeds:
                error_embed = MovieBotEmbeds.create_error_embed(
                    "No Results Found",
                    f"No movies or shows found for '{query}'"
                )
                await interaction.edit_original_response(embed=error_embed, view=None)
            else:
                # Send first embed with success status
                success_embed = MovieBotEmbeds.create_progress_embed(
                    "Search Complete",
                    f"Found {len(movie_results)} movies and {len(tv_results)} TV shows",
                    progress=1.0,
                    status="success"
                )
                await interaction.edit_original_response(embed=success_embed, view=None)
                
                # Send individual result embeds
                for embed in embeds:
                    await interaction.followup.send(embed=embed, ephemeral=True)
            
            await tmdb.close()
            
        except Exception as e:
            error_embed = MovieBotEmbeds.create_error_embed(
                "Search Failed",
                f"An error occurred while searching: {str(e)}"
            )
            await interaction.edit_original_response(embed=error_embed, view=None)

    @discovery_group.command(name="trending", description="Show trending content")
    @app_commands.describe(
        media_type="Type of content (all, movie, tv, person)",
        time_window="Time period (day, week)",
        limit="Maximum results to show (default: 10)"
    )
    async def trending_content(
        interaction: discord.Interaction,
        media_type: Optional[str] = "all",
        time_window: Optional[str] = "week",
        limit: Optional[int] = 10
    ):
        await interaction.response.defer(ephemeral=True)
        
        if media_type not in ["all", "movie", "tv", "person"]:
            media_type = "all"
        if time_window not in ["day", "week"]:
            time_window = "week"
        
        # Create progress indicator
        progress_embed = MovieBotEmbeds.create_progress_embed(
            "Fetching Trending Content",
            f"Getting {media_type} trending for {time_window}...",
            progress=0.1,
            status="working"
        )
        await interaction.followup.send(embed=progress_embed, ephemeral=True)
        
        try:
            settings = load_settings(client.project_root)
            if not settings.tmdb_api_key:
                error_embed = MovieBotEmbeds.create_error_embed(
                    "Configuration Error",
                    "TMDb API key not configured"
                )
                await interaction.edit_original_response(embed=error_embed)
                return
            
            tmdb = TMDbClient(settings.tmdb_api_key)
            embeds = []
            
            # For now, we'll focus on movies and TV since person search isn't implemented
            if media_type in ["all", "movie"]:
                # Update progress
                progress_embed = MovieBotEmbeds.create_progress_embed(
                    "Fetching Trending Content",
                    "Getting trending movies...",
                    progress=0.3,
                    status="working"
                )
                await interaction.edit_original_response(embed=progress_embed)
                
                movie_data = await tmdb.trending("movie", time_window)
                movie_results = movie_data.get("results", [])[:limit//2]
                
                for movie in movie_results[:3]:  # Limit to 3 for embed limits
                    embed = MovieBotEmbeds.create_movie_embed(movie)
                    embed.title = f"🔥 {embed.title}"  # Add trending indicator
                    embeds.append(embed)
            
            if media_type in ["all", "tv"]:
                # Update progress
                progress_embed = MovieBotEmbeds.create_progress_embed(
                    "Fetching Trending Content",
                    "Getting trending TV shows...",
                    progress=0.6,
                    status="working"
                )
                await interaction.edit_original_response(embed=progress_embed)
                
                tv_data = await tmdb.trending("tv", time_window)
                tv_results = tv_data.get("results", [])[:limit//2]
                
                for show in tv_results[:3]:  # Limit to 3 for embed limits
                    embed = MovieBotEmbeds.create_tv_embed(show)
                    embed.title = f"🔥 {embed.title}"  # Add trending indicator
                    embeds.append(embed)
            
            # Update progress
            progress_embed = MovieBotEmbeds.create_progress_embed(
                "Fetching Trending Content",
                "Formatting results...",
                progress=0.9,
                status="working"
            )
            await interaction.edit_original_response(embed=progress_embed)
            
            if not embeds:
                error_embed = MovieBotEmbeds.create_error_embed(
                    "No Trending Content",
                    f"No trending {media_type} found for {time_window}"
                )
                await interaction.edit_original_response(embed=error_embed)
            else:
                # Send success status
                success_embed = MovieBotEmbeds.create_progress_embed(
                    "Trending Content Ready",
                    f"Found {len(embeds)} trending items",
                    progress=1.0,
                    status="success"
                )
                await interaction.edit_original_response(embed=success_embed)
                
                # Send individual result embeds
                for embed in embeds:
                    await interaction.followup.send(embed=embed, ephemeral=True)
            
            await tmdb.close()
            
        except Exception as e:
            error_embed = MovieBotEmbeds.create_error_embed(
                "Failed to Get Trending Content",
                f"An error occurred: {str(e)}"
            )
            await interaction.edit_original_response(embed=error_embed)

    @discovery_group.command(name="popular", description="Show popular content")
    @app_commands.describe(
        media_type="Type of content (movie, tv)",
        limit="Maximum results to show (default: 10)"
    )
    async def popular_content(
        interaction: discord.Interaction,
        media_type: str = "movie",
        limit: Optional[int] = 10
    ):
        await interaction.response.defer(ephemeral=True)
        
        if media_type not in ["movie", "tv"]:
            media_type = "movie"
        
        try:
            settings = load_settings(client.project_root)
            if not settings.tmdb_api_key:
                await interaction.followup.send("TMDb API key not configured", ephemeral=True)
                return
            
            tmdb = TMDbClient(settings.tmdb_api_key)
            
            if media_type == "movie":
                data = await tmdb.popular_movies()
                results = data.get("results", [])[:limit]
                lines = ["**Popular Movies:**"]
                for movie in results:
                    title = movie.get('title', 'Unknown')
                    year = (movie.get('release_date') or '????')[:4]
                    rating = movie.get('vote_average', 'N/A')
                    lines.append(f"• {title} ({year}) — Rating: {rating}/10")
            else:
                data = await tmdb.popular_tv()
                results = data.get("results", [])[:limit]
                lines = ["**Popular TV Shows:**"]
                for show in results:
                    title = show.get('name', 'Unknown')
                    year = (show.get('first_air_date') or '????')[:4]
                    rating = show.get('vote_average', 'N/A')
                    lines.append(f"• {title} ({year}) — Rating: {rating}/10")
            
            text = "\n".join(lines)
            await interaction.followup.send(text[:1900], ephemeral=True)
            await tmdb.close()
            
        except Exception as e:
            await interaction.followup.send(f"Failed to get popular content: {str(e)}", ephemeral=True)

    @discovery_group.command(name="upcoming", description="Show upcoming movie releases")
    @app_commands.describe(limit="Maximum results to show (default: 10)")
    async def upcoming_movies(interaction: discord.Interaction, limit: Optional[int] = 10):
        await interaction.response.defer(ephemeral=True)
        
        try:
            settings = load_settings(client.project_root)
            if not settings.tmdb_api_key:
                await interaction.followup.send("TMDb API key not configured", ephemeral=True)
                return
            
            tmdb = TMDbClient(settings.tmdb_api_key)
            data = await tmdb.upcoming_movies()
            results = data.get("results", [])[:limit]
            
            lines = ["**Upcoming Movies:**"]
            for movie in results:
                title = movie.get('title', 'Unknown')
                release_date = movie.get('release_date', 'Unknown')
                rating = movie.get('vote_average', 'N/A')
                lines.append(f"• {title} — Releases: {release_date}, Rating: {rating}/10")
            
            text = "\n".join(lines)
            await interaction.followup.send(text[:1900], ephemeral=True)
            await tmdb.close()
            
        except Exception as e:
            await interaction.followup.send(f"Failed to get upcoming movies: {str(e)}", ephemeral=True)

    @discovery_group.command(name="nowplaying", description="Show movies currently in theaters")
    @app_commands.describe(limit="Maximum results to show (default: 10)")
    async def now_playing_movies(interaction: discord.Interaction, limit: Optional[int] = 10):
        await interaction.response.defer(ephemeral=True)
        
        try:
            settings = load_settings(client.project_root)
            if not settings.tmdb_api_key:
                await interaction.followup.send("TMDb API key not configured", ephemeral=True)
                return
            
            tmdb = TMDbClient(settings.tmdb_api_key)
            data = await tmdb.now_playing_movies()
            results = data.get("results", [])[:limit]
            
            lines = ["**Now Playing in Theaters:**"]
            for movie in results:
                title = movie.get('title', 'Unknown')
                year = (movie.get('release_date') or '????')[:4]
                rating = movie.get('vote_average', 'N/A')
                lines.append(f"• {title} ({year}) — Rating: {rating}/10")
            
            text = "\n".join(lines)
            await interaction.followup.send(text[:1900], ephemeral=True)
            await tmdb.close()
            
        except Exception as e:
            await interaction.followup.send(f"Failed to get now playing movies: {str(e)}", ephemeral=True)

    tree.add_command(discovery_group)
