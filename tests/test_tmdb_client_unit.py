import pytest

from integrations.tmdb_client import TMDbClient, TMDbResponseLevel


class _FakeResponse:
    def __init__(self, status=200, json_data=None, text_data=""):
        self.status = status
        self._json = json_data or {}
        self._text = text_data

    async def json(self):
        return self._json

    async def text(self):
        return self._text

    def release(self):
        # No-op for unit tests
        pass


class _FakeClient:
    def __init__(self, response):
        self._response = response

    async def request(self, method, url, params=None, json=None, headers=None):
        return self._response

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_search_movie_serialization_levels():
    payload = {
        "page": 1,
        "total_pages": 10,
        "total_results": 100,
        "results": [
            {
                "id": 603,
                "title": "The Matrix",
                "overview": "A hacker discovers …",
                "vote_average": 7.5,
                "vote_count": 1000,
                "release_date": "1999-03-31",
                "poster_path": "/x.jpg",
                "backdrop_path": "/b.jpg",
                "popularity": 10.0,
                "original_language": "en",
                "original_title": "The Matrix",
            }
        ],
    }
    fake_resp = _FakeResponse(status=200, json_data=payload)
    c = TMDbClient(api_key="k")
    c._client = _FakeClient(fake_resp)

    # minimal
    out = await c.search_movie("matrix", response_level=TMDbResponseLevel.MINIMAL)
    item = out["results"][0]
    assert set(item.keys()) <= {"id", "title", "media_type", "release_date", "vote_average"}

    # compact
    out = await c.search_movie("matrix", response_level=TMDbResponseLevel.COMPACT)
    item = out["results"][0]
    assert "overview" in item and "poster_path" in item

    # standard
    out = await c.search_movie("matrix", response_level=TMDbResponseLevel.STANDARD)
    item = out["results"][0]
    assert "backdrop_path" in item and "original_title" in item


@pytest.mark.asyncio
async def test_movie_details_serialization_and_error():
    # success path with STANDARD
    item = {
        "id": 1,
        "title": "X",
        "overview": "...",
        "genres": [{"id": 1, "name": "Action"}],
        "runtime": 120,
        "poster_path": "/p.jpg",
    }
    c = TMDbClient("k", default_response_level=TMDbResponseLevel.COMPACT)
    c._client = _FakeClient(_FakeResponse(status=200, json_data=item))
    out = await c.movie_details(1, response_level=TMDbResponseLevel.STANDARD)
    assert out["id"] == 1 and out["genres"][0]["name"] == "Action"

    # error path
    c._client = _FakeClient(_FakeResponse(status=404, json_data={"status_message": "Not found"}, text_data="Not found"))
    with pytest.raises(RuntimeError):
        await c.movie_details(9999)


@pytest.mark.asyncio
async def test_search_keyword_endpoint():
    payload = {"page": 1, "total_pages": 1, "total_results": 1, "results": [{"id": 1, "name": "time travel"}]}
    c = TMDbClient("k")
    c._client = _FakeClient(_FakeResponse(status=200, json_data=payload))
    out = await c.search_keyword("time")
    assert out["results"][0]["name"] == "time travel"


@pytest.mark.asyncio
async def test_client_close_delegates():
    closed = {"v": False}

    class _C:
        async def close(self):
            closed["v"] = True

    c = TMDbClient("k")
    c._client = _C()
    await c.close()
    assert closed["v"] is True


