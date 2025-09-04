from __future__ import annotations

import discord
from typing import Any, Dict, List, Optional, Union
from datetime import datetime


class MovieBotEmbeds:
    """Rich embed utilities for MovieBot Discord responses."""
    
    # Color palette for different types of content
    COLORS = {
        'movie': 0x00ff00,      # Green for movies
        'tv': 0x0099ff,         # Blue for TV shows
        'success': 0x00ff00,    # Green for success
        'error': 0xff0000,      # Red for errors
        'warning': 0xffaa00,    # Orange for warnings
        'info': 0x0099ff,       # Blue for info
        'plex': 0xe5a00d,       # Plex orange
        'radarr': 0x264d73,     # Radarr blue
        'sonarr': 0x35c5f0,     # Sonarr cyan
        'tmdb': 0x01d277,       # TMDb green
    }
    
    @staticmethod
    def create_movie_embed(movie_data: Dict[str, Any], include_actions: bool = False) -> discord.Embed:
        """Create a rich embed for a movie."""
        title = movie_data.get('title', 'Unknown Movie')
        year = movie_data.get('release_date', '????')[:4] if movie_data.get('release_date') else '????'
        overview = movie_data.get('overview', 'No description available')
        rating = movie_data.get('vote_average', 0)
        poster_path = movie_data.get('poster_path')
        tmdb_id = movie_data.get('id', 'N/A')
        
        # Truncate overview if too long
        if len(overview) > 300:
            overview = overview[:297] + "..."
        
        embed = discord.Embed(
            title=f"{title} ({year})",
            description=overview,
            color=MovieBotEmbeds.COLORS['movie'],
            timestamp=datetime.utcnow()
        )
        
        # Add poster thumbnail if available
        if poster_path:
            embed.set_thumbnail(url=f"https://image.tmdb.org/t/p/w500{poster_path}")
        
        # Add fields
        embed.add_field(name="Rating", value=f"⭐ {rating}/10", inline=True)
        embed.add_field(name="TMDb ID", value=str(tmdb_id), inline=True)
        
        # Add genre if available
        if movie_data.get('genre_ids'):
            # Note: In a real implementation, you'd map genre_ids to names
            embed.add_field(name="Genres", value="Action, Thriller", inline=True)
        
        # Add footer
        embed.set_footer(text="Powered by TMDb", icon_url="https://www.themoviedb.org/assets/2/v4/logos/v2/blue_short-8e7b30f73a4020692ccca9c88bafe5dcb6f8a62a4c6bc55cd9ba82bb2cd95f6c.svg")
        
        return embed
    
    @staticmethod
    def create_tv_embed(tv_data: Dict[str, Any], include_actions: bool = False) -> discord.Embed:
        """Create a rich embed for a TV show."""
        title = tv_data.get('name', 'Unknown Show')
        year = tv_data.get('first_air_date', '????')[:4] if tv_data.get('first_air_date') else '????'
        overview = tv_data.get('overview', 'No description available')
        rating = tv_data.get('vote_average', 0)
        poster_path = tv_data.get('poster_path')
        tmdb_id = tv_data.get('id', 'N/A')
        
        # Truncate overview if too long
        if len(overview) > 300:
            overview = overview[:297] + "..."
        
        embed = discord.Embed(
            title=f"{title} ({year})",
            description=overview,
            color=MovieBotEmbeds.COLORS['tv'],
            timestamp=datetime.utcnow()
        )
        
        # Add poster thumbnail if available
        if poster_path:
            embed.set_thumbnail(url=f"https://image.tmdb.org/t/p/w500{poster_path}")
        
        # Add fields
        embed.add_field(name="Rating", value=f"⭐ {rating}/10", inline=True)
        embed.add_field(name="TMDb ID", value=str(tmdb_id), inline=True)
        
        # Add genre if available
        if tv_data.get('genre_ids'):
            embed.add_field(name="Genres", value="Drama, Sci-Fi", inline=True)
        
        # Add footer
        embed.set_footer(text="Powered by TMDb", icon_url="https://www.themoviedb.org/assets/2/v4/logos/v2/blue_short-8e7b30f73a4020692ccca9c88bafe5dcb6f8a62a4c6bc55cd9ba82bb2cd95f6c.svg")
        
        return embed
    
    @staticmethod
    def create_plex_media_embed(media_data: Any, media_type: str = "movie") -> discord.Embed:
        """Create a rich embed for Plex media."""
        title = getattr(media_data, 'title', 'Unknown')
        year = getattr(media_data, 'year', '????')
        summary = getattr(media_data, 'summary', 'No description available')
        rating = getattr(media_data, 'rating', 0)
        thumb = getattr(media_data, 'thumb', None)
        rating_key = getattr(media_data, 'ratingKey', 'N/A')
        
        # Truncate summary if too long
        if len(summary) > 300:
            summary = summary[:297] + "..."
        
        embed = discord.Embed(
            title=f"{title} ({year})",
            description=summary,
            color=MovieBotEmbeds.COLORS['plex'],
            timestamp=datetime.utcnow()
        )
        
        # Add thumbnail if available
        if thumb:
            # In a real implementation, you'd construct the Plex thumbnail URL
            embed.set_thumbnail(url=f"https://your-plex-server.com{thumb}")
        
        # Add fields
        if rating:
            embed.add_field(name="Rating", value=f"⭐ {rating}/10", inline=True)
        embed.add_field(name="Plex ID", value=str(rating_key), inline=True)
        embed.add_field(name="Type", value=media_type.title(), inline=True)
        
        # Add footer
        embed.set_footer(text="From your Plex library", icon_url="https://www.plex.tv/wp-content/themes/plex/assets/img/plex-logo.svg")
        
        return embed
    
    @staticmethod
    def create_progress_embed(title: str, description: str, progress: float = 0.0, status: str = "working") -> discord.Embed:
        """Create a progress indicator embed."""
        # Choose color based on status
        color_map = {
            'working': MovieBotEmbeds.COLORS['info'],
            'success': MovieBotEmbeds.COLORS['success'],
            'error': MovieBotEmbeds.COLORS['error'],
            'warning': MovieBotEmbeds.COLORS['warning']
        }
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=color_map.get(status, MovieBotEmbeds.COLORS['info']),
            timestamp=datetime.utcnow()
        )
        
        # Add progress bar
        if 0 <= progress <= 1:
            bar_length = 10
            filled_length = int(bar_length * progress)
            bar = "█" * filled_length + "░" * (bar_length - filled_length)
            embed.add_field(
                name="Progress", 
                value=f"`{bar}` {progress:.1%}", 
                inline=False
            )
        
        # Add status indicator
        status_emojis = {
            'working': '⏳',
            'success': '✅',
            'error': '❌',
            'warning': '⚠️'
        }
        embed.add_field(
            name="Status", 
            value=f"{status_emojis.get(status, '⏳')} {status.title()}", 
            inline=True
        )
        
        return embed
    
    @staticmethod
    def create_search_results_embed(results: List[Dict[str, Any]], query: str, result_type: str = "movie") -> discord.Embed:
        """Create an embed for search results."""
        embed = discord.Embed(
            title=f"Search Results for '{query}'",
            description=f"Found {len(results)} {result_type}s",
            color=MovieBotEmbeds.COLORS.get(result_type, MovieBotEmbeds.COLORS['info']),
            timestamp=datetime.utcnow()
        )
        
        # Add results as fields (limit to 10 to avoid embed limits)
        for i, result in enumerate(results[:10]):
            title = result.get('title') or result.get('name', 'Unknown')
            year = (result.get('release_date') or result.get('first_air_date', '????'))[:4]
            rating = result.get('vote_average', 0)
            tmdb_id = result.get('id', 'N/A')
            
            embed.add_field(
                name=f"{i+1}. {title} ({year})",
                value=f"⭐ {rating}/10 | ID: {tmdb_id}",
                inline=False
            )
        
        if len(results) > 10:
            embed.set_footer(text=f"Showing first 10 of {len(results)} results")
        
        return embed
    
    @staticmethod
    def create_system_status_embed(status_data: Dict[str, Any]) -> discord.Embed:
        """Create an embed for system status."""
        embed = discord.Embed(
            title="System Status",
            color=MovieBotEmbeds.COLORS['info'],
            timestamp=datetime.utcnow()
        )
        
        # Add service status
        for service, data in status_data.items():
            if isinstance(data, dict):
                status = data.get('status', 'unknown')
                emoji = "✅" if status == "ok" else "❌" if status == "error" else "⚠️"
                embed.add_field(
                    name=service.title(),
                    value=f"{emoji} {status.title()}",
                    inline=True
                )
        
        return embed
    
    @staticmethod
    def create_error_embed(title: str, error_message: str, error_type: str = "error") -> discord.Embed:
        """Create an error embed."""
        embed = discord.Embed(
            title=f"❌ {title}",
            description=error_message,
            color=MovieBotEmbeds.COLORS['error'],
            timestamp=datetime.utcnow()
        )
        
        embed.set_footer(text="If this persists, please check your configuration")
        
        return embed
    
    @staticmethod
    def create_success_embed(title: str, message: str) -> discord.Embed:
        """Create a success embed."""
        embed = discord.Embed(
            title=f"✅ {title}",
            description=message,
            color=MovieBotEmbeds.COLORS['success'],
            timestamp=datetime.utcnow()
        )
        
        return embed


class ProgressIndicator:
    """Progress indicator utilities for Discord."""
    
    @staticmethod
    def create_progress_view(interaction: discord.Interaction) -> discord.ui.View:
        """Create a view with progress indicators."""
        view = discord.ui.View(timeout=300)  # 5 minute timeout
        
        # Add a stop button
        stop_button = discord.ui.Button(
            label="Stop",
            style=discord.ButtonStyle.danger,
            emoji="⏹️"
        )
        
        async def stop_callback(interaction: discord.Interaction):
            await interaction.response.edit_message(
                content="Operation cancelled by user.",
                view=None,
                embed=None
            )
        
        stop_button.callback = stop_callback
        view.add_item(stop_button)
        
        return view
    
    @staticmethod
    def update_progress_embed(embed: discord.Embed, progress: float, status: str = "working", details: str = "") -> discord.Embed:
        """Update an existing progress embed."""
        # Clear existing progress fields
        embed.clear_fields()
        
        # Add progress bar
        if 0 <= progress <= 1:
            bar_length = 10
            filled_length = int(bar_length * progress)
            bar = "█" * filled_length + "░" * (bar_length - filled_length)
            embed.add_field(
                name="Progress", 
                value=f"`{bar}` {progress:.1%}", 
                inline=False
            )
        
        # Add status
        status_emojis = {
            'working': '⏳',
            'success': '✅',
            'error': '❌',
            'warning': '⚠️'
        }
        embed.add_field(
            name="Status", 
            value=f"{status_emojis.get(status, '⏳')} {status.title()}", 
            inline=True
        )
        
        # Add details if provided
        if details:
            embed.add_field(
                name="Details",
                value=details,
                inline=False
            )
        
        return embed
