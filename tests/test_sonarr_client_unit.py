import pytest
from unittest.mock import patch, Mock, AsyncMock

from integrations.sonarr_client import SonarrClient


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
    for method_name, resp in response_by_method.items():
        getattr(client, method_name).return_value = resp
    return client


@pytest.mark.asyncio
async def test_constructor_validation_and_close():
    with pytest.raises(ValueError):
        SonarrClient("", "x")
    with pytest.raises(ValueError):
        SonarrClient("http://localhost:8989", "")
    with pytest.raises(ValueError):
        SonarrClient("localhost:8989", "x")

    # Ensure close delegates to underlying client
    with patch('integrations.sonarr_client.httpx.AsyncClient') as MockAsyncClient:
        # With per-call clients, close is a no-op; just ensure it doesn't raise
        _ = setup_async_client(MockAsyncClient, {})
        s = SonarrClient("http://localhost:8989", "k")
        await s.close()


@pytest.mark.asyncio
async def test_system_status_health_disk_space():
    with patch('integrations.sonarr_client.httpx.AsyncClient') as MockAsyncClient:
        c = setup_async_client(MockAsyncClient, {"get": make_response({"version": "4"})})
        s = SonarrClient("http://localhost:8989", "k")
        out = await s.system_status()
        assert out["version"] == "4"
        c.get.assert_called_with("/api/v3/system/status")

        c.get.return_value = make_response([])
        out = await s.health()
        c.get.assert_called_with("/api/v3/health")

        out = await s.disk_space()
        c.get.assert_called_with("/api/v3/diskspace")


@pytest.mark.asyncio
async def test_quality_profiles_helpers_and_root_folders():
    with patch('integrations.sonarr_client.httpx.AsyncClient') as MockAsyncClient:
        c = setup_async_client(MockAsyncClient, {"get": make_response([{"id": 1, "name": "HD-1080p"}, {"id": 2}])})
        s = SonarrClient("http://localhost:8989", "k")
        profiles = await s.quality_profiles()
        assert profiles[0]["name"] == "HD-1080p"
        helper = await s.get_quality_profile_names()
        assert helper == [{"id": 1, "name": "HD-1080p"}]

        c.get.return_value = make_response([{"path": "/tv"}, {"path": None}])
        folders = await s.root_folders()
        assert isinstance(folders, list)
        paths = await s.get_root_folder_paths()
        assert paths == ["/tv"]


@pytest.mark.asyncio
async def test_get_series_and_lookup():
    with patch('integrations.sonarr_client.httpx.AsyncClient') as MockAsyncClient:
        c = setup_async_client(MockAsyncClient, {"get": make_response([{"id": 10}, {"id": 11}])})
        s = SonarrClient("http://localhost:8989", "k")
        all_series = await s.get_series()
        c.get.assert_called_with("/api/v3/series")
        assert len(all_series) == 2

        c.get.return_value = make_response({"id": 10})
        one = await s.get_series(10)
        c.get.assert_called_with("/api/v3/series/10")
        assert one["id"] == 10

        c.get.return_value = make_response([{"title": "Breaking Bad"}])
        res = await s.lookup("Breaking")
        c.get.assert_called_with("/api/v3/series/lookup", params={"term": "Breaking"})
        assert res and res[0]["title"] == "Breaking Bad"


@pytest.mark.asyncio
async def test_add_series_validation_and_payload_building():
    with patch('integrations.sonarr_client.httpx.AsyncClient') as MockAsyncClient:
        c = setup_async_client(MockAsyncClient, {})
        # quality profiles, root folders, lookup (validate), lookup (payload)
        c.get.side_effect = [
            make_response([{"id": 1}]),  # quality_profiles
            make_response([{"path": "/tv"}]),  # root_folders
            make_response([{"title": "Show", "titleSlug": "show", "overview": "..."}]),  # lookup (validate)
            make_response([{"title": "Show", "titleSlug": "show", "overview": "..."}]),  # lookup (payload)
        ]
        c.post.return_value = make_response({"id": 123, "title": "Show"})

        s = SonarrClient("http://localhost:8989", "k")
        series = await s.add_series(
            tvdb_id=121361,
            quality_profile_id=1,
            root_folder_path="/tv",
            monitored=True,
            search_for_missing=True,
            season_folder=True,
        )
        assert series["id"] == 123
        c.post.assert_called_with(
            "/api/v3/series",
            json={
                "tvdbId": 121361,
                "title": "Show",
                "titleSlug": "show",
                "overview": "...",
                "qualityProfileId": 1,
                "rootFolderPath": "/tv",
                "monitored": True,
                "seasonFolder": True,
                "addOptions": {
                    "searchForMissingEpisodes": True,
                    "ignoreEpisodesWithFiles": False,
                    "ignoreEpisodesWithoutFiles": False,
                    "addAndSearchForMissing": True,
                },
                "monitorNewEpisodes": True,
                "useAlternateTitlesForSearch": False,
                "addOnly": False,
                "seasons": [],
                "episodes": [],
            },
        )


@pytest.mark.asyncio
async def test_update_and_delete_series():
    with patch('integrations.sonarr_client.httpx.AsyncClient') as MockAsyncClient:
        c = setup_async_client(MockAsyncClient, {"put": make_response({"id": 1, "monitored": False}), "delete": make_response(None)})

        s = SonarrClient("http://localhost:8989", "k")
        updated = await s.update_series(1, monitored=False)
        assert updated["monitored"] is False
        c.put.assert_called_with("/api/v3/series/1", json={"monitored": False})

        await s.delete_series(1, delete_files=True, add_import_list_exclusion=True)
        c.delete.assert_called_with(
            "/api/v3/series/1",
            params={"deleteFiles": True, "addImportListExclusion": True},
        )


@pytest.mark.asyncio
async def test_episodes_and_monitoring_helpers():
    with patch('integrations.sonarr_client.httpx.AsyncClient') as MockAsyncClient:
        c = setup_async_client(MockAsyncClient, {})
        c.get.side_effect = [
            # monitor_episodes -> get_episodes by ids
            make_response([{"id": 1}, {"id": 2}]),
            # monitor_episodes_by_season -> get_episodes by series
            make_response([{"id": 1, "seasonNumber": 1}, {"id": 2, "seasonNumber": 2}]),
            # monitor_episodes_by_season -> monitor_episodes -> get_episodes by ids
            make_response([{"id": 1, "seasonNumber": 1}, {"id": 2, "seasonNumber": 2}]),
            # monitor_episodes_by_air_date -> get_episodes by series
            make_response([{"id": 1, "airDateUtc": "2024-01-10"}, {"id": 2, "airDateUtc": "2024-03-01"}]),
            # monitor_episodes_by_air_date -> monitor_episodes -> get_episodes by ids
            make_response([{"id": 1, "airDateUtc": "2024-01-10"}]),
        ]
        c.put.return_value = make_response([{"id": 1, "monitored": True}, {"id": 2, "monitored": True}])

        s = SonarrClient("http://localhost:8989", "k")
        # monitor_episodes
        out = await s.monitor_episodes([1, 2], True)
        assert all(ep["monitored"] for ep in out)
        c.get.assert_any_call("/api/v3/episode", params={"episodeIds": [1, 2]})
        c.put.assert_called_with("/api/v3/episode", json=[{"id": 1, "monitored": True}, {"id": 2, "monitored": True}])

        # monitor_episodes_by_season
        out = await s.monitor_episodes_by_season(10, 1, True)
        c.get.assert_any_call("/api/v3/episode", params={"seriesId": 10})

        # monitor_episodes_by_air_date
        out = await s.monitor_episodes_by_air_date(10, "2024-01-01", "2024-02-01", False)
        c.get.assert_any_call("/api/v3/episode", params={"seriesId": 10})


@pytest.mark.asyncio
async def test_season_details_and_helpers():
    with patch('integrations.sonarr_client.httpx.AsyncClient') as MockAsyncClient:
        c = setup_async_client(MockAsyncClient, {})
        c.get.side_effect = [
            make_response([{"seasonNumber": 1, "monitored": True}]),  # get_seasons
            make_response({"id": 1, "monitored": True}),  # get_season_details (first)
            make_response({"id": 1, "monitored": True}),  # monitor_season: get season details
            make_response({"id": 1, "monitored": True}),  # get_season_summary: get season details
            make_response([{"id": 1, "seasonNumber": 1}, {"id": 2, "seasonNumber": 1}]),  # get_episodes for summary
        ]
        c.put.return_value = make_response({"id": 1, "monitored": False})

        s = SonarrClient("http://localhost:8989", "k")
        seasons = await s.get_seasons(10)
        assert seasons[0]["seasonNumber"] == 1

        details = await s.get_season_details(10, 1)
        assert details["monitored"] is True

        out = await s.monitor_season(10, 1, False)
        assert out["monitored"] is False

        summary = await s.get_season_summary(10, 1)
        assert summary["season_number"] == 1


@pytest.mark.asyncio
async def test_search_commands():
    with patch('integrations.sonarr_client.httpx.AsyncClient') as MockAsyncClient:
        c = setup_async_client(MockAsyncClient, {"get": make_response([{"id": 1, "seasonNumber": 1}, {"id": 2, "seasonNumber": 2}]), "post": make_response({"ok": True})})

        s = SonarrClient("http://localhost:8989", "k")
        _ = await s.search_series(55)
        c.post.assert_called_with("/api/v3/command", json={"name": "SeriesSearch", "seriesId": 55})

        _ = await s.search_episode(99)
        c.post.assert_called_with("/api/v3/command", json={"name": "EpisodeSearch", "episodeIds": [99]})

        _ = await s.search_episodes([1, 2])
        c.post.assert_called_with("/api/v3/command", json={"name": "EpisodeSearch", "episodeIds": [1, 2]})

        _ = await s.search_season(55, 1)
        # Should have posted EpisodeSearch based on season episodes
        c.post.assert_called_with("/api/v3/command", json={"name": "EpisodeSearch", "episodeIds": [1]})

        _ = await s.search_missing()
        c.post.assert_called_with("/api/v3/command", json={"name": "MissingEpisodeSearch"})


@pytest.mark.asyncio
async def test_commands_queue_history_importlists_notifications_tags_calendar_wanted_cutoff():
    with patch('integrations.sonarr_client.httpx.AsyncClient') as MockAsyncClient:
        c = setup_async_client(MockAsyncClient, {})
        c.get.side_effect = [
            make_response([]),  # get_commands
            make_response({"page": 1}),  # get_queue
            make_response({"page": 1}),  # get_history
            make_response([]),  # get_import_lists
            make_response([]),  # get_notifications
            make_response([]),  # get_tags
            make_response([]),  # get_calendar
            make_response({"page": 2}),  # get_wanted
            make_response({"page": 3}),  # get_cutoff
        ]
        c.post.return_value = make_response({"ok": True})
        c.delete.return_value = make_response(None)

        s = SonarrClient("http://localhost:8989", "k")
        _ = await s.get_commands()
        c.get.assert_called_with("/api/v3/command")

        _ = await s.get_queue()
        c.get.assert_called_with("/api/v3/queue")

        _ = await s.get_history(series_id=1, episode_id=2, page=1, page_size=20)
        c.get.assert_called_with("/api/v3/history", params={"page": 1, "pageSize": 20, "seriesId": 1, "episodeId": 2})

        _ = await s.get_import_lists()
        c.get.assert_called_with("/api/v3/importlist")

        _ = await s.test_import_list(10)
        c.post.assert_called_with("/api/v3/importlist/test", json={"id": 10})

        _ = await s.get_notifications()
        c.get.assert_called_with("/api/v3/notification")

        _ = await s.get_tags()
        c.get.assert_called_with("/api/v3/tag")

        _ = await s.create_tag("New")
        c.post.assert_called_with("/api/v3/tag", json={"label": "New"})

        await s.delete_tag(2)
        c.delete.assert_called_with("/api/v3/tag/2")

        _ = await s.get_calendar(start_date="2024-01-01", end_date="2024-01-31")
        c.get.assert_called_with("/api/v3/calendar", params={"start": "2024-01-01", "end": "2024-01-31"})

        _ = await s.get_wanted(page=2, page_size=10, sort_key="airDateUtc", sort_dir="asc")
        c.get.assert_called_with("/api/v3/wanted/missing", params={"page": 2, "pageSize": 10, "sortKey": "airDateUtc", "sortDir": "asc"})

        _ = await s.get_cutoff(page=3, page_size=5, sort_key="airDateUtc", sort_dir="desc")
        c.get.assert_called_with("/api/v3/wanted/cutoff", params={"page": 3, "pageSize": 5, "sortKey": "airDateUtc", "sortDir": "desc"})
