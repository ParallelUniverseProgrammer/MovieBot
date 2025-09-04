from __future__ import annotations

import asyncio
import os
from typing import Optional
from pathlib import Path
import re
import logging
import random
import time
from datetime import datetime

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
from .agent_prompt import build_minimal_system_prompt
from .discord_embeds import MovieBotEmbeds, ProgressIndicator


def ephemeral_embed(title: str, description: str) -> discord.Embed:
    embed = discord.Embed(title=title, description=description)
    return embed


class ProgressCalculator:
    """Calculates meaningful progress percentages based on agent work phases."""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """Reset progress tracking state."""
        self.agent_started = False
        self.llm_calls = 0
        self.tool_calls = 0
        self.tool_completions = 0
        self.current_phase = None
        self.iteration = 0
        self.max_iterations = 6  # Default max iterations
    
    def calculate_progress(self, event_type: str, data: dict = None) -> float:
        """Calculate progress percentage based on event type and data."""
        if event_type == "agent.start":
            self.agent_started = True
            self.max_iterations = data.get("iters", 6) if data else 6
            return 0.05  # 5% - just started
        
        elif event_type == "thinking":
            self.iteration = data.get("iteration", "1/6").split("/")[0] if data else 1
            try:
                iter_num = int(self.iteration)
                # Thinking phase: 5-15% of total progress
                return 0.05 + (iter_num - 1) * 0.02
            except (ValueError, TypeError):
                return 0.10
        
        elif event_type == "llm.start":
            self.llm_calls += 1
            # LLM calls: 15-25% of total progress
            return 0.15 + min(self.llm_calls * 0.02, 0.10)
        
        elif event_type == "llm.finish":
            # LLM completion: 25-35% of total progress
            return 0.25 + min(self.llm_calls * 0.02, 0.10)
        
        elif event_type == "tool.start":
            self.tool_calls += 1
            # Tool execution: 35-65% of total progress
            return 0.35 + min(self.tool_calls * 0.05, 0.30)
        
        elif event_type == "tool.finish":
            self.tool_completions += 1
            # Tool completion: 65-85% of total progress
            return 0.65 + min(self.tool_completions * 0.05, 0.20)
        
        elif event_type == "tool.error":
            # Tool error still counts as progress
            self.tool_completions += 1
            return 0.65 + min(self.tool_completions * 0.05, 0.20)
        
        elif event_type.startswith("phase."):
            self.current_phase = event_type
            # Phase work: 85-95% of total progress
            phase_progress = 0.85
            if "validation" in event_type:
                phase_progress = 0.90
            elif "read_only" in event_type:
                phase_progress = 0.88
            elif "write_enabled" in event_type:
                phase_progress = 0.92
            return phase_progress
        
        elif event_type == "agent.finish":
            return 1.0  # 100% - completed
        
        elif event_type == "agent.metrics":
            # Near completion: 95-99%
            return 0.95
        
        # Default fallback based on current state
        if self.tool_completions > 0:
            return 0.70 + min(self.tool_completions * 0.05, 0.25)
        elif self.tool_calls > 0:
            return 0.50 + min(self.tool_calls * 0.03, 0.20)
        elif self.llm_calls > 0:
            return 0.30 + min(self.llm_calls * 0.02, 0.15)
        elif self.agent_started:
            return 0.10
        else:
            return 0.05


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
        # New and more varied additions:
        "Consulting the snack oracle for optimal popcorn pairing…",
        "Dusting off the genre compass…",
        "Running a vibe check on the database…",
        "Polishing the crystal ball for sharper predictions…",
        "Rebooting the cleverness module…",
        "Syncing with the collective movie consciousness…",
        "Folding plot twists into origami…",
        "Recalibrating the snark filter…",
        "Googling the meaning of ‘taste’…",
        "Rehearsing recommendations in the mirror…",
        "Herding recommendations like caffeinated cats…",
        "Spinning up the quantum suggestion engine…",
        "Debugging the taste matrix…",
        "Recharging the inspiration capacitor…",
        "Cross-referencing with the taste thesaurus…",
        "Staring into the digital abyss… the abyss recommends back…",
        "Consulting the council of imaginary critics…",
        "Wrestling with indecision (and winning)…",
        "Simmering ideas for extra flavor…",
    ]

    thinking_messages = [
        # Original spirit, expanded and spiced up
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

        # New, playful and varied
        "Brainstorming… letting the neurons do jazz hands…",
        "Crunching numbers… and a few popcorn kernels…",
        "Pondering… waiting for inspiration to buffer…",
        "Simmering… letting the ideas marinate for extra flavor…",
        "Consulting the algorithmic crystal ball…",
        "Rewiring the plot twist detector…",
        "Daydreaming… but only about good recommendations…",
        "Debugging the taste matrix…",
        "Recalibrating the snark filter…",
        "Syncing with the collective movie consciousness…",
        "Sharpening pencils and wits…",
        "Rebooting the cleverness module…",
        "Polishing the punchlines…",
        "Herding thoughts like caffeinated cats…",
        "Tuning the taste buds for maximum nuance…",
        "Recharging the inspiration capacitor…",
        "Consulting the council of imaginary critics…",
        "Running a vibe check on the data…",
        "Untangling the spaghetti logic…",
        "Replaying the mental montage in slow motion…",

        # More variety, meta, and fun
        "Staring into the digital abyss… the abyss recommends back…",
        "Rehearsing the answer in the mirror…",
        "Googling the meaning of ‘taste’…",
        "Waiting for the muse to clock in…",
        "Folding plot twists into origami…",
        "Cross-referencing with the taste thesaurus…",
        "Spinning up the quantum recommendation engine…",
        "Consulting the snack oracle for wisdom…",
        "Running a background check on clichés…",
        "Polishing the crystal ball for clarity…",
        "Replaying the last good idea on loop…",
        "Wrestling with indecision (and winning)…",
        "Recharging the cleverness battery…",
        "Tuning the sarcasm dial to ‘just right’…",
        "Reassembling the plot puzzle…",
        "Running a taste audit…",
        "Consulting the plot bunny farm…",
        "Re-indexing the clever quips…",
        "Waiting for the inspiration download to finish…",
        "Running a full diagnostic on the funniness module…",
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

    # 1b) If starting a tool, make it feel kinetic.
    if n_type == "tool_start":
        if hint:
            return f"Opening the toolbox — {hint}"
        return "Rolling up sleeves… initiating complicated antics…"

    # 1c) If finishing a tool, give a cheeky wrap.
    if n_type in ("tool_done", "tool_ok", "tool_error"):
        suffix = "(mostly in one piece)" if n_type != "tool_error" else "(it fought back)"
        if hint:
            return f"Crossing that off — {hint} {suffix}"
        return f"One box checked {suffix}"

    # 1d) If finalizing, imply synthesis.
    if n_type == "finalizing":
        return "Polishing the epilogue… arranging punchlines and citations…"

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
        
        # Choose provider by config priority
        from config.loader import resolve_llm_selection
        provider, _sel = resolve_llm_selection(self.project_root, "chat")  # type: ignore[attr-type]
        api_key = settings.openai_api_key if provider == "openai" else (settings.openrouter_api_key or "")
        
        progress_message = None
        progress_update_task = None
        # Event-driven progress updates
        progress_events: asyncio.Queue = asyncio.Queue()
        last_rendered = None
        iteration_counter = 0
        
        # Progress callback function for the agent -> enqueue events
        def progress_callback(progress_type: str, details: str):
            try:
                # Drop noisy heartbeat updates from the UI queue
                if progress_type == "heartbeat":
                    return
                # Normalize event types from agent
                mapped_type = progress_type
                if progress_type == "tool":
                    mapped_type = "tool_start"
                # Ensure thread-safety if ever called off-loop
                try:
                    loop = asyncio.get_running_loop()
                    loop.call_soon_threadsafe(progress_events.put_nowait, {"type": mapped_type, "details": details})
                except RuntimeError:
                    # No running loop - this shouldn't happen in Discord context
                    # but if it does, we'll skip the update rather than risk race conditions
                    pass
            except Exception:
                # Silent failure for progress updates
                pass
        
        agent = Agent(api_key=api_key, project_root=self.project_root, provider=provider, progress_callback=progress_callback)  # type: ignore[arg-type]
        
        # Set the LLM client in the conversation store for token counting
        CONVERSATIONS.set_llm_client(agent.llm)
        
        CONVERSATIONS.add_user(conv_id, content)
        log.info("incoming message", extra={
            "channel_id": conv_id,
            "author": str(message.author),
            "content_preview": content[:120],
        })

        # Lightweight quick-path: respond directly with a small model if tools likely unnecessary
        def _is_quick_path(s: str) -> bool:
            s_lo = s.strip().lower()
            if not s_lo:
                return False

            # Avoid quick path for actionable/tool-intent requests
            blocklist = [
                "search", "find", "recommend", "recommendation", "trending", "popular",
                "add", "queue", "status", "recent", "on deck", "continue", "rate", "rating",
                "unwatched", "collection", "details", "similar", "top rated", "upcoming",
                "now playing", "watch providers", "providers",
                "plex", "radarr", "sonarr", "tmdb"
            ]
            for term in blocklist:
                if re.search(r"\b" + re.escape(term) + r"\b", s_lo):
                    return False

            # Heuristic: treat "Title (Year)" patterns as actionable (e.g., add/search), not quick path
            # e.g., "synchronic (2020)", "inception (2010)"
            try:
                if re.search(r"\((19|20)\d{2}\)", s, flags=re.IGNORECASE):
                    return False
            except Exception:
                pass

            # Greetings / pleasantries / capability queries / style-only asks
            quick_keywords = [
                "hi", "hello", "hey", "how are you", "what can you do", "help", "capabilities",
                "who are you", "what is moviebot", "explain yourself", "about you", "commands",
                "format", "how to use", "usage", "examples", "tips", "thanks", "thank you"
            ]

            for phrase in quick_keywords:
                if re.search(r"\b" + re.escape(phrase) + r"\b", s_lo):
                    return True

            # Default: not quick-path
            return False

        # Quick-path answer function using the 'quick' role
        async def _maybe_quick_path_response(text: str) -> str | None:
            if not _is_quick_path(text):
                return None
            from config.loader import resolve_llm_selection
            provider, sel = resolve_llm_selection(self.project_root, "quick")  # type: ignore[attr-type]
            api_key = settings.openai_api_key if provider == "openai" else (settings.openrouter_api_key or "")
            # Minimal prompt, no tools
            system_msg = {"role": "system", "content": build_minimal_system_prompt()}
            user_msg = {"role": "user", "content": text}
            llm = Agent(api_key=api_key, project_root=self.project_root, provider=provider).llm  # type: ignore[arg-type]
            try:
                resp = await llm.achat(model=sel.get("model", "gpt-5"), messages=[system_msg, user_msg], **(sel.get("params", {}) or {}))
                content = resp.choices[0].message.content  # type: ignore[attr-defined]
                return content or ""
            except Exception:
                return None

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
                used_quick_path = False

                async def progress_updater():
                    """Update the progress message only when real events occur, but not too often."""
                    nonlocal progress_message, last_rendered
                    # Load throttling knobs
                    rc_local = load_runtime_config(self.project_root)  # type: ignore[attr-defined]
                    min_update_ms = int(rc_local.get("ux", {}).get("progressUpdateIntervalMs", 5000))
                    freq = int(rc_local.get("ux", {}).get("progressUpdateFrequency", 3))
                    last_edit_ms = 0.0
                    event_counter = 0
                    
                    # Initialize progress calculator
                    progress_calc = ProgressCalculator()
                    
                    try:
                        # Wait until either done or threshold elapses
                        await asyncio.wait_for(done.wait(), timeout=progress_ms / 1000)
                        return  # Completed before we needed any status message
                    except asyncio.TimeoutError:
                        pass

                    # After threshold, create the status message on first event or use a generic opener
                    try:
                        try:
                            evt = await asyncio.wait_for(progress_events.get(), timeout=1.0)
                        except asyncio.TimeoutError:
                            evt = {"type": "thinking", "details": ""}

                        # Calculate progress based on event type
                        progress_value = progress_calc.calculate_progress(evt.get("type"), evt)
                        initial = _get_clever_progress_message(1,  # type: ignore[attr-defined]
                                                               evt.get("details"),
                                                               evt.get("type"))
                        
                        # Create rich progress embed
                        progress_embed = MovieBotEmbeds.create_progress_embed(
                            "MovieBot Working",
                            initial,
                            progress=progress_value,
                            status="working"
                        )
                        progress_message = await message.channel.send(embed=progress_embed, silent=True)
                        last_rendered = initial

                        # Consume subsequent events until done
                        while not done.is_set():
                            try:
                                evt = await asyncio.wait_for(progress_events.get(), timeout=30)
                            except asyncio.TimeoutError:
                                # No new events for a while; do not update arbitrarily
                                continue

                            # Determine if we should update based on type, frequency, and time interval
                            ptype = evt.get("type")
                            if ptype in {"heartbeat"}:
                                continue

                            event_counter += 1
                            now_ms = time.monotonic() * 1000.0
                            should_update = False
                            if (now_ms - last_edit_ms) >= max(500, min_update_ms):
                                should_update = True
                            elif freq > 1 and (event_counter % freq == 0):
                                should_update = True
                            if not should_update:
                                continue

                            # Calculate progress based on event type
                            progress_value = progress_calc.calculate_progress(ptype, evt)
                            tool_name = evt.get("details")
                            new_message = _get_clever_progress_message(event_counter, tool_name, ptype)  # type: ignore[attr-defined]
                            if progress_message and new_message != last_rendered:
                                # Update progress embed with calculated progress
                                updated_embed = MovieBotEmbeds.create_progress_embed(
                                    "MovieBot Working",
                                    new_message,
                                    progress=progress_value,
                                    status="working"
                                )
                                await progress_message.edit(embed=updated_embed)
                                last_rendered = new_message
                                last_edit_ms = now_ms
                    except Exception as e:
                        log.warning(f"Failed to send or update progress message: {e}")

                try:
                    # Try quick-path first (do not start progress updates yet)
                    quick_text = await _maybe_quick_path_response(content)
                    if quick_text is not None and quick_text.strip():
                        response = {"choices": [{"message": {"content": quick_text}}]}
                        used_quick_path = True
                    else:
                        # Only start progress updates if we are not using quick path
                        progress_update_task = asyncio.create_task(progress_updater())
                        try:
                            # Buffer streamed chunks internally; do not send partials to the user
                            streamed_text_parts: list[str] = []

                            async def _on_stream(chunk: str) -> None:
                                if not chunk:
                                    return
                                streamed_text_parts.append(chunk)

                            response = await agent.aconverse(history, stream_final_to_callback=_on_stream)
                        except Exception:
                            # As a last resort, try quick-path even if heuristic failed initially
                            fallback_text = await _maybe_quick_path_response(content)
                            if fallback_text:
                                response = {"choices": [{"message": {"content": fallback_text}}]}
                                used_quick_path = True
                            else:
                                raise
                finally:
                    done.set()
                    if progress_update_task:
                        progress_update_task.cancel()
                        # Wait for task to complete cancellation to prevent memory leaks
                        try:
                            await asyncio.wait_for(progress_update_task, timeout=1.0)
                        except (asyncio.CancelledError, asyncio.TimeoutError):
                            pass
                        
            # Extract text from response for both SDK objects and plain dicts
            try:
                if isinstance(response, dict):
                    choices = response.get("choices", [])  # type: ignore[assignment]
                    if choices and isinstance(choices[0], dict):
                        msg = choices[0].get("message", {})
                        text = msg.get("content", "")
                    else:
                        text = str(response)
                elif hasattr(response, "choices"):
                    text = response.choices[0].message.content  # type: ignore[attr-defined]
                else:
                    text = str(response)
            except Exception:
                text = str(response)
        except Exception as e:  # noqa: BLE001
            text = f"(error talking to model: {e})"
            done.set()
            if progress_update_task:
                progress_update_task.cancel()
        
        # Send final reply with rich embed
        CONVERSATIONS.add_assistant(conv_id, text)
        log.info("assistant reply", extra={"channel_id": conv_id, "content_preview": text[:120]})
        
        # Create a rich embed for the response
        if used_quick_path:
            # Quick path responses get a simple embed
            response_embed = discord.Embed(
                title="MovieBot Response",
                description=text[:1900],
                color=MovieBotEmbeds.COLORS['info'],
                timestamp=datetime.utcnow()
            )
            response_embed.set_footer(text="Quick Response", icon_url="https://cdn.discordapp.com/emojis/1234567890.png")
        else:
            # Agent responses get a more detailed embed
            response_embed = discord.Embed(
                title="🎬 MovieBot Analysis",
                description=text[:1900],
                color=MovieBotEmbeds.COLORS['plex'],
                timestamp=datetime.utcnow()
            )
            response_embed.set_footer(text="AI-Powered Media Assistant", icon_url="https://cdn.discordapp.com/emojis/1234567890.png")
        
        await message.reply(embed=response_embed, mention_author=False)

        # Delete the progress message if it exists
        if progress_message:
            try:
                await progress_message.delete()
            except Exception as e:
                log.warning(f"Failed to delete progress message: {e}")

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
    
    # Initialize tool registry cache at startup for performance
    from .tools.registry_cache import initialize_registry_cache
    initialize_registry_cache(client.project_root)

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
        print("Bot Has Started!")
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("Bot stopped.")
        pass

