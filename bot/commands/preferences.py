from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands

from ..tools.tool_impl import build_preferences_context, PreferencesStore


def register(client: discord.Client) -> None:
    tree = client.tree
    
    # Preferences group for household preferences
    prefs_group = app_commands.Group(name="prefs", description="Manage household preferences and taste profiles")

    @prefs_group.command(name="show", description="Show household preferences")
    @app_commands.describe(
        compact="Show a compact, human-oriented summary",
        path="Show specific section (e.g., 'likes', 'constraints')"
    )
    async def show_prefs(
        interaction: discord.Interaction, 
        compact: bool = False,
        path: Optional[str] = None
    ):
        await interaction.response.defer(ephemeral=True)
        
        try:
            store = PreferencesStore(client.project_root)
            data = await store.load()
            
            if path:
                # Navigate to specific path
                keys = path.split('.')
                current = data
                for key in keys:
                    if isinstance(current, dict) and key in current:
                        current = current[key]
                    else:
                        await interaction.followup.send(f"Path '{path}' not found", ephemeral=True)
                        return
                
                if compact:
                    try:
                        summary = build_preferences_context({path: current})
                    except Exception:
                        summary = json.dumps(current, indent=2)
                else:
                    summary = json.dumps(current, indent=2)
                
                text = f"**Preferences for '{path}':**\n```json\n{summary}\n```"
            else:
                if compact:
                    try:
                        summary = build_preferences_context(data)
                    except Exception as e:
                        summary = f"(Failed to build summary: {e})\n" + json.dumps(data, indent=2)
                    text = summary
                else:
                    text = f"**All Preferences:**\n```json\n{json.dumps(data, indent=2)}\n```"
            
            await interaction.followup.send(text[:1900], ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"Failed to read preferences: {str(e)}", ephemeral=True)

    @prefs_group.command(name="set", description="Set a preference value")
    @app_commands.describe(
        key="Key to set (e.g., 'likes', 'constraints')",
        json_value="JSON value (e.g., '[\"sci-fi\", \"action\"]')"
    )
    async def set_pref(interaction: discord.Interaction, key: str, json_value: str):
        await interaction.response.defer(ephemeral=True)
        
        try:
            store = PreferencesStore(client.project_root)
            data = await store.load()
            
            try:
                value = json.loads(json_value)
            except json.JSONDecodeError as e:
                await interaction.followup.send(f"❌ Invalid JSON: {e}", ephemeral=True)
                return
            
            # Support dotted path
            data = store._set_by_path(data, key, value)
            await store.save(data)
            
            await interaction.followup.send(
                f"✅ Updated preference '{key}' to: {json_value}", 
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to set preference: {str(e)}", ephemeral=True)

    @prefs_group.command(name="add", description="Add to a list preference")
    @app_commands.describe(
        key="Key to add to (e.g., 'likes', 'dislikes')",
        value="Value to add"
    )
    async def add_pref(interaction: discord.Interaction, key: str, value: str):
        await interaction.response.defer(ephemeral=True)
        
        try:
            store = PreferencesStore(client.project_root)
            data = await store.load()
            try:
                # Try JSON decode for rich values
                parsed: object = json.loads(value)
            except Exception:
                parsed = value
            # Append to list at dotted path
            data = store._list_append(data, key, parsed)
            await store.save(data)
            
            await interaction.followup.send(
                f"✅ Added '{value}' to '{key}'.", 
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to add preference: {str(e)}", ephemeral=True)

    @prefs_group.command(name="remove", description="Remove from a list preference")
    @app_commands.describe(
        key="Key to remove from (e.g., 'likes', 'dislikes')",
        value="Value to remove"
    )
    async def remove_pref(interaction: discord.Interaction, key: str, value: str):
        await interaction.response.defer(ephemeral=True)
        
        try:
            store = PreferencesStore(client.project_root)
            data = await store.load()
            try:
                parsed: object = json.loads(value)
            except Exception:
                parsed = value
            data = store._list_remove_value(data, key, parsed)
            await store.save(data)
            remaining_path_val = store._get_by_path(data, key)
            remaining = ', '.join(remaining_path_val) if isinstance(remaining_path_val, list) and remaining_path_val else 'none'
            await interaction.followup.send(
                f"✅ Removed '{value}' from '{key}'. Remaining values: {remaining}", 
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to remove preference: {str(e)}", ephemeral=True)

    @prefs_group.command(name="search", description="Search preferences for specific terms")
    @app_commands.describe(
        query="Search term",
        limit="Maximum results to show (default: 10)"
    )
    async def search_prefs(interaction: discord.Interaction, query: str, limit: Optional[int] = 10):
        await interaction.response.defer(ephemeral=True)
        
        try:
            store = PreferencesStore(client.project_root)
            data = await store.load()
            
            # Simple text search through preferences
            results = []
            query_lower = query.lower()
            
            def search_dict(d, path=""):
                for k, v in d.items():
                    current_path = f"{path}.{k}" if path else k
                    
                    if isinstance(v, str) and query_lower in v.lower():
                        results.append(f"• {current_path}: {v}")
                    elif isinstance(v, list):
                        for item in v:
                            if isinstance(item, str) and query_lower in item.lower():
                                results.append(f"• {current_path}: {item}")
                    elif isinstance(v, dict):
                        search_dict(v, current_path)
            
            search_dict(data)
            
            if results:
                text = f"**Search results for '{query}':**\n" + "\n".join(results[:limit])
            else:
                text = f"No preferences found matching '{query}'"
            
            await interaction.followup.send(text[:1900], ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Search failed: {str(e)}", ephemeral=True)

    @prefs_group.command(name="reset", description="Reset all preferences (use with caution!)")
    async def reset_prefs(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            store = PreferencesStore(client.project_root)
            data = await store.load()
            
            if not data:
                await interaction.followup.send("No preferences to reset", ephemeral=True)
                return
            
            # Create backup
            backup_path = (client.project_root / "data" / "household_preferences.json").with_suffix('.json.backup')
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            with open(backup_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            
            # Reset to empty
            await store.save({})
            
            await interaction.followup.send(
                f"✅ Reset all preferences. Backup saved to {backup_path.name}", 
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to reset preferences: {str(e)}", ephemeral=True)

    tree.add_command(prefs_group)
