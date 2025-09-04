import os
import pytest

from integrations.tmdb_client import TMDbClient, TMDbResponseLevel


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tmdb_search_and_details_live():
    api_key = os.getenv("TMDB_API_KEY")
    if not api_key:
        pytest.skip("TMDB_API_KEY not set in environment/.env")

    tmdb = TMDbClient(api_key)

    # Search
    res = await tmdb.search_movie("Matrix", page=1, response_level=TMDbResponseLevel.COMPACT)
    assert isinstance(res, dict)
    results = res.get("results") or []
    if not results:
        pytest.skip("TMDb returned no results for 'Matrix'")

    movie_id = results[0].get("id")
    assert movie_id is not None

    # Details
    details = await tmdb.movie_details(movie_id, response_level=TMDbResponseLevel.STANDARD)
    assert isinstance(details, dict)
    assert details.get("id") == movie_id

    # Trending sanity
    trending = await tmdb.trending("movie", "week", response_level=TMDbResponseLevel.MINIMAL)
    assert isinstance(trending, dict)

    await tmdb.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tmdb_search_with_details_live():
    api_key = os.getenv("TMDB_API_KEY")
    if not api_key:
        pytest.skip("TMDB_API_KEY not set in environment/.env")

    tmdb = TMDbClient(api_key)

    # Test search with details - use a more specific query to get "The Matrix" (1999)
    res = await tmdb.search_movie_with_details("The Matrix", year=1999, page=1, response_level=TMDbResponseLevel.COMPACT, max_details=3)
    assert isinstance(res, dict)
    results = res.get("results") or []
    if not results:
        pytest.skip("TMDb returned no results for 'The Matrix'")

    # Check that we have results
    assert len(results) > 0
    
    # Check that the first few results have detailed information (merged from search + details)
    for i, result in enumerate(results[:3]):  # Check first 3 results
        assert result.get("id") is not None
        assert result.get("title") is not None
        # These fields should be present from the details call
        assert "overview" in result
        # Check for some detail fields that should be present after merging
        print(f"Result {i}: {list(result.keys())}")  # Debug output
        # The details should include additional fields beyond basic search results
        detail_fields = ["genres", "runtime", "production_companies", "credits", "videos", "images"]
        has_detail_fields = any(field in result for field in detail_fields)
        assert has_detail_fields, f"Expected at least one detail field in result, got: {list(result.keys())}"

    await tmdb.close()


