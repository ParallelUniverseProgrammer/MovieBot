import os
from urllib.parse import urlencode
import xml.etree.ElementTree as ET

import pytest
import httpx

from integrations.plex_client import PlexClient


@pytest.mark.integration
class TestPlexHdr4KLive:
    @pytest.fixture(scope="class")
    def plex_creds(self, integration_requirements_met):
        base_url = os.getenv("PLEX_BASE_URL")
        token = os.getenv("PLEX_TOKEN")
        if not base_url or not token:
            pytest.skip("PLEX_BASE_URL and PLEX_TOKEN are required in .env for live test")
        return {"base_url": base_url.rstrip("/"), "token": token}

    @pytest.fixture(scope="class")
    def movie_section_id(self, plex_creds):
        client = PlexClient(plex_creds["base_url"], plex_creds["token"])
        sections = client.get_library_sections()
        # Prefer a section explicitly typed as movies
        for title, info in sections.items():
            if info.get("type") == "movie":
                return str(info.get("section_id"))
        pytest.skip("No movie library section found on this Plex server")

    def _fetch_videos(self, base_url: str, token: str, section_id: str, params: dict) -> int:
        # Limit container size to keep responses small and fast
        base_params = {
            "X-Plex-Token": token,
            "X-Plex-Container-Start": "0",
            "X-Plex-Container-Size": "30",
            "type": "1",  # movies
        }
        qp = base_params.copy()
        qp.update(params)
        url = f"{base_url}/library/sections/{section_id}/all?{urlencode(qp)}"
        r = httpx.get(url, headers={"Accept": "application/xml"}, timeout=5.0)
        r.raise_for_status()
        # Parse Plex XML and count <Video> items
        root = ET.fromstring(r.text)
        return len(root.findall(".//Video"))

    def test_live_movies_4k_or_hdr(self, plex_creds, movie_section_id):
        attempts = []
        # Try combined OR query first, then fallbacks
        query_variants = [
            {"or": "1", "resolution": "4k", "hdr": "1"},
            {"or": "1", "videoResolution": "4k", "hdr": "1"},
            {"or": "1", "resolution": "4k", "hdr": "true"},
            {"or": "1", "videoResolution": "4k", "hdr": "true"},
            # Fallbacks (union semantics handled by running separately)
            {"resolution": "4k"},
            {"videoResolution": "4k"},
            {"hdr": "1"},
            {"hdr": "true"},
        ]

        total_found = 0
        for i, params in enumerate(query_variants, start=1):
            try:
                count = self._fetch_videos(plex_creds["base_url"], plex_creds["token"], movie_section_id, params)
                attempts.append((params, count, None))
                total_found = max(total_found, count)
                # Early exit as soon as we find results
                if count > 0:
                    break
            except Exception as e:
                attempts.append((params, None, str(e)))
                # Fail fast on obvious auth or connectivity errors
                if "401" in str(e) or "403" in str(e):
                    pytest.fail(f"Authentication failed contacting Plex: {e}")

        # Diagnose if nothing was found to help users adjust filters
        if total_found == 0:
            diag = "; ".join(
                [
                    f"params={p} -> count={c} err={err}"  # type: ignore[str-format]
                    for (p, c, err) in attempts
                ]
            )
            pytest.fail(
                "No HDR or 4K movies found via live Plex API. "
                "Checked multiple compliant parameter variants. "
                f"Attempts: {diag}"
            )

        # If we got here, we have at least one result
        assert total_found > 0


