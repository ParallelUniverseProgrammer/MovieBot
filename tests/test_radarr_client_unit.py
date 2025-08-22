import pytest
from unittest.mock import patch, Mock, AsyncMock

from integrations.radarr_client import RadarrClient


def make_response(data):
    resp = Mock()
    resp.json.return_value = data
    resp.raise_for_status = Mock()
    return resp


def setup_async_client(mock_async_client, response_by_method):
    client = AsyncMock()
    mock_async_client.return_value = client
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    # Attach method responses
    for method_name, resp in response_by_method.items():
        getattr(client, method_name).return_value = resp
    return client


@pytest.mark.asyncio
async def test_system_status_calls_correct_endpoint():
    with patch('integrations.radarr_client.httpx.AsyncClient') as MockAsyncClient:
        resp = make_response({"version": "4.0.0"})
        client = setup_async_client(MockAsyncClient, {"get": resp})

        rc = RadarrClient("http://localhost:7878", "secret")
        out = await rc.system_status()

        assert out == {"version": "4.0.0"}
        client.get.assert_called_once_with("/api/v3/system/status")


@pytest.mark.asyncio
async def test_quality_profiles_and_root_folders():
    with patch('integrations.radarr_client.httpx.AsyncClient') as MockAsyncClient:
        profiles_resp = make_response([{"id": 1, "name": "HD-1080p"}])
        folders_resp = make_response([{"path": "/data/movies"}])
        client = setup_async_client(MockAsyncClient, {"get": profiles_resp})

        rc = RadarrClient("http://localhost:7878", "secret")
        profiles = await rc.quality_profiles()
        assert profiles == [{"id": 1, "name": "HD-1080p"}]
        client.get.assert_called_with("/api/v3/qualityprofile")

        # Switch return for subsequent call
        client.get.return_value = folders_resp
        folders = await rc.root_folders()
        assert folders == [{"path": "/data/movies"}]
        client.get.assert_called_with("/api/v3/rootfolder")


@pytest.mark.asyncio
async def test_get_movies_with_and_without_id():
    with patch('integrations.radarr_client.httpx.AsyncClient') as MockAsyncClient:
        movies_resp = make_response([{"title": "A"}])
        movie_resp = make_response({"title": "B"})
        client = setup_async_client(MockAsyncClient, {"get": movies_resp})

        rc = RadarrClient("http://localhost:7878", "secret")
        all_movies = await rc.get_movies()
        assert all_movies == [{"title": "A"}]
        client.get.assert_called_with("/api/v3/movie")

        client.get.return_value = movie_resp
        one = await rc.get_movies(42)
        assert one == {"title": "B"}
        client.get.assert_called_with("/api/v3/movie/42")


@pytest.mark.asyncio
async def test_lookup_and_add_update_delete_movie():
    with patch('integrations.radarr_client.httpx.AsyncClient') as MockAsyncClient:
        lookup_resp = make_response([{"tmdbId": 603, "title": "The Matrix"}])
        add_resp = make_response({"id": 101})
        update_resp = make_response({"id": 101, "monitored": False})
        delete_resp = make_response(None)
        client = setup_async_client(MockAsyncClient, {"get": lookup_resp, "post": add_resp, "put": update_resp, "delete": delete_resp})

        rc = RadarrClient("http://localhost:7878", "secret")
        results = await rc.lookup("Matrix")
        assert results[0]["tmdbId"] == 603
        client.get.assert_called_with("/api/v3/movie/lookup", params={"term": "Matrix"})

        created = await rc.add_movie(
            tmdb_id=603,
            quality_profile_id=1,
            root_folder_path="/movies",
            monitored=True,
            search_now=True,
        )
        assert created == {"id": 101}
        client.post.assert_called_with(
            "/api/v3/movie",
            json={
                "tmdbId": 603,
                "qualityProfileId": 1,
                "rootFolderPath": "/movies",
                "monitored": True,
                "minimumAvailability": "announced",
                "addOptions": {"searchForMovie": True},
            },
        )

        updated = await rc.update_movie(101, monitored=False)
        assert updated["monitored"] is False
        client.put.assert_called_with("/api/v3/movie/101", json={"monitored": False})

        await rc.delete_movie(101, delete_files=True, add_import_list_exclusion=True)
        client.delete.assert_called_with(
            "/api/v3/movie/101",
            params={"deleteFiles": True, "addImportListExclusion": True},
        )


@pytest.mark.asyncio
async def test_commands_and_queue():
    with patch('integrations.radarr_client.httpx.AsyncClient') as MockAsyncClient:
        cmd_resp = make_response({"name": "MoviesSearch"})
        queue_resp = make_response({"page": 1, "records": []})
        client = setup_async_client(MockAsyncClient, {"post": cmd_resp, "get": queue_resp})

        rc = RadarrClient("http://localhost:7878", "secret")
        cmd = await rc.search_movie(101)
        assert cmd["name"] == "MoviesSearch"
        client.post.assert_called_with("/api/v3/command", json={"name": "MoviesSearch", "movieIds": [101]})

        missing = await rc.search_missing()
        client.post.assert_called_with("/api/v3/command", json={"name": "MissingMovieSearch"})

        cutoff = await rc.search_cutoff()
        client.post.assert_called_with("/api/v3/command", json={"name": "CutOffUnmetMoviesSearch"})

        queue = await rc.get_queue()
        assert queue["page"] == 1
        client.get.assert_called_with("/api/v3/queue")


@pytest.mark.asyncio
async def test_history_params_and_blacklist_operations():
    with patch('integrations.radarr_client.httpx.AsyncClient') as MockAsyncClient:
        history_resp = make_response({"page": 1, "records": []})
        list_resp = make_response({"page": 1, "records": []})
        ok_resp = make_response(None)
        client = setup_async_client(MockAsyncClient, {"get": history_resp, "delete": ok_resp})

        rc = RadarrClient("http://localhost:7878", "secret")
        # history default
        _ = await rc.get_history()
        client.get.assert_called_with("/api/v3/history", params={"page": 1, "pageSize": 20})

        # history with params
        _ = await rc.get_history(movie_id=5, page=2, page_size=10, event_type="grabbed")
        client.get.assert_called_with(
            "/api/v3/history",
            params={"page": 2, "pageSize": 10, "movieId": 5, "eventType": "grabbed"},
        )

        # blacklist list
        client.get.return_value = list_resp
        _ = await rc.get_blacklist(page=3, page_size=50)
        client.get.assert_called_with("/api/v3/blocklist", params={"page": 3, "pageSize": 50})

        # delete item
        await rc.delete_blacklist_item(99)
        client.delete.assert_called_with("/api/v3/blocklist/99")

        # clear all
        await rc.clear_blacklist()
        client.delete.assert_called_with("/api/v3/blocklist")


@pytest.mark.asyncio
async def test_indexers_and_download_clients_and_notifications():
    with patch('integrations.radarr_client.httpx.AsyncClient') as MockAsyncClient:
        get_resp = make_response([{"id": 1}])
        test_resp = make_response({"ok": True})
        client = setup_async_client(MockAsyncClient, {"get": get_resp, "post": test_resp})

        rc = RadarrClient("http://localhost:7878", "secret")
        _ = await rc.get_indexers()
        client.get.assert_called_with("/api/v3/indexer")
        _ = await rc.test_indexer(1)
        client.post.assert_called_with("/api/v3/indexer/test", json={"id": 1})

        _ = await rc.get_download_clients()
        client.get.assert_called_with("/api/v3/downloadclient")
        _ = await rc.test_download_client(2)
        client.post.assert_called_with("/api/v3/downloadclient/test", json={"id": 2})

        _ = await rc.get_notifications()
        client.get.assert_called_with("/api/v3/notification")


@pytest.mark.asyncio
async def test_tags_create_and_delete():
    with patch('integrations.radarr_client.httpx.AsyncClient') as MockAsyncClient:
        get_resp = make_response([{"id": 1, "label": "X"}])
        create_resp = make_response({"id": 2, "label": "Y"})
        ok_resp = make_response(None)
        client = setup_async_client(MockAsyncClient, {"get": get_resp, "post": create_resp, "delete": ok_resp})

        rc = RadarrClient("http://localhost:7878", "secret")
        _ = await rc.get_tags()
        client.get.assert_called_with("/api/v3/tag")

        _ = await rc.create_tag("New")
        client.post.assert_called_with("/api/v3/tag", json={"label": "New"})

        await rc.delete_tag(2)
        client.delete.assert_called_with("/api/v3/tag/2")


@pytest.mark.asyncio
async def test_calendar_and_wanted_cutoff_params():
    with patch('integrations.radarr_client.httpx.AsyncClient') as MockAsyncClient:
        cal_resp = make_response([])
        wanted_resp = make_response({"page": 2})
        cutoff_resp = make_response({"page": 3})
        client = setup_async_client(MockAsyncClient, {"get": cal_resp})

        rc = RadarrClient("http://localhost:7878", "secret")
        _ = await rc.get_calendar(start_date="2024-01-01", end_date="2024-01-31")
        client.get.assert_called_with("/api/v3/calendar", params={"start": "2024-01-01", "end": "2024-01-31"})

        client.get.return_value = wanted_resp
        _ = await rc.get_wanted(page=2, page_size=10, sort_key="title", sort_dir="asc")
        client.get.assert_called_with(
            "/api/v3/wanted/missing",
            params={"page": 2, "pageSize": 10, "sortKey": "title", "sortDir": "asc"},
        )

        client.get.return_value = cutoff_resp
        _ = await rc.get_cutoff(page=3, page_size=5, sort_key="id", sort_dir="desc")
        client.get.assert_called_with(
            "/api/v3/wanted/cutoff",
            params={"page": 3, "pageSize": 5, "sortKey": "id", "sortDir": "desc"},
        )


@pytest.mark.asyncio
async def test_metadata_and_naming_and_ui_config():
    with patch('integrations.radarr_client.httpx.AsyncClient') as MockAsyncClient:
        meta_resp = make_response([{"id": 1}])
        get_conf_resp = make_response({"foo": "bar"})
        put_resp = make_response({"ok": True})
        client = setup_async_client(MockAsyncClient, {"get": meta_resp, "put": put_resp})

        rc = RadarrClient("http://localhost:7878", "secret")
        _ = await rc.get_metadata_profiles()
        client.get.assert_called_with("/api/v3/metadataprofile")

        # naming config
        client.get.return_value = get_conf_resp
        _ = await rc.get_naming_config()
        client.get.assert_called_with("/api/v3/config/naming")

        _ = await rc.update_naming_config({"format": "X"})
        client.put.assert_called_with("/api/v3/config/naming", json={"format": "X"})

        # UI config
        client.get.return_value = get_conf_resp
        _ = await rc.get_ui_config()
        client.get.assert_called_with("/api/v3/config/ui")

        _ = await rc.update_ui_config({"language": "en"})
        client.put.assert_called_with("/api/v3/config/ui", json={"language": "en"})


@pytest.mark.asyncio
async def test_delete_queue_item_param_and_close_noop():
    with patch('integrations.radarr_client.httpx.AsyncClient') as MockAsyncClient:
        ok_resp = make_response(None)
        client = setup_async_client(MockAsyncClient, {"delete": ok_resp})

        rc = RadarrClient("http://localhost:7878", "secret")
        await rc.delete_queue_item(77, blacklist=True)
        client.delete.assert_called_with("/api/v3/queue/77", params={"blacklist": True})

        # close should not raise even if no underlying client exists
        await rc.close()


@pytest.mark.asyncio
async def test_close_handles_event_loop_closed():
    rc = RadarrClient("http://localhost:7878", "secret")
    # Simulate a stored client that raises RuntimeError on close
    ac = AsyncMock()
    ac.aclose.side_effect = RuntimeError("Event loop is closed")
    rc._client = ac
    # Should not raise
    await rc.close()


