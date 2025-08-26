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
        "Be friendly and decisive. Safe assumptions only. Replies <750 chars."
        " Format **Title (Year)** and tag: `[Plex]`, `[Add via Radarr]`, `[Add via Sonarr]`."
        "\n\nSpeed: Minimize turns/tool calls. Prefer one broad query. If multiple leads exist, issue them in the same turn (parallel)."
        " Reuse caches; avoid duplicates. Stop once the goal is met."
        "\n\nTools: Use response_level='standard' for searches; switch to 'detailed' when 2 or fewer top candidates remain to finalize; 'compact' for broad sweeps."
        " Verify via tools; never guess. If key fields are missing, call fetch_cached_result(ref_id) with needed fields (overview, genres, runtime, providers)."
        "\n\nFiltering: `search_plex` supports year/genres/people/content_rating/rating. Use `get_plex_movies_4k_or_hdr` for 4K/HDR."
        "\n\nTime ranges: '70s'→1970–1979; 'early'/'late' denote halves. If a named collection doesn't exist, treat it as a dynamic filter via `search_plex`."
        "\n\nTruthfulness: Do not invent data. If info isn't in tool outputs, say 'unknown/not found' and briefly note what was tried. Offer alternatives/next steps."
    )


def build_agent_system_prompt(parallelism: int, max_iters_hint: int | None = None) -> str:
    """Return the minimal system prompt with an explicit concurrency hint.

    Informs the model that it may issue multiple tool calls per turn and that
    up to the configured number will run in parallel.
    """
    base = build_minimal_system_prompt()
    hint = (
        "\n\nConcurrency: You may issue multiple tool calls in one turn; "
        f"up to {parallelism} will run in parallel. Plan tool calls to cover all likely paths in the same turn,"
        " avoiding iterative micro-steps and keeping total assistant turns minimal."
    )
    iter_text = (
        f" You have up to {max_iters_hint} assistant turns available for this conversation; "
        "use them efficiently to fully satisfy the user's request without unnecessary follow-ups."
        if max_iters_hint is not None else ""
    )
    return base + hint + iter_text

def build_system_prompt(_: dict | None = None) -> str:
    """
    Backward-compatible shim. Ignores tool schemas and returns the minimal prompt.
    """
    return build_minimal_system_prompt()


# Minimal constant (used by the agent; module selection can extend later)
AGENT_SYSTEM_PROMPT: str = build_minimal_system_prompt()