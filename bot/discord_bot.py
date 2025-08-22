from __future__ import annotations

import asyncio
import os
from typing import Optional
from pathlib import Path
import re
import logging
import random

import discord
from discord import app_commands

from config.loader import load_settings, load_runtime_config
from .commands.search import register as register_search
from .commands.watchlist import register as register_watchlist
from .commands.ratings import register as register_ratings
from .commands.prefs import register as register_prefs
from .conversation import CONVERSATIONS
from .agent import Agent


def ephemeral_embed(title: str, description: str) -> discord.Embed:
    embed = discord.Embed(title=title, description=description)
    return embed


def _get_clever_progress_message(iteration: int, tool_name: str = None, progress_type: str = None) -> str:
    """Generate clever, opaque progress messages that hint at what's happening."""
    messages = [
        "Working on it — checking services…",
        "Still working — consulting the digital oracle…",
        "Processing… like a librarian on caffeine…",
        "Analyzing… because details matter…",
        "Thinking… but not too hard…",
        "Computing… one bit at a time…",
        "Processing… patience is a virtue…",
        "Working… like a well-oiled machine…",
        "Analyzing… because magic takes time…",
        "Processing… gathering digital wisdom…",
        "Thinking… but not overthinking…",
        "Computing… because algorithms are patient…",
        "Working… like a digital detective…",
        "Processing… one request at a time…",
        "Analyzing… because quality takes time…",
        "Working… like a film critic with a deadline…",
        "Processing… because good taste can't be rushed…",
        "Thinking… like a movie buff in a library…",
        "Computing… one frame at a time…",
        "Analyzing… because every detail tells a story…",
        "Working… like a director in the editing room…",
        "Processing… because perfection takes time…",
        "Thinking… like a screenwriter with writer's block…",
        "Computing… because algorithms have feelings too…",
        "Analyzing… like a film student studying classics…",
        "Working… because the show must go on…",
        "Processing… like a popcorn machine warming up…",
        "Thinking… because good recommendations are worth waiting for…",
        "Computing… like a film projector loading reels…",
        "Analyzing… because every movie has its moment…",
        "Working… like a film archivist organizing classics…",
        "Processing… because quality entertainment takes effort…",
    ]
    
    # Tool-specific hints for more intelligent progress
    if tool_name:
        tool_hints = {
            "tmdb": "consulting the movie database…",
            "plex": "checking your personal library…",
            "radarr": "scanning the movie collection…",
            "sonarr": "browsing the TV series…",
            "preferences": "checking your taste profile…",
            "search": "searching through the archives…",
            "recommendations": "finding the perfect match…",
            "discover": "uncovering hidden gems…",
            "trending": "checking what's hot right now…",
            "popular": "seeing what everyone's watching…",
            "similar": "finding lookalikes…",
            "details": "gathering the fine print…",
            "collections": "browsing curated sets…",
            "playlists": "checking your custom lists…",
            "history": "reviewing your journey…",
            "status": "checking current state…",
            "health": "running diagnostics…",
            "queue": "checking the waiting list…",
            "wanted": "scanning wishlists…",
            "calendar": "checking the schedule…",
            "blacklist": "filtering out the bad stuff…",
            "indexers": "consulting search engines…",
            "download": "checking transfer status…",
            "system": "running system checks…",
            "disk": "checking storage space…",
            "quality": "verifying quality settings…",
            "folders": "scanning directories…",
            "episodes": "browsing episode lists…",
            "seasons": "checking season info…",
            "series": "analyzing show details…",
            "monitor": "setting up alerts…",
            "missing": "finding what's not there…",
            "cutoff": "checking quality thresholds…",
            "extras": "looking for bonus content…",
            "playback": "checking what's playing…",
            "file": "examining file details…",
            "fallback": "finding alternatives…",
            # More specific and clever tool hints
            "tmdb_search": "searching the movie database like a film detective…",
            "tmdb_recommendations": "asking the algorithm for its best picks…",
            "tmdb_discover": "unearthing cinematic treasures…",
            "tmdb_trending": "checking what's making waves in Hollywood…",
            "tmdb_popular": "seeing what the masses are watching…",
            "tmdb_top_rated": "consulting the critics' choice…",
            "tmdb_upcoming": "peeking into the future of cinema…",
            "tmdb_now_playing": "checking what's currently in theaters…",
            "tmdb_on_the_air": "seeing what's currently on TV…",
            "tmdb_airing_today": "checking today's TV lineup…",
            "tmdb_movie_details": "reading the fine print on that film…",
            "tmdb_tv_details": "getting the scoop on that show…",
            "tmdb_similar": "finding cinematic soulmates…",
            "tmdb_genres": "browsing by category…",
            "tmdb_collection": "checking out the franchise…",
            "tmdb_watch_providers": "finding where you can watch it…",
            "plex_search": "searching your personal movie vault…",
            "plex_library": "browsing your collection…",
            "plex_recently_added": "checking what's new in your library…",
            "plex_on_deck": "seeing what's next in your queue…",
            "plex_continue_watching": "finding where you left off…",
            "plex_unwatched": "discovering unwatched gems…",
            "plex_collections": "browsing your curated sets…",
            "plex_playlists": "checking your custom lists…",
            "plex_rating": "updating your personal rating…",
            "plex_playback": "checking what's currently playing…",
            "plex_history": "reviewing your viewing journey…",
            "radarr_lookup": "looking up movie information…",
            "radarr_add": "adding to your movie collection…",
            "radarr_search": "searching for movie files…",
            "radarr_queue": "checking your download queue…",
            "radarr_wanted": "scanning your wishlist…",
            "radarr_calendar": "checking your movie schedule…",
            "sonarr_lookup": "looking up TV show information…",
            "sonarr_add": "adding to your TV collection…",
            "sonarr_search": "searching for TV episodes…",
            "sonarr_queue": "checking your download queue…",
            "sonarr_wanted": "scanning your TV wishlist…",
            "sonarr_calendar": "checking your TV schedule…",
            "sonarr_monitor": "setting up episode monitoring…",
            "sonarr_episodes": "browsing episode lists…",
            "sonarr_seasons": "checking season information…",
            "household_preferences": "checking your family's taste profile…",
            "household_search": "searching through your preferences…",
            "household_update": "updating your taste settings…",
            "household_query": "consulting your preference database…",
        }
        
        for tool_key, hint in tool_hints.items():
            if tool_key in tool_name.lower():
                return f"Still working — {hint}"
    
    # Progress type-specific messages
    if progress_type == "thinking":
        thinking_messages = [
            "Thinking… processing your request…",
            "Analyzing… considering the options…",
            "Computing… working through the logic…",
            "Processing… connecting the dots…",
            "Thinking… because good answers take time…",
            "Thinking… like a film critic analyzing a plot…",
            "Analyzing… because every request is unique…",
            "Computing… like a movie algorithm with taste…",
            "Processing… because good recommendations need thought…",
            "Thinking… because your entertainment matters…",
        ]
        return random.choice(thinking_messages)
    
    # Iteration-specific messages for better progress tracking
    if iteration > 1:
        iteration_messages = [
            f"Still working — step {iteration} of the process…",
            f"Processing… iteration {iteration} and counting…",
            f"Working through it — step {iteration}…",
            f"Analyzing… this is step {iteration}…",
            f"Computing… iteration {iteration} in progress…",
            f"Processing… step {iteration} of the journey…",
            f"Thinking… iteration {iteration} and still going…",
            f"Working… step {iteration} and not giving up…",
            f"Analyzing… iteration {iteration} and counting…",
            f"Processing… step {iteration} of the adventure…",
        ]
        return random.choice(iteration_messages)
    
    # Return a random message for variety
    return random.choice(messages)


class MovieBotClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        # During development, sync commands to a single guild if provided
        settings = load_settings(self.project_root)  # type: ignore[attr-defined]
        guild_id = settings.discord_development_guild_id
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            await self.tree.sync(guild)
        else:
            await self.tree.sync()

    async def _reply_llm_message(self, message: discord.Message) -> None:
        log = logging.getLogger("moviebot.bot")
        if not message.content:
            return
        conv_id = message.channel.id
        # Strip bot mention if present
        content = message.content
        if self.user:  # type: ignore[truthy-bool]
            mention_pattern = re.compile(rf"<@!?{self.user.id}>")
            content = mention_pattern.sub("", content).strip()
        if not content:
            return
        
        settings = load_settings(self.project_root)  # type: ignore[attr-defined]
        
        # Choose provider: OpenRouter if available, otherwise OpenAI
        if settings.openai_api_key:
            api_key = settings.openai_api_key
            provider = "openai"
        else:
            api_key = settings.openrouter_api_key or ""
            provider = "openrouter"
        
        progress_message = None
        progress_update_task = None
        current_tool = None
        current_progress_type = None
        
        # Progress callback function for the agent
        def progress_callback(progress_type: str, details: str):
            nonlocal current_tool, current_progress_type
            current_progress_type = progress_type
            if progress_type == "tool":
                current_tool = details
            elif progress_type == "thinking":
                current_progress_type = "thinking"
        
        agent = Agent(api_key=api_key, project_root=self.project_root, provider=provider, progress_callback=progress_callback)  # type: ignore[arg-type]
        
        # Set the LLM client in the conversation store for token counting
        CONVERSATIONS.set_llm_client(agent.llm)
        
        CONVERSATIONS.add_user(conv_id, content)
        log.info("incoming message", extra={
            "channel_id": conv_id,
            "author": str(message.author),
            "content_preview": content[:120],
        })

        # Run blocking LLM call in a thread to avoid blocking the event loop
        loop = asyncio.get_running_loop()
        history = CONVERSATIONS.tail(conv_id)
        
        # Log token count for monitoring
        token_count = CONVERSATIONS.get_token_count(conv_id)
        log.info("conversation token count", extra={
            "channel_id": conv_id,
            "token_count": token_count,
            "message_count": len(history)
        })
        
        try:
            async with message.channel.typing():
                # Show a progress note if it takes too long
                rc = load_runtime_config(self.project_root)  # type: ignore[attr-defined]
                progress_ms = int(rc.get("ux", {}).get("progressThresholdMs", 5000))
                done = asyncio.Event()

                async def progress_updater():
                    """Continuously update the progress message with intelligent updates."""
                    nonlocal progress_message, current_tool, current_progress_type
                    try:
                        await asyncio.wait_for(done.wait(), timeout=progress_ms / 1000)
                    except asyncio.TimeoutError:
                        # Send initial progress message
                        try:
                            progress_message = await message.channel.send(
                                _get_clever_progress_message(0),  # type: ignore[attr-defined]
                                silent=True
                            )
                            
                            # Continue updating the message every few seconds
                            iteration = 1
                            last_tool = None
                            last_progress_type = None
                            
                            # Get update interval from config
                            update_interval = int(rc.get("ux", {}).get("progressUpdateIntervalMs", 2000)) / 1000
                            update_frequency = int(rc.get("ux", {}).get("progressUpdateFrequency", 4))
                            
                            while not done.is_set():
                                try:
                                    await asyncio.sleep(update_interval)
                                    if done.is_set():
                                        break
                                    
                                    # Check if we have new progress information
                                    tool_changed = current_tool != last_tool
                                    progress_type_changed = current_progress_type != last_progress_type
                                    
                                    if tool_changed or progress_type_changed or iteration % update_frequency == 0:  # Update on changes or based on frequency
                                        # Generate new message based on current state
                                        new_message = _get_clever_progress_message(  # type: ignore[attr-defined]
                                            iteration, 
                                            current_tool, 
                                            current_progress_type
                                        )
                                        
                                        # Only edit if the message actually changed
                                        if new_message != progress_message.content:
                                            await progress_message.edit(content=new_message)
                                        
                                        last_tool = current_tool
                                        last_progress_type = current_progress_type
                                    
                                    iteration += 1
                                except Exception as e:
                                    log.warning(f"Failed to update progress message: {e}")
                                    break
                        except Exception as e:
                            log.warning(f"Failed to send progress message: {e}")

                progress_update_task = asyncio.create_task(progress_updater())
                
                try:
                    response = await loop.run_in_executor(None, lambda: agent.converse(history))
                finally:
                    done.set()
                    if progress_update_task:
                        progress_update_task.cancel()
                        
            text = (
                response.choices[0].message.content  # type: ignore[attr-defined]
                if hasattr(response, 'choices') else str(response)
            )
        except Exception as e:  # noqa: BLE001
            text = f"(error talking to model: {e})"
            done.set()
            if progress_update_task:
                progress_update_task.cancel()
        
        # Delete the progress message if it exists
        if progress_message:
            try:
                await progress_message.delete()
            except Exception as e:
                log.warning(f"Failed to delete progress message: {e}")
        
        CONVERSATIONS.add_assistant(conv_id, text)
        log.info("assistant reply", extra={"channel_id": conv_id, "content_preview": text[:120]})
        await message.reply(text[:1900], mention_author=False)

    async def on_message(self, message: discord.Message) -> None:  # type: ignore[override]
        # Ignore bot/self messages
        if message.author.bot:
            return
        is_dm = message.guild is None
        mentioned = False
        if self.user:
            mentioned = self.user in message.mentions  # type: ignore[truthy-bool]
        if not is_dm and not mentioned:
            return
        await self._reply_llm_message(message)


def build_client() -> MovieBotClient:
    intents = discord.Intents.default()
    intents.message_content = True  # required for reading user messages
    client = MovieBotClient(intents=intents)
    client.project_root = Path(__file__).resolve().parents[1]  # type: ignore[attr-defined]

    @client.tree.command(name="ping", description="Health check")
    async def ping(interaction: discord.Interaction) -> None:
        await interaction.response.send_message("Pong!", ephemeral=True)

    # Register command groups
    register_search(client)
    register_watchlist(client)
    register_ratings(client)
    register_prefs(client)

    @client.event
    async def on_ready() -> None:  # type: ignore[override]
        # Show as online with a helpful activity message
        await client.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(type=discord.ActivityType.listening, name="your requests")
        )

    return client


async def run_bot() -> None:
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[1]
    settings = load_settings(project_root)
    if not settings.discord_token:
        raise RuntimeError("DISCORD_TOKEN missing. Run setup wizard or set .env.")

    client = build_client()
    await client.start(settings.discord_token)


if __name__ == "__main__":
    try:
        print("Starting bot...")
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("Bot stopped.")
        pass

