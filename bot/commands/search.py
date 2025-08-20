from __future__ import annotations

import discord
from discord import app_commands

from config.loader import load_settings
from integrations.plex_client import PlexClient
from integrations.tmdb_client import TMDbClient


def register(client: discord.Client) -> None:
    tree = client.tree

    @tree.command(name="search", description="Search Plex (local) and optionally TMDb")
    @app_commands.describe(query="Title to search", external="Also search TMDb")
    async def search(interaction: discord.Interaction, query: str, external: bool = False) -> None:
        await interaction.response.defer(ephemeral=True)
        settings = load_settings(client.project_root)  # type: ignore[attr-defined]

        # Plex search
        try:
            plex = PlexClient(settings.plex_base_url, settings.plex_token or "")
            plex_results = plex.search_movies(query)
            plex_lines = [f"Plex: {m.title} ({getattr(m, 'year', '?')}) — ratingKey {getattr(m, 'ratingKey', 'n/a')}" for m in plex_results[:10]]
        except Exception as e:  # noqa: BLE001
            plex_lines = [f"Plex search failed: {e}"]

        # TMDb optional
        tmdb_lines = []
        if external:
            try:
                tmdb = TMDbClient(settings.tmdb_api_key or "")
                data = await tmdb.search_movie(query)
                results = data.get("results", [])[:10]
                tmdb_lines = [f"TMDb: {r.get('title')} ({(r.get('release_date') or '????')[:4]}) — tmdbId {r.get('id')}" for r in results]
                await tmdb.close()
            except Exception as e:  # noqa: BLE001
                tmdb_lines = [f"TMDb search failed: {e}"]

        chunks = ["\n".join(plex_lines)]
        if tmdb_lines:
            chunks.append("\n".join(tmdb_lines))
        text = "\n\n".join(chunks)
        if not text:
            text = "No results."
        await interaction.followup.send(text, ephemeral=True)


