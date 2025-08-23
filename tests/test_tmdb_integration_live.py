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


