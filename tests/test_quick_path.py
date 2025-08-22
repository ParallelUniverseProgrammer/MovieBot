import pytest
from bot.discord_bot import _get_clever_progress_message  # ensure importable


def test_progress_message_sample():
    # Smoke test existing function
    m = _get_clever_progress_message(1, tool_name="tmdb_search", progress_type="thinking")
    assert isinstance(m, str) and len(m) > 0
