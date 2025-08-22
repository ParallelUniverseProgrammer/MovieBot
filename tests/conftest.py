import pytest
import sys
from pathlib import Path
import os
from dotenv import load_dotenv

# Add the project root to the Python path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment from .env for all tests (does not override existing env)
load_dotenv(project_root / ".env")

# Common test fixtures and configuration
@pytest.fixture(scope="session")
def test_project_root():
    """Provide a test project root path."""
    return Path(__file__).parent.parent

@pytest.fixture(autouse=True)
def mock_environment(monkeypatch, request):
    """Mock environment variables for unit tests only.

    Skips mocking when running tests marked with `integration` so that real
    environment variables from .env are used for live server tests.
    """
    if request.node.get_closest_marker("integration") is not None:
        # Do not override env for integration tests
        return

    # Mock environment variables that might be needed for unit tests
    monkeypatch.setenv("PLEX_TOKEN", "test_token_123")
    monkeypatch.setenv("PLEX_BASE_URL", "http://localhost:32400")
    monkeypatch.setenv("TMDB_API_KEY", "test_tmdb_key")
    monkeypatch.setenv("RADARR_BASE_URL", "http://localhost:7878")
    monkeypatch.setenv("RADARR_API_KEY", "test_radarr_key")
    monkeypatch.setenv("SONARR_BASE_URL", "http://localhost:8989")
    monkeypatch.setenv("SONARR_API_KEY", "test_sonarr_key")


# ---------------------- Integration CLI options ----------------------
def pytest_addoption(parser):
    parser.addoption("--plex-url", action="store", default=None, help="Plex server URL for integration tests (overrides .env)")
    parser.addoption("--plex-token", action="store", default=None, help="Plex server token for integration tests (overrides .env)")
    parser.addoption("--radarr-url", action="store", default=None, help="Radarr server URL for integration tests (overrides .env)")
    parser.addoption("--radarr-key", action="store", default=None, help="Radarr API key for integration tests (overrides .env)")
    parser.addoption("--sonarr-url", action="store", default=None, help="Sonarr server URL for integration tests (overrides .env)")
    parser.addoption("--sonarr-key", action="store", default=None, help="Sonarr API key for integration tests (overrides .env)")


@pytest.fixture(scope="session")
def integration_config(request):
    # Load .env
    project_root = Path(__file__).parent.parent
    env_file = project_root / ".env"
    if env_file.exists():
        load_dotenv(env_file)

    cfg = {
        "plex_url": request.config.getoption("--plex-url") or os.getenv("PLEX_BASE_URL"),
        "plex_token": request.config.getoption("--plex-token") or os.getenv("PLEX_TOKEN"),
        "radarr_url": request.config.getoption("--radarr-url") or os.getenv("RADARR_BASE_URL"),
        "radarr_key": request.config.getoption("--radarr-key") or os.getenv("RADARR_API_KEY"),
        "sonarr_url": request.config.getoption("--sonarr-url") or os.getenv("SONARR_BASE_URL"),
        "sonarr_key": request.config.getoption("--sonarr-key") or os.getenv("SONARR_API_KEY"),
    }
    return cfg


@pytest.fixture(scope="session")
def integration_requirements_met(integration_config):
    if not integration_config.get("plex_url") or not integration_config.get("plex_token"):
        pytest.skip("Plex URL/token not provided (set .env or pass CLI options)")
    return True


@pytest.fixture(scope="session")
def radarr_config(integration_config):
    if not integration_config.get("radarr_url") or not integration_config.get("radarr_key"):
        pytest.skip("Radarr URL or API key not provided (set .env or pass CLI options)")
    return {"url": integration_config["radarr_url"], "api_key": integration_config["radarr_key"]}


@pytest.fixture(scope="session")
def sonarr_config(integration_config):
    if not integration_config.get("sonarr_url") or not integration_config.get("sonarr_key"):
        pytest.skip("Sonarr URL or API key not provided (set .env or pass CLI options)")
    return {"url": integration_config["sonarr_url"], "api_key": integration_config["sonarr_key"]}

@pytest.fixture
def mock_paths(monkeypatch, tmp_path):
    """Mock file system paths for testing."""
    # Create temporary test directories
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    
    # Mock the data directory path
    monkeypatch.setattr("pathlib.Path", lambda x: tmp_path / x if x == "data" else Path(x))
    
    return {
        "data_dir": data_dir,
        "tmp_path": tmp_path
    }
