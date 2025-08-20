from __future__ import annotations

import discord
from discord import app_commands

from config.loader import load_settings
from integrations.plex_client import PlexClient


def register(client: discord.Client) -> None:
    tree = client.tree

    @tree.command(name="rate", description="Set a Plex rating by ratingKey (1-10)")
    @app_commands.describe(rating_key="Plex ratingKey", rating="Rating 1-10")
    async def rate(interaction: discord.Interaction, rating_key: int, rating: int) -> None:
        await interaction.response.defer(ephemeral=True)
        if rating < 1 or rating > 10:
            await interaction.followup.send("Rating must be 1-10.", ephemeral=True)
            return
        settings = load_settings(client.project_root)  # type: ignore[attr-defined]
        try:
            plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
            plex.set_rating(rating_key, rating)
            await interaction.followup.send(f"Set rating {rating} on item {rating_key}.", ephemeral=True)
        except Exception as e:  # noqa: BLE001
            await interaction.followup.send(f"Failed to set rating: {e}", ephemeral=True)


