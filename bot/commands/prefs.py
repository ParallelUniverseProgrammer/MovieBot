from __future__ import annotations

import json
from pathlib import Path

import discord
from discord import app_commands
from ..tools.tool_impl import build_preferences_context


def _prefs_path(project_root: Path) -> Path:
    return project_root / "data" / "household_preferences.json"


def _read_prefs(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_prefs(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def register(client: discord.Client) -> None:
    tree = client.tree
    group = app_commands.Group(name="prefs", description="Household preferences")

    @group.command(name="get", description="Show household preferences")
    @app_commands.describe(compact="If true, show a compact, human-oriented summary")
    async def get_prefs(interaction: discord.Interaction, compact: bool = False) -> None:
        await interaction.response.defer(ephemeral=True)
        data = _read_prefs(_prefs_path(client.project_root))  # type: ignore[attr-defined]
        if compact:
            try:
                summary = build_preferences_context(data)
            except Exception as e:  # noqa: BLE001
                summary = f"(failed to build summary: {e})\n" + json.dumps(data, indent=2)
            await interaction.followup.send(summary[:1900], ephemeral=True)
        else:
            text = json.dumps(data, indent=2)[:1900]
            await interaction.followup.send(f"```json\n{text}\n```", ephemeral=True)

    @group.command(name="set", description="Set a top-level key to a JSON value")
    @app_commands.describe(key="Key (e.g., likes, constraints)", json_value="JSON value (e.g., [\"sci-fi\"]) ")
    async def set_key(interaction: discord.Interaction, key: str, json_value: str) -> None:
        await interaction.response.defer(ephemeral=True)
        path = _prefs_path(client.project_root)  # type: ignore[attr-defined]
        data = _read_prefs(path)
        try:
            value = json.loads(json_value)
        except Exception as e:  # noqa: BLE001
            await interaction.followup.send(f"Invalid JSON: {e}", ephemeral=True)
            return
        data[key] = value
        _write_prefs(path, data)
        await interaction.followup.send(f"Updated {key}.", ephemeral=True)

    tree.add_command(group)


