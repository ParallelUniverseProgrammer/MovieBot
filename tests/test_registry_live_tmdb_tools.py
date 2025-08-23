import os
import pytest
from pathlib import Path

from bot.tools.registry import build_openai_tools_and_registry


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tmdb_tools_smoke_live():
    if not os.getenv("TMDB_API_KEY"):
        pytest.skip("TMDB_API_KEY not set")

    _, reg = build_openai_tools_and_registry(Path(__file__).parent.parent)

    # minimal smoke across common tools
    tool_names_and_args = [
        ("tmdb_search", {"query": "Matrix", "page": 1}),
        ("tmdb_trending", {"media_type": "movie", "time_window": "week"}),
        ("tmdb_popular_movies", {}),
        ("tmdb_top_rated_movies", {}),
        ("tmdb_upcoming_movies", {}),
        ("tmdb_now_playing_movies", {}),
    ]

    for name, args in tool_names_and_args:
        out = await reg.get(name)(args)
        assert isinstance(out, dict)


