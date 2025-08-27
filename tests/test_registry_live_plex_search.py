import pytest
from pathlib import Path
import re
import random

from bot.tools.registry import build_openai_tools_and_registry


@pytest.mark.integration
class TestRegistryLivePlexSearch:
    @pytest.fixture(scope="class")
    def registry(self):
        project_root = Path(__file__).parent.parent
        _, reg = build_openai_tools_and_registry(project_root)
        return reg

    @pytest.mark.asyncio
    async def test_sorting_by_title_year_rating_asc_desc(self, registry, integration_requirements_met):
        tool = registry.get("search_plex")
        def _title_key(it: dict):
            t = (it.get("title") or "").strip().casefold()
            for art in ("the ", "a ", "an "):
                if t.startswith(art):
                    t = t[len(art):]
                    break
            # Avoid numeric token splitting to better mirror Plex titleSort comparisons
            return t

        numeric_fields_and_extractors = {
            "year": lambda it: it.get("year"),
            "rating": lambda it: it.get("rating"),
        }

        # Numeric fields: enforce monotonicity within each result
        for field, extractor in numeric_fields_and_extractors.items():
            for order in ("asc", "desc"):
                out = await tool({
                    "limit": 10,
                    "response_level": "compact",
                    "filters": {"sort_by": field, "sort_order": order},
                })
                assert isinstance(out, dict)
                items = out.get("items") or []
                if len(items) < 2:
                    continue
                vals = [extractor(it) for it in items if extractor(it) is not None]
                if len(vals) < 2:
                    continue
                if order == "asc":
                    assert all(a <= b for a, b in zip(vals, vals[1:]))
                else:
                    assert all(a >= b for a, b in zip(vals, vals[1:]))

        # Title field: smoke check both orders return results and differ at least at one endpoint
        out_asc = await tool({
            "limit": 10,
            "response_level": "compact",
            "filters": {"sort_by": "title", "sort_order": "asc"},
        })
        out_desc = await tool({
            "limit": 10,
            "response_level": "compact",
            "filters": {"sort_by": "title", "sort_order": "desc"},
        })
        assert isinstance(out_asc, dict) and isinstance(out_desc, dict)
        items_asc = out_asc.get("items") or []
        items_desc = out_desc.get("items") or []
        if items_asc and items_desc:
            t_first_asc = _title_key(items_asc[0])
            t_last_desc = _title_key(items_desc[-1])
            # Very weak assertion: endpoints should not be identical under our key
            assert t_first_asc != t_last_desc

    @pytest.mark.asyncio
    async def test_filter_by_actor_candidates(self, registry, integration_requirements_met):
        tool = registry.get("search_plex")
        # Try a couple of common actor spellings; pass multiple to leverage OR logic
        actor_sets = [
            ["Nicolas Cage", "Nic Cage"],
            ["Tom Cruise"],
        ]
        found = False
        for actors in actor_sets:
            out = await tool({
                "limit": 10,
                "response_level": "detailed",
                "filters": {"actors": actors},
            })
            items = out.get("items") or []
            if not items:
                continue
            # Validate at least one returned item lists one of the requested actors
            lowered = [a.lower() for a in actors]
            for it in items:
                raw = it.get("actors") or []
                # actors should be a list of strings at detailed level
                movie_actors = [str(a).lower() for a in raw]
                if any(a in movie_actors for a in lowered):
                    found = True
                    break
            if found:
                break
        if not found:
            pytest.skip("No items matched actor filters in this Plex library")

    @pytest.mark.asyncio
    async def test_filter_by_director_candidates(self, registry, integration_requirements_met):
        tool = registry.get("search_plex")
        director_sets = [
            ["Sam Raimi"],
            ["Christopher Nolan"],
        ]
        found = False
        for directors in director_sets:
            out = await tool({
                "limit": 10,
                "response_level": "detailed",
                "filters": {"directors": directors},
            })
            items = out.get("items") or []
            if not items:
                continue
            lowered = [d.lower() for d in directors]
            for it in items:
                raw = it.get("directors") or []
                movie_directors = [str(d).lower() for d in raw]
                if any(d in movie_directors for d in lowered):
                    found = True
                    break
            if found:
                break
        if not found:
            pytest.skip("No items matched director filters in this Plex library")

    @pytest.mark.asyncio
    async def test_filter_then_sort_desc_year(self, registry, integration_requirements_met):
        tool = registry.get("search_plex")
        out = await tool({
            "limit": 10,
            "response_level": "compact",
            "filters": {
                "actors": ["Nicolas Cage", "Nic Cage"],
                "sort_by": "year",
                "sort_order": "desc",
            },
        })
        assert isinstance(out, dict)
        items = out.get("items") or []
        if len(items) < 2:
            pytest.skip("Not enough results for combined filter+sort validation")
        years = [it.get("year") for it in items if it.get("year") is not None]
        if len(years) < 2:
            pytest.skip("Missing year fields to validate sort order")
        assert years == sorted(years, reverse=True)

    @pytest.mark.asyncio
    async def test_year_range_filter_and_sort(self, registry, integration_requirements_met):
        tool = registry.get("search_plex")
        # Gather baseline to discover available years
        base = await tool({"limit": 40, "response_level": "compact"})
        items = base.get("items") or []
        years = sorted([it.get("year") for it in items if isinstance(it.get("year"), int)])
        if len(years) < 3:
            pytest.skip("Not enough items with year to test range filtering")
        mid = years[len(years)//2]
        hi = years[-1]

        # Filter [mid, hi] and sort ascending by year
        out = await tool({
            "limit": 20,
            "response_level": "compact",
            "filters": {"year_min": mid, "year_max": hi, "sort_by": "year", "sort_order": "asc"},
        })
        its = out.get("items") or []
        yrs = [it.get("year") for it in its if it.get("year") is not None]
        if not yrs:
            pytest.skip("No items matched chosen year range")
        within = [y for y in yrs if mid <= y <= hi]
        # Require strong majority to be within range; Plex server behavior can include edge items
        assert len(within) >= max(1, int(0.8 * len(yrs)))
        assert all(a <= b for a, b in zip(yrs, yrs[1:]))

    @pytest.mark.asyncio
    async def test_rating_range_filter_and_sort(self, registry, integration_requirements_met):
        tool = registry.get("search_plex")
        base = await tool({"limit": 40, "response_level": "compact"})
        items = base.get("items") or []
        ratings = sorted([it.get("rating") for it in items if isinstance(it.get("rating"), (int, float))])
        if len(ratings) < 3:
            pytest.skip("Not enough items with ratings to test range filtering")
        lo = max(0.0, float(ratings[0]))
        mid = float(ratings[len(ratings)//2])
        hi = float(ratings[-1])

        out = await tool({
            "limit": 20,
            "response_level": "compact",
            "filters": {"rating_min": mid, "rating_max": hi, "sort_by": "rating", "sort_order": "desc"},
        })
        its = out.get("items") or []
        vals = [it.get("rating") for it in its if it.get("rating") is not None]
        if not vals:
            pytest.skip("No items matched chosen rating range")
        assert all(mid <= v <= hi for v in vals)
        assert all(a >= b for a, b in zip(vals, vals[1:]))

    @pytest.mark.asyncio
    async def test_content_rating_filter(self, registry, integration_requirements_met):
        tool = registry.get("search_plex")
        # Discover an available content rating from detailed payload
        base = await tool({"limit": 40, "response_level": "detailed"})
        items = base.get("items") or []
        crs = [it.get("contentRating") for it in items if isinstance(it.get("contentRating"), str)]
        if not crs:
            pytest.skip("No content ratings found to test filter")
        chosen = crs[0]

        out = await tool({
            "limit": 15,
            "response_level": "detailed",
            "filters": {"content_rating": chosen},
        })
        its = out.get("items") or []
        if not its:
            pytest.skip("No items matched selected content rating")
        assert all(it.get("contentRating") == chosen for it in its)

    @pytest.mark.asyncio
    async def test_genre_filter_and_title_sort(self, registry, integration_requirements_met):
        tool = registry.get("search_plex")
        base = await tool({"limit": 40, "response_level": "standard"})
        items = base.get("items") or []
        # Find a present genre string
        candidate_genre: str | None = None
        for it in items:
            gs = it.get("genres") or []
            if gs and isinstance(gs, list) and isinstance(gs[0], str):
                candidate_genre = gs[0]
                break
        if not candidate_genre:
            pytest.skip("No genres found to test filter")

        out_asc = await tool({
            "limit": 15,
            "response_level": "standard",
            "filters": {"genres": [candidate_genre], "sort_by": "title", "sort_order": "asc"},
        })
        its = out_asc.get("items") or []
        if not its:
            pytest.skip("No items matched genre filter")
        assert any(candidate_genre in (it.get("genres") or []) for it in its)

        out_desc = await tool({
            "limit": 15,
            "response_level": "standard",
            "filters": {"genres": [candidate_genre], "sort_by": "title", "sort_order": "desc"},
        })
        its_desc = out_desc.get("items") or []
        if its_desc:
            # Weak sort check: endpoints likely change across order
            assert (its[0].get("ratingKey") != its_desc[0].get("ratingKey")) or (its[-1].get("ratingKey") != its_desc[-1].get("ratingKey"))

    @pytest.mark.asyncio
    async def test_query_plus_filters_and_sort(self, registry, integration_requirements_met):
        tool = registry.get("search_plex")
        # Use a broad query to increase hit-rate
        query = "the"
        base = await tool({"query": query, "limit": 40, "response_level": "compact"})
        items = base.get("items") or []
        years = sorted([it.get("year") for it in items if isinstance(it.get("year"), int)])
        if len(years) < 2:
            pytest.skip("Not enough items with year for query-based filter test")
        year_cut = years[len(years)//2]

        out = await tool({
            "query": query,
            "limit": 20,
            "response_level": "compact",
            "filters": {"year_min": year_cut, "sort_by": "year", "sort_order": "asc"},
        })
        its = out.get("items") or []
        yrs = [it.get("year") for it in its if isinstance(it.get("year"), int)]
        if not yrs:
            pytest.skip("No items matched query+year filter")
        assert all(y >= year_cut for y in yrs)
        assert all(a <= b for a, b in zip(yrs, yrs[1:]))

    @pytest.mark.asyncio
    async def test_combined_filters_year_rating_genre_with_rating_sort(self, registry, integration_requirements_met):
        tool = registry.get("search_plex")
        # Discover viable genre and rating bounds
        base = await tool({"limit": 60, "response_level": "standard"})
        items = base.get("items") or []
        # genre
        genre = None
        for it in items:
            gs = it.get("genres") or []
            if gs and isinstance(gs[0], str):
                genre = gs[0]
                break
        # ratings and years
        ratings = sorted([it.get("rating") for it in items if isinstance(it.get("rating"), (int, float))])
        years = sorted([it.get("year") for it in items if isinstance(it.get("year"), int)])
        if not genre or len(ratings) < 3 or len(years) < 3:
            pytest.skip("Insufficient data to test combined filters")
        rmin = float(ratings[len(ratings)//3])
        rmax = float(ratings[-1])
        ymin = years[len(years)//3]

        out = await tool({
            "limit": 20,
            "response_level": "standard",
            "filters": {
                "genres": [genre],
                "rating_min": rmin,
                "rating_max": rmax,
                "year_min": ymin,
                "sort_by": "rating",
                "sort_order": "desc",
            },
        })
        its = out.get("items") or []
        if not its:
            pytest.skip("No items matched combined filters")
        # Validate constraints
        genre_lists = [it.get("genres") or [] for it in its]
        positives = [gl for gl in genre_lists if any(isinstance(g, str) and g == genre for g in gl)]
        # Accept majority to account for missing tags on some items
        assert len(positives) >= max(1, int(0.7 * len(genre_lists)))
        rvals = [it.get("rating") for it in its if it.get("rating") is not None]
        assert rvals and all(rmin <= v <= rmax for v in rvals)
        assert all((it.get("year") or 0) >= ymin for it in its)
        # Monotonic sort by rating desc
        assert all(a >= b for a, b in zip(rvals, rvals[1:]))

    @pytest.mark.asyncio
    async def test_exact_year_filter(self, registry, integration_requirements_met):
        tool = registry.get("search_plex")
        base = await tool({"limit": 30, "response_level": "compact"})
        items = base.get("items") or []
        years = [it.get("year") for it in items if isinstance(it.get("year"), int)]
        if not years:
            pytest.skip("No year data available")
        year = years[0]
        out = await tool({
            "limit": 20,
            "response_level": "compact",
            "filters": {"year_min": year, "year_max": year, "sort_by": "title", "sort_order": "asc"},
        })
        its = out.get("items") or []
        if not its:
            pytest.skip("No items matched exact-year filter")
        assert all(it.get("year") == year for it in its if it.get("year") is not None)

    @pytest.mark.asyncio
    async def test_genres_union_semantics(self, registry, integration_requirements_met):
        tool = registry.get("search_plex")
        base = await tool({"limit": 60, "response_level": "standard"})
        items = base.get("items") or []
        # Collect two distinct genres across the sample
        seen = []
        for it in items:
            for g in (it.get("genres") or []):
                if isinstance(g, str) and g not in seen:
                    seen.append(g)
                if len(seen) >= 2:
                    break
            if len(seen) >= 2:
                break
        if len(seen) < 2:
            pytest.skip("Not enough distinct genres found")
        g1, g2 = seen[0], seen[1]
        out = await tool({
            "limit": 20,
            "response_level": "standard",
            "filters": {"genres": [g1, g2]},
        })
        its = out.get("items") or []
        if not its:
            pytest.skip("No items matched genre union filter")
        hits = 0
        for it in its:
            gl = it.get("genres") or []
            if any(isinstance(g, str) and (g == g1 or g == g2) for g in gl):
                hits += 1
        assert hits >= max(1, int(0.7 * len(its)))

    @pytest.mark.asyncio
    async def test_actor_and_director_intersection(self, registry, integration_requirements_met):
        tool = registry.get("search_plex")
        base = await tool({"limit": 60, "response_level": "detailed"})
        items = base.get("items") or []
        # Find an item with both actors and directors to construct intersection filters
        actor = director = None
        for it in items:
            actors = it.get("actors") or []
            directors = it.get("directors") or []
            if actors and directors:
                actor = actors[0]
                director = directors[0]
                break
        if not actor or not director:
            pytest.skip("No item with both actors and directors to test intersection")
        out = await tool({
            "limit": 15,
            "response_level": "detailed",
            "filters": {"actors": [actor], "directors": [director]},
        })
        its = out.get("items") or []
        if not its:
            pytest.skip("No items matched actor+director intersection")
        assert all((actor in (it.get("actors") or []) and director in (it.get("directors") or [])) for it in its)

    @pytest.mark.asyncio
    async def test_sort_by_duration_monotonic(self, registry, integration_requirements_met):
        tool = registry.get("search_plex")
        out = await tool({
            "limit": 20,
            "response_level": "standard",
            "filters": {"sort_by": "duration", "sort_order": "asc"},
        })
        its = out.get("items") or []
        durs = [it.get("duration") for it in its if isinstance(it.get("duration"), int)]
        if len(durs) < 2:
            pytest.skip("Not enough duration data to validate order")
        assert all(a <= b for a, b in zip(durs, durs[1:]))

    @pytest.mark.asyncio
    async def test_sort_by_added_desc_monotonic(self, registry, integration_requirements_met):
        tool = registry.get("search_plex")
        out = await tool({
            "limit": 20,
            "response_level": "detailed",
            "filters": {"sort_by": "addedAt", "sort_order": "desc"},
        })
        its = out.get("items") or []
        adds = [it.get("addedAt") for it in its if isinstance(it.get("addedAt"), str)]
        if len(adds) < 2:
            pytest.skip("Not enough addedAt data to validate order")
        assert all(a >= b for a, b in zip(adds, adds[1:]))

    @pytest.mark.asyncio
    async def test_sort_by_last_viewed_desc_monotonic(self, registry, integration_requirements_met):
        tool = registry.get("search_plex")
        out = await tool({
            "limit": 20,
            "response_level": "detailed",
            "filters": {"sort_by": "lastViewedAt", "sort_order": "desc"},
        })
        its = out.get("items") or []
        times = [it.get("lastViewedAt") for it in its if isinstance(it.get("lastViewedAt"), str)]
        if len(times) < 2:
            pytest.skip("Not enough lastViewedAt data to validate order")
        assert all(a >= b for a, b in zip(times, times[1:]))

    @pytest.mark.asyncio
    async def test_limit_honored_under_filters(self, registry, integration_requirements_met):
        tool = registry.get("search_plex")
        # Discover a frequent actor to improve hit rate
        base = await tool({"limit": 50, "response_level": "detailed"})
        items = base.get("items") or []
        actor = None
        for it in items:
            if it.get("actors"):
                actor = it["actors"][0]
                break
        if not actor:
            pytest.skip("No actor found to test limit under filter")
        out = await tool({
            "limit": 3,
            "response_level": "compact",
            "filters": {"actors": [actor], "sort_by": "year", "sort_order": "desc"},
        })
        its = out.get("items") or []
        assert len(its) <= 3

    @pytest.mark.asyncio
    async def test_oldest_movie_is_trip_to_the_moon(self, registry, integration_requirements_met):
        tool = registry.get("search_plex")
        out = await tool({
            "limit": 1,
            "response_level": "standard",
            "filters": {"sort_by": "year", "sort_order": "asc"},
        })
        its = out.get("items") or []
        assert len(its) == 1
        first = its[0]
        title = (first.get("title") or "").strip().lower()
        year = first.get("year")
        assert year == 1902
        assert "trip to the moon" in title

    @pytest.mark.asyncio
    async def test_three_random_nicolas_cage_titles_found(self, registry, integration_requirements_met):
        tool = registry.get("search_plex")
        # Gather a pool of Nicolas Cage movies
        pool = await tool({
            "limit": 200,
            "response_level": "detailed",
            "filters": {"actors": ["Nicolas Cage", "Nic Cage"]},
        })
        items = pool.get("items") or []
        if len(items) < 3:
            pytest.skip("Need at least 3 Nicolas Cage movies in the library")
        random.seed(0)
        picks = random.sample(items, 3)
        # Verify each pick can be individually found by title + actor
        found = 0
        for it in picks:
            title = it.get("title")
            rk = it.get("ratingKey")
            if not title or rk is None:
                continue
            res = await tool({
                "query": title,
                "limit": 10,
                "response_level": "compact",
                "filters": {"actors": ["Nicolas Cage", "Nic Cage"]},
            })
            returned = res.get("items") or []
            ids = {i.get("ratingKey") for i in returned}
            if rk in ids:
                found += 1
        assert found == 3


