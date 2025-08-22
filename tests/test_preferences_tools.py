import json
from pathlib import Path
import pytest

from bot.tools.registry import build_openai_tools_and_registry


class _DummyMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _DummyChoice:
    def __init__(self, content: str) -> None:
        self.message = _DummyMessage(content)


class _DummyLLMResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_DummyChoice(content)]


class _DummyLLMClient:
    async def achat(self, *args, **kwargs):
        # Always return a short one-sentence answer
        return _DummyLLMResponse("Yes, jump scares are allowed based on the preferences.")


@pytest.fixture()
def tmp_project_root(tmp_path: Path) -> Path:
    root = tmp_path
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    # Minimal preferences snapshot for tests
    sample = {
        "version": 1,
        "likes": {
            "genres": ["thriller", "sci-fi"],
            "people": ["Pedro Pascal"],
        },
        "dislikes": {
            "genres": ["found footage"],
        },
        "constraints": {
            "eraMinYear": 2019,
            "languageWhitelist": ["en"],
            "runtimeSweetSpotMins": [100, 130],
            "contentWarnings": ["cancer"],
            "visualsDisallow": ["found footage"],
            "allowJumpScares": True,
        },
        "profile": {
            "tone": {"nonHorror": "witty", "horror": "dead-serious"},
            "pacing": "propulsive",
            "plausibilityScore10": 8,
        },
        "anchors": {
            "loved": ["The Matrix"],
            "trustedFaces": ["Pedro Pascal"],
        },
        "heuristics": {"themes": ["tech", "class"], "zeroSpoilers": True},
        "antiPreferences": ["pure camp"],
        "notes": "Sleek, twisty, recent English-language genre",
    }
    with open(data_dir / "household_preferences.json", "w", encoding="utf-8") as f:
        json.dump(sample, f, indent=2)
    return root


@pytest.mark.asyncio
async def test_read_preferences_compact_and_targeted(tmp_project_root: Path):
    _, registry = build_openai_tools_and_registry(tmp_project_root, _DummyLLMClient())

    # Compact summary
    out = await registry.get("read_household_preferences")({"compact": True})
    assert "Constraints:" in out["compact"]
    assert "Likes:" in out["compact"]

    # Path navigation
    out = await registry.get("read_household_preferences")({"path": "likes.genres"})
    assert out["path"] == "likes.genres"
    assert out["value"] == ["thriller", "sci-fi"]

    # Keys projection
    out = await registry.get("read_household_preferences")({"keys": ["likes", "constraints"]})
    assert "likes" in out and "constraints" in out


@pytest.mark.asyncio
async def test_search_preferences_text(tmp_project_root: Path):
    _, registry = build_openai_tools_and_registry(tmp_project_root, _DummyLLMClient())
    out = await registry.get("search_household_preferences")({"query": "thriller", "limit": 5})
    paths = [m["path"] for m in out["matches"]]
    assert any("likes.genres" in p for p in paths)


@pytest.mark.asyncio
async def test_update_preferences_deep_merge_and_path_ops(tmp_project_root: Path):
    _, registry = build_openai_tools_and_registry(tmp_project_root, _DummyLLMClient())

    # Deep merge patch
    rv = await registry.get("update_household_preferences")({
        "patch": {"likes": {"languages": ["en", "es"]}}
    })
    assert rv["ok"] is True

    out = await registry.get("read_household_preferences")({"path": "likes.languages"})
    assert out["value"] == ["en", "es"]

    # Path set with dotted key
    rv = await registry.get("update_household_preferences")({
        "path": "likes.people", "value": ["Pedro Pascal", "Margot Robbie"]
    })
    assert rv["ok"] is True
    out = await registry.get("read_household_preferences")({"path": "likes.people"})
    assert out["value"] == ["Pedro Pascal", "Margot Robbie"]

    # Append to list at path
    rv = await registry.get("update_household_preferences")({
        "path": "likes.people", "append": "Keanu Reeves"
    })
    assert rv["ok"] is True
    out = await registry.get("read_household_preferences")({"path": "likes.people"})
    assert "Keanu Reeves" in out["value"]

    # Remove from list at path
    rv = await registry.get("update_household_preferences")({
        "path": "likes.people", "remove_value": "Pedro Pascal"
    })
    assert rv["ok"] is True
    out = await registry.get("read_household_preferences")({"path": "likes.people"})
    assert "Pedro Pascal" not in out["value"]


@pytest.mark.asyncio
async def test_update_preferences_json_patch_ops(tmp_project_root: Path):
    _, registry = build_openai_tools_and_registry(tmp_project_root, _DummyLLMClient())

    rv = await registry.get("update_household_preferences")({
        "ops": [
            {"op": "add", "path": "/heuristics/coupleFirst", "value": True},
            {"op": "remove", "path": "/antiPreferences"}
        ]
    })
    assert rv["ok"] is True

    out = await registry.get("read_household_preferences")({"keys": ["heuristics", "antiPreferences"]})
    assert out["heuristics"].get("coupleFirst") is True
    assert out.get("antiPreferences") is None


@pytest.mark.asyncio
async def test_query_household_preferences_worker(tmp_project_root: Path):
    _, registry = build_openai_tools_and_registry(tmp_project_root, _DummyLLMClient())
    out = await registry.get("query_household_preferences")({"query": "Are jump scares allowed?"})
    assert "answer" in out
    assert out["answer"].lower().startswith("yes")


