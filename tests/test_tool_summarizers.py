from bot.tool_summarizers import summarize_tool_result


def test_summarize_plex_items_truncates_and_keeps_keys():
    res = {"items": [{"title": "A", "year": 2020, "rating": 8.1, "ratingKey": 1, "type": "movie", "extra": 1} for _ in range(10)], "total_found": 10}
    out = summarize_tool_result("get_plex_recently_added", res, max_items=3)
    assert "items" in out and len(out["items"]) == 3
    assert set(out["items"][0].keys()) <= {"title", "year", "rating", "ratingKey", "type"}


def test_summarize_tmdb_results_truncates():
    res = {"page": 1, "total_pages": 5, "total_results": 100, "results": [{"id": 1, "title": "T", "overview": "...", "vote_average": 7.2, "release_date": "2024-01-01", "media_type": "movie", "poster_path": "/x"} for _ in range(10)]}
    out = summarize_tool_result("tmdb_search", res, max_items=2)
    assert out["page"] == 1 and len(out["results"]) == 2


def test_default_truncates_top_level_list():
    res = {"data": list(range(10))}
    out = summarize_tool_result("unknown_tool", res, max_items=4)
    assert len(out["data"]) == 4
