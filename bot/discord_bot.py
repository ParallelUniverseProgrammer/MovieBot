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
from .commands import (
    register_media,
    register_discovery,
    register_management,
    register_preferences,
    register_utilities
)
from .conversation import CONVERSATIONS
from .agent import Agent


def ephemeral_embed(title: str, description: str) -> discord.Embed:
    embed = discord.Embed(title=title, description=description)
    return embed


def _get_clever_progress_message(
    iteration: int, tool_name: str = None, progress_type: str = None
) -> str:
    """Generate clever, opaque progress messages that hint at what's happening.
    Same signature and compatible tool keys. Funnier, sturdier selection logic.
    """
    import random

    def _norm(s):
        return (s or "").strip().lower()

    n_tool = _norm(tool_name)
    n_type = _norm(progress_type)

    # Stable-ish randomness so the same (iteration/tool/type) won't jitter
    seed = 0x9E3779B97F4A7C15
    for ch in f"{iteration}|{n_tool}|{n_type}":
        seed = (seed ^ ord(ch)) * 0x100000001B3 & ((1 << 64) - 1)
    rng = random.Random(seed)

    base_messages = [
        "Calibrating taste sensors… please hold your applause…",
        "Sharpening algorithms with safety scissors…",
        "Letting the cache stretch its legs…",
        "Negotiating with the progress bar union…",
        "Politely asking the servers to be fast for once…",
        "Warming up the recommendation cauldron…",
        "Reading tea leaves, but they’re JSON…",
        "Making shapes in the cloud look like answers…",
        "Teaching the model not to pick the same three blockbusters…",
        "Re-indexing the vibes…",
        "Untangling spaghetti queries…",
        "Buffering wit… and bits…",
    ]

    thinking_messages = [
        "Thinking… assembling a thought that won’t age poorly…",
        "Analyzing… separating signal from blockbuster noise…",
        "Computing… allocating two brain cells and a dream…",
        "Processing… connecting plot threads and data threads…",
        "Thinking… consulting the vibe oracle…",
        "Analyzing… because taste is a dataset and a journey…",
        "Computing… removing duplicates and bad takes…",
        "Processing… one clever synapse at a time…",
        "Thinking… pausing for dramatic effect…",
        "Analyzing… rerouting around clichés…",
    ]

    def _iter_message(i: int) -> str:
        bank = [
            f"Still working — step {i} of ‘soon’…",
            f"Progress update: iteration {i}. Morale: high.",
            f"Grinding politely — pass {i} through the gauntlet…",
            f"Iteration {i}… we chose violence against bugs.",
            f"Step {i}… trimming the hedges, not the corners…",
            f"Iteration {i}… refining, refactoring, rejoicing…",
            f"Step {i}… like a montage, but with APIs…",
            f"Iteration {i}… closer than the last one, promise…",
            f"Pass {i}… inspecting edge cases with a magnifying glass…",
            f"Still working — lap {i} around the data track…",
        ]
        # Nudge tone based on how deep we are
        if i >= 8:
            bank.append(f"Iteration {i}… we’re in too deep to bail now…")
        elif i >= 4:
            bank.append(f"Iteration {i}… mid-flight course correction…")
        else:
            bank.append(f"Step {i}… warming up the clever bit…")
        return rng.choice(bank)

    # Tool-specific hints (keys preserved for compatibility)
    tool_hints = {
        "tmdb": "bribing the movie database with virtual popcorn…",
        "plex": "dusting your Plex shelves like a neat freak…",
        "radarr": "lighting the Radarr signal for fresh cinema…",
        "sonarr": "herding episodes into the right pens…",
        "preferences": "peeking at your taste DNA (no judgment)…",
        "search": "opening a wormhole to find the good stuff…",
        "recommendations": "playing matchmaker between you and a great watch…",
        "discover": "digging for sleeper hits with a tiny shovel…",
        "trending": "checking what the herd is stampeding toward…",
        "popular": "seeing what the algorithm thinks is for ‘everyone’…",
        "similar": "finding cinematic cousins…",
        "details": "reading the small print so you don’t have to…",
        "collections": "arranging franchises alphabetically and spiritually…",
        "playlists": "DJ‑ing your watchlist…",
        "history": "time‑traveling through your viewing past…",
        "status": "taking the system’s pulse…",
        "health": "asking the system to say ‘ahh’…",
        "queue": "peeking at the download conga line…",
        "wanted": "checking the ‘bring me this’ list…",
        "calendar": "syncing with the space‑time continuum…",
        "blacklist": "banishing the unworthy to the shadow realm…",
        "indexers": "whispering sweet nothings to search engines…",
        "download": "watching the progress bar inch heroically…",
        "system": "appeasing the machine spirits…",
        "disk": "measuring free space with a tiny ruler…",
        "quality": "negotiating with the Quality Council…",
        "folders": "spelunking through directories…",
        "episodes": "lining up episodes like very obedient ducks…",
        "seasons": "stacking seasons into tidy arcs…",
        "series": "annotating show lore like a trivia goblin…",
        "monitor": "arming tripwires for new releases…",
        "missing": "playing hide‑and‑seek with files…",
        "cutoff": "checking if the bar is set high enough…",
        "extras": "hunting for bloopers and shiny nuggets…",
        "playback": "making sure the play button actually plays…",
        "file": "sniffing file metadata like a sommelier…",
        "fallback": "crafting Plan B (and C)…",
        "tmdb_search": "interrogating TMDB with leading questions…",
        "tmdb_recommendations": "asking TMDB for vibes, not just stats…",
        "tmdb_discover": "unearthing cinematic treasures…",
        "tmdb_trending": "checking what’s making waves this minute…",
        "tmdb_popular": "seeing what the masses are binging…",
        "tmdb_top_rated": "consulting the critics’ pantheon…",
        "tmdb_upcoming": "peeking at the near future of cinema…",
        "tmdb_now_playing": "checking what’s on the big screens…",
        "tmdb_on_the_air": "seeing what’s currently airing…",
        "tmdb_airing_today": "checking today’s TV lineup…",
        "tmdb_movie_details": "reading the fine print on that film…",
        "tmdb_tv_details": "getting the scoop on that show…",
        "tmdb_similar": "finding cinematic soulmates…",
        "tmdb_genres": "browsing by vibe and genre…",
        "tmdb_collection": "checking the franchise family tree…",
        "tmdb_watch_providers": "finding where it’s actually watchable…",
        "plex_search": "rifling through your personal vault…",
        "plex_library": "browsing your shelves with white gloves…",
        "plex_recently_added": "peeking at the latest arrivals…",
        "plex_on_deck": "lining up what’s next on deck…",
        "plex_continue_watching": "finding where you left the remote…",
        "plex_unwatched": "dusting off the unseen gems…",
        "plex_collections": "admiring your curated sets…",
        "plex_playlists": "checking your custom mixes…",
        "plex_rating": "updating your royal decree (rating)…",
        "plex_playback": "ensuring smooth, buttery playback…",
        "plex_history": "reviewing your heroic viewing saga…",
        "radarr_lookup": "looking up movie intel…",
        "radarr_add": "adding a fresh title to the vault…",
        "radarr_search": "hunting down the right files…",
        "radarr_queue": "auditing the download queue…",
        "radarr_wanted": "scanning the wishboard…",
        "radarr_calendar": "syncing cinema with your calendar…",
        "sonarr_lookup": "looking up show dossiers…",
        "sonarr_add": "enrolling a new series into the fold…",
        "sonarr_search": "searching for the right episodes…",
        "sonarr_queue": "checking the TV download queue…",
        "sonarr_wanted": "scanning the episode wishlist…",
        "sonarr_calendar": "syncing TV time with real time…",
        "sonarr_monitor": "setting up episode surveillance…",
        "sonarr_episodes": "browsing the episode roster…",
        "sonarr_seasons": "double‑checking season intel…",
        "household_preferences": "consulting your household taste genome…",
        "household_search": "searching across family tastes…",
        "household_update": "refreshing your taste presets…",
        "household_query": "querying the household preference archive…",
    }

    def _match_tool_hint(name: str):
        if not name:
            return None
        # Prefer the longest key that matches to avoid over-broad hits
        for key in sorted(tool_hints.keys(), key=len, reverse=True):
            if key in name or name in key:
                return tool_hints[key]
        return None

    hint = _match_tool_hint(n_tool)

    # Decision logic:
    # 1) If explicitly "thinking", do that.
    if n_type == "thinking":
        # Occasionally pair with a hint for extra context
        if hint and rng.random() < 0.35:
            core = rng.choice(thinking_messages)
            clean_hint = hint[:-1] if hint.endswith("…") else hint
            return f"{core} ({clean_hint})"
        return rng.choice(thinking_messages)

    # 2) If we have a tool hint, use it most of the time.
    if hint and rng.random() < 0.7:
        return f"Still working — {hint}"

    # 3) If multiple passes, show iteration-aware messages.
    if isinstance(iteration, int) and iteration > 1:
        return _iter_message(iteration)

    # 4) Otherwise fall back to base messages.
    return rng.choice(base_messages)


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
        
        # Resolve provider for chat role via config
        from config.loader import resolve_llm_provider_and_model
        provider, _ = resolve_llm_provider_and_model(self.project_root, "chat")  # type: ignore[arg-type]
        api_key = settings.openai_api_key if provider == "openai" else (settings.openrouter_api_key or "")
        
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
                # Show a progress note if it takes too long - optimized threshold
                rc = load_runtime_config(self.project_root)  # type: ignore[attr-defined]
                progress_ms = int(rc.get("ux", {}).get("progressThresholdMs", 3000))  # Reduced from 5000ms for faster feedback
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
                            
                            # Get update interval from config - optimized for better performance
                            update_interval = int(rc.get("ux", {}).get("progressUpdateIntervalMs", 5000)) / 1000  # Increased from 2000ms
                            update_frequency = int(rc.get("ux", {}).get("progressUpdateFrequency", 2))  # Reduced from 4
                            
                            while not done.is_set():
                                try:
                                    await asyncio.sleep(update_interval)
                                    if done.is_set():
                                        break
                                    
                                    # Check if we have new progress information
                                    tool_changed = current_tool != last_tool
                                    progress_type_changed = current_progress_type != last_progress_type
                                    
                                    # Only update on significant changes or based on frequency to reduce overhead
                                    if tool_changed or progress_type_changed or iteration % update_frequency == 0:
                                        # Generate new message based on current state
                                        new_message = _get_clever_progress_message(  # type: ignore[attr-defined]
                                            iteration, 
                                            current_tool, 
                                            current_progress_type
                                        )
                                        
                                        # Only edit if the message actually changed to avoid unnecessary API calls
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
                    response = await agent.aconverse(history)
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
    register_media(client)
    register_discovery(client)
    register_management(client)
    register_preferences(client)
    register_utilities(client)

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

