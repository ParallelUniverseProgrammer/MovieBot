from __future__ import annotations

from datetime import datetime, timezone


def _now_utc_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def build_minimal_system_prompt() -> str:
    """
    Minimal, speed-first system prompt without tool catalogs.
    Keep guidance compact and rely on tool schema attachment for capabilities.
    """
    now = _now_utc_str()
    return (
        f"You are MovieBot. Date/time: {now}\n\n"
        "Be friendly, efficient, and decisive. Prefer making smart assumptions over asking follow-ups,"
        " except for destructive actions. Keep replies under 750 characters, format titles as **Title (Year)**,"
        " and use code-style availability tags like `[Plex]`, `[Add via Radarr]`, `[Add via Sonarr]`."
        "\n\nEfficiency: Use minimal/compact tool response levels by default; request details only when necessary."
        " Always verify via tools; never guess IDs or availability."
    )


def build_system_prompt(_: dict | None = None) -> str:
    """
    Backward-compatible shim. Ignores tool schemas and returns the minimal prompt.
    """
    return build_minimal_system_prompt()


# Minimal constant (used by the agent; module selection can extend later)
AGENT_SYSTEM_PROMPT: str = build_minimal_system_prompt()