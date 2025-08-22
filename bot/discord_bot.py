from __future__ import annotations

import asyncio
import os
from typing import Optional
from pathlib import Path
import re
import logging

import discord
from discord import app_commands

from config.loader import load_settings, load_runtime_config
from .commands.search import register as register_search
from .commands.watchlist import register as register_watchlist
from .commands.ratings import register as register_ratings
from .commands.prefs import register as register_prefs
from .conversation import CONVERSATIONS
from .agent import Agent


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
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()


def ephemeral_embed(title: str, description: str) -> discord.Embed:
    embed = discord.Embed(title=title, description=description)
    return embed


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

    async def _reply_llm_message(message: discord.Message) -> None:
        log = logging.getLogger("moviebot.bot")
        if not message.content:
            return
        conv_id = message.channel.id
        # Strip bot mention if present
        content = message.content
        if client.user:  # type: ignore[truthy-bool]
            mention_pattern = re.compile(rf"<@!?{client.user.id}>")
            content = mention_pattern.sub("", content).strip()
        if not content:
            return
        
        settings = load_settings(client.project_root)  # type: ignore[attr-defined]
        
        # Choose provider: OpenRouter if available, otherwise OpenAI
        if settings.openai_api_key:
            api_key = settings.openai_api_key
            provider = "openai"
        else:
            api_key = settings.openrouter_api_key or ""
            provider = "openrouter"
        
        agent = Agent(api_key=api_key, project_root=client.project_root, provider=provider)  # type: ignore[arg-type]
        
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
                rc = load_runtime_config(client.project_root)  # type: ignore[attr-defined]
                progress_ms = int(rc.get("ux", {}).get("progressThresholdMs", 5000))
                done = asyncio.Event()

                async def progress_nag():
                    try:
                        await asyncio.wait_for(done.wait(), timeout=progress_ms / 1000)
                    except asyncio.TimeoutError:
                        try:
                            await message.channel.send("Working on it — checking services…", silent=True)
                        except Exception:
                            pass

                nag_task = asyncio.create_task(progress_nag())
                try:
                    response = await loop.run_in_executor(None, lambda: agent.converse(history))
                finally:
                    done.set()
                    nag_task.cancel()
            text = (
                response.choices[0].message.content  # type: ignore[attr-defined]
                if hasattr(response, "choices") else str(response)
            )
        except Exception as e:  # noqa: BLE001
            text = f"(error talking to model: {e})"
        CONVERSATIONS.add_assistant(conv_id, text)
        log.info("assistant reply", extra={"channel_id": conv_id, "content_preview": text[:120]})
        await message.reply(text[:1900], mention_author=False)

    @client.event
    async def on_message(message: discord.Message) -> None:  # type: ignore[override]
        # Ignore bot/self messages
        if message.author.bot:
            return
        is_dm = message.guild is None
        mentioned = False
        if client.user:
            mentioned = client.user in message.mentions  # type: ignore[truthy-bool]
        if not is_dm and not mentioned:
            return
        await _reply_llm_message(message)

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

