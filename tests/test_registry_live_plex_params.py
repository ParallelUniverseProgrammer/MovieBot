import os
import pytest
from pathlib import Path
import asyncio

from bot.tools.registry import build_openai_tools_and_registry


@pytest.mark.integration
class TestRegistryLivePlexParams:
    @pytest.fixture(scope="class")
    def registry(self):
        project_root = Path(__file__).parent.parent
        _, reg = build_openai_tools_and_registry(project_root)
        return reg

    @pytest.mark.asyncio
    async def test_all_tools_defaults(self, registry, integration_requirements_met):
        tool_names = [
            "get_plex_library_sections",
            "get_plex_recently_added",
            "get_plex_on_deck",
            "get_plex_continue_watching",
            "get_plex_unwatched",
            "get_plex_collections",
            "get_plex_playlists",
            "get_plex_playback_status",
        ]
        for name in tool_names:
            out = await registry.get(name)({})
            assert isinstance(out, dict)

    @pytest.mark.asyncio
    async def test_response_levels(self, registry, integration_requirements_met):
        response_levels = ["minimal", "compact", "standard", "detailed"]
        # Recently added (movie + show)
        for level in response_levels:
            out_m = await registry.get("get_plex_recently_added")({"section_type": "movie", "limit": 3, "response_level": level})
            out_s = await registry.get("get_plex_recently_added")({"section_type": "show", "limit": 3, "response_level": level})
            assert isinstance(out_m, dict) and isinstance(out_s, dict)
            assert out_m.get("response_level") == level
            assert out_s.get("response_level") == level
            # Validate shape roughly matches level
            for out in (out_m, out_s):
                items = out.get("items") or []
                if not items:
                    continue
                item = items[0]
                if level == "minimal":
                    for k in ("title", "ratingKey", "type"):
                        assert k in item
                if level == "compact":
                    for k in ("title", "ratingKey", "type", "year"):
                        assert k in item
                if level in ("standard", "detailed"):
                    for k in ("title", "ratingKey", "type", "genres"):
                        assert k in item

        # On deck / continue watching
        for level in response_levels:
            on_deck = await registry.get("get_plex_on_deck")({"limit": 3, "response_level": level})
            cont = await registry.get("get_plex_continue_watching")({"limit": 3, "response_level": level})
            assert on_deck.get("response_level") == level
            assert cont.get("response_level") == level

        # Unwatched and collections
        for level in response_levels:
            uw = await registry.get("get_plex_unwatched")({"section_type": "movie", "limit": 3, "response_level": level})
            col = await registry.get("get_plex_collections")({"section_type": "movie", "limit": 3, "response_level": level})
            assert uw.get("response_level") == level
            assert col.get("response_level") == level

        # Playlists
        for level in response_levels:
            pls = await registry.get("get_plex_playlists")({"limit": 3, "response_level": level})
            assert pls.get("response_level") == level

        # Playback status
        for level in response_levels:
            status = await registry.get("get_plex_playback_status")({"response_level": level})
            assert status.get("response_level") == level

    @pytest.mark.asyncio
    async def test_item_specific_tools(self, registry, integration_requirements_met):
        # Pick an item from recently added and exercise item tools across response levels
        recent = await registry.get("get_plex_recently_added")({"limit": 1, "response_level": "standard"})
        items = recent.get("items") or []
        if not items:
            pytest.skip("No recent items available for item-specific tests")
        rating_key = items[0].get("ratingKey")
        assert rating_key is not None

        levels = ["minimal", "compact", "standard", "detailed"]
        for level in levels:
            details = await registry.get("get_plex_item_details")({"rating_key": rating_key, "response_level": level})
            assert isinstance(details, dict)
            assert details.get("response_level") == level
            item = details.get("item") or {}
            if level == "minimal":
                for k in ("title", "ratingKey", "type"):
                    assert k in item
            if level == "compact":
                for k in ("title", "ratingKey", "type", "year"):
                    assert k in item
            if level in ("standard", "detailed"):
                for k in ("title", "ratingKey", "type", "genres"):
                    assert k in item

            sim = await registry.get("get_plex_similar_items")({"rating_key": rating_key, "limit": 5, "response_level": level})
            assert isinstance(sim, dict)
            assert sim.get("response_level") == level

        extras = await registry.get("get_plex_extras")({"rating_key": rating_key})
        assert isinstance(extras, dict)
        hist = await registry.get("get_plex_watch_history")({"rating_key": rating_key, "limit": 5})
        assert isinstance(hist, dict)

    @pytest.mark.asyncio
    async def test_search_tool_across_levels_and_filters(self, registry, integration_requirements_met):
        # Query might be empty; tool should support both empty and populated queries
        for query in ["", "The"]:
            for level in ["compact", "standard", "detailed"]:
                out = await registry.get("search_plex")({
                    "query": query,
                    "limit": 5,
                    "response_level": level,
                    # Filters only meaningful for standard/detailed
                    "filters": {
                        "year_min": 1900,
                        "year_max": 2100,
                        "rating_min": 0,
                        "rating_max": 10,
                        "sort_by": "title",
                        "sort_order": "asc",
                    }
                })
                assert isinstance(out, dict)
                assert out.get("response_level") == level
                items = out.get("items") or []
                assert isinstance(items, list)
                if not items:
                    continue
                sample = items[0]
                if level == "compact":
                    for k in ("title", "ratingKey", "type", "year"):
                        assert k in sample
                if level in ("standard", "detailed"):
                    for k in ("title", "ratingKey", "type", "genres"):
                        assert k in sample

    @pytest.mark.asyncio
    async def test_limits_and_edges(self, registry, integration_requirements_met):
        # Zero and large limits should be handled
        zero = await registry.get("get_plex_recently_added")({"limit": 0})
        assert isinstance(zero, dict)
        assert zero.get("total_found") == 0
        large = await registry.get("get_plex_recently_added")({"limit": 200})
        assert isinstance(large, dict)
        assert large.get("total_found") <= 200

    @pytest.mark.asyncio
    async def test_library_sections_sensible(self, registry, integration_requirements_met):
        sections = await registry.get("get_plex_library_sections")({})
        assert isinstance(sections, dict)
        secs = sections.get("sections") or {}
        assert isinstance(secs, dict)
        # Must contain at least something and have reasonable fields
        if secs:
            first = next(iter(secs.values()))
            assert "type" in first and "count" in first and "section_id" in first

    @pytest.mark.asyncio
    async def test_set_rating_opt_in(self, registry, integration_requirements_met):
        if not os.getenv("PLEX_TEST_MUTATIONS"):
            pytest.skip("Set rating test skipped (set PLEX_TEST_MUTATIONS=1 to enable)")
        recent = await registry.get("get_plex_recently_added")({"limit": 1})
        items = recent.get("items") or []
        if not items:
            pytest.skip("No items available to rate")
        rating_key = items[0].get("ratingKey")
        ok = await registry.get("set_plex_rating")({"rating_key": int(rating_key), "rating": 5})
        assert isinstance(ok, dict)
        assert ok.get("ok") is True
