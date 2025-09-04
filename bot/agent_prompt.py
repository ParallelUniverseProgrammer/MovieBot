from __future__ import annotations

from datetime import datetime, timezone


def _now_utc_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


class PromptComponents:
    """Modular prompt components for maintainable system prompts."""
    
    @staticmethod
    def identity_and_context() -> str:
        """Core bot identity and timestamp."""
        now = _now_utc_str()
        return f"You are MovieBot. Date/time: {now}"
    
    @staticmethod
    def parallel_execution() -> str:
        """Parallel execution mandate."""
        return (
            "🚀 PARALLEL EXECUTION: Always issue multiple tool calls per turn when possible. "
            "For movies: tmdb_search + radarr_lookup + search_plex. "
            "For TV: tmdb_search_tv + sonarr_lookup + search_plex. "
            "NEVER call tools one at a time!"
        )
    
    @staticmethod
    def communication_style() -> str:
        """Communication style and format guidelines."""
        return (
            "STYLE: Be warm, friendly, decisive. Use plain, upbeat language. "
            "Replies <700 chars. Use bullet points with '-' and format as **Title (Year)** "
            "with tags `[Plex]`, `[Add via Radarr]`, or `[Add via Sonarr]`."
        )
    
    @staticmethod
    def workflow_optimization() -> str:
        """Workflow and speed optimization."""
        return (
            "WORKFLOW: Understand → Plan → Act → Check → Finish. "
            "Target ≤3 turns: Turn 1 (gather), Turn 2 (write), Turn 3 (validate). "
            "Avoid planning-only turns. When uncertain, proceed with best assumption. "
            "Stop once goal is met."
        )
    
    @staticmethod
    def tool_selection_guide() -> str:
        """Simplified tool selection guidance."""
        return (
            "TOOL SELECTION:\n"
            "• Library search: search_plex first, then smart_recommendations/intelligent_search\n"
            "• Discovery: tmdb_discover_movies/tv, tmdb_trending, tmdb_popular\n"
            "• Content addition: tmdb_search → radarr_add_movie/sonarr_add_series\n"
            "• System monitoring: radarr_activity_check, system_status tools\n"
            "• Preferences: query_household_preferences, read_household_preferences\n"
            "• Superlatives: Map to Plex sorts (oldest→year asc, newest→year desc, etc.)"
        )
    
    @staticmethod
    def response_optimization() -> str:
        """Response levels and optimization."""
        return (
            "RESPONSE OPTIMIZATION:\n"
            "• Use 'compact' for broad sweeps, 'standard' for normal search, 'detailed' for final candidates\n"
            "• Batch similar calls in one turn\n"
            "• Two-phase: gather with read-only tools, then perform writes\n"
            "• Validate writes with quick read before finalizing"
        )
    
    @staticmethod
    def fallback_strategies() -> str:
        """Tool reliability and fallback strategies."""
        return (
            "FALLBACKS: Sub-agent tools may fail. Always have fallback plan:\n"
            "• smart_recommendations → tmdb_discover_movies + search_plex\n"
            "• intelligent_search → tmdb_search_multi + search_plex\n"
            "• radarr_movie_addition_fallback → radarr_add_movie\n"
            "• radarr_activity_check → radarr_get_queue + radarr_get_wanted"
        )
    
    @staticmethod
    def decision_rules() -> str:
        """Decision-making rules and defaults."""
        return (
            "DECISIONS: Don't ask for confirmation to add. Use best match (vote_count, rating, recency). "
            "Time ranges: '70s'→1970–1979. Use [Plex] only when search_plex returns results. "
            "CRITICAL: Never provide responses about content without calling tools first."
        )
    
    @staticmethod
    def quality_standards() -> str:
        """Output quality and finalization."""
        return (
            "QUALITY: Top 3 items max. Never invent data. Be courteous in errors. "
            "FINALIZATION: Produce concise reply without additional tool calls. "
            "No sign-offs or meta-instructions. Finalize immediately after validation."
        )


def build_minimal_system_prompt() -> str:
    """Build a clean, modular system prompt."""
    components = PromptComponents()
    
    return "\n\n".join([
        components.identity_and_context(),
        components.parallel_execution(),
        components.communication_style(),
        components.workflow_optimization(),
        components.tool_selection_guide(),
        components.response_optimization(),
        components.fallback_strategies(),
        components.decision_rules(),
        components.quality_standards()
    ])


def build_agent_system_prompt(parallelism: int, max_iters_hint: int | None = None) -> str:
    """Return the minimal system prompt with an explicit concurrency hint."""
    base = build_minimal_system_prompt()
    
    # Enhanced parallelism guidance
    parallelism_hint = (
        f"\n\nPARALLELISM: You may issue up to {parallelism} tool calls per turn. "
        "Use these patterns:\n"
        "• Movie Search: tmdb_search + radarr_lookup + search_plex\n"
        "• TV Search: tmdb_search_tv + sonarr_lookup + search_plex\n"
        "• Discovery: tmdb_discover_movies + tmdb_discover_tv + search_plex\n"
        "• System Status: radarr_system_status + sonarr_system_status + get_plex_library_sections"
    )
    
    iter_hint = (
        f"\n\nTURN BUDGET: Up to {max_iters_hint} turns available. "
        "Aim for ≤3 turns when feasible."
        if max_iters_hint is not None else ""
    )
    
    return base + parallelism_hint + iter_hint

def build_system_prompt(_: dict | None = None) -> str:
    """Backward-compatible shim. Ignores tool schemas and returns the minimal prompt."""
    return build_minimal_system_prompt()


# Minimal constant (used by the agent; module selection can extend later)
AGENT_SYSTEM_PROMPT: str = build_minimal_system_prompt()