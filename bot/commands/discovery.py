from __future__ import annotations

import discord
from discord import app_commands
from typing import Optional

from config.loader import load_settings
from integrations.tmdb_client import TMDbClient


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
        
        try:
            settings = load_settings(client.project_root)
            if not settings.tmdb_api_key:
                await interaction.followup.send("TMDb API key not configured", ephemeral=True)
                return
            
            tmdb = TMDbClient(settings.tmdb_api_key)
            
            # Search for movies
            movie_data = await tmdb.search_movie(query, year=year)
            movie_results = movie_data.get("results", [])[:limit//2]
            
            # Search for TV shows
            tv_data = await tmdb.search_tv(query, first_air_date_year=year)
            tv_results = tv_data.get("results", [])[:limit//2]
            
            lines = []
            if movie_results:
                lines.append("**Movies:**")
                for movie in movie_results:
                    title = movie.get('title', 'Unknown')
                    year = (movie.get('release_date') or '????')[:4]
                    tmdb_id = movie.get('id', 'N/A')
                    lines.append(f"• {title} ({year}) — TMDb ID: {tmdb_id}")
            
            if tv_results:
                if lines:
                    lines.append("")
                lines.append("**TV Shows:**")
                for show in tv_results:
                    title = show.get('name', 'Unknown')
                    year = (show.get('first_air_date') or '????')[:4]
                    tmdb_id = show.get('id', 'N/A')
                    lines.append(f"• {title} ({year}) — TMDb ID: {tmdb_id}")
            
            if not lines:
                lines.append(f"No results found for '{query}'")
            
            text = "\n".join(lines)
            await interaction.followup.send(text[:1900], ephemeral=True)
            await tmdb.close()
            
        except Exception as e:
            await interaction.followup.send(f"Search failed: {str(e)}", ephemeral=True)

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
        
        try:
            settings = load_settings(client.project_root)
            if not settings.tmdb_api_key:
                await interaction.followup.send("TMDb API key not configured", ephemeral=True)
                return
            
            tmdb = TMDbClient(settings.tmdb_api_key)
            
            # For now, we'll focus on movies and TV since person search isn't implemented
            if media_type in ["all", "movie"]:
                movie_data = await tmdb.trending("movie", time_window)
                movie_results = movie_data.get("results", [])[:limit//2]
                
                lines = ["**Trending Movies:**"]
                for movie in movie_results:
                    title = movie.get('title', 'Unknown')
                    year = (movie.get('release_date') or '????')[:4]
                    rating = movie.get('vote_average', 'N/A')
                    lines.append(f"• {title} ({year}) — Rating: {rating}/10")
            
            if media_type in ["all", "tv"]:
                tv_data = await tmdb.trending("tv", time_window)
                tv_results = tv_data.get("results", [])[:limit//2]
                
                if media_type == "all":
                    lines.append("")
                lines.append("**Trending TV Shows:**")
                for show in tv_results:
                    title = show.get('name', 'Unknown')
                    year = (show.get('first_air_date') or '????')[:4]
                    rating = show.get('vote_average', 'N/A')
                    lines.append(f"• {title} ({year}) — Rating: {rating}/10")
            
            text = "\n".join(lines)
            await interaction.followup.send(text[:1900], ephemeral=True)
            await tmdb.close()
            
        except Exception as e:
            await interaction.followup.send(f"Failed to get trending content: {str(e)}", ephemeral=True)

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
