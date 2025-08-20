import pytest
import sys
from pathlib import Path

# Add the project root to the Python path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Common test fixtures and configuration
@pytest.fixture(scope="session")
def test_project_root():
    """Provide a test project root path."""
    return Path(__file__).parent.parent

@pytest.fixture(autouse=True)
def mock_environment(monkeypatch):
    """Mock environment variables for testing."""
    # Mock environment variables that might be needed
    monkeypatch.setenv("PLEX_TOKEN", "test_token_123")
    monkeypatch.setenv("PLEX_BASE_URL", "http://localhost:32400")
    monkeypatch.setenv("TMDB_API_KEY", "test_tmdb_key")
    monkeypatch.setenv("RADARR_BASE_URL", "http://localhost:7878")
    monkeypatch.setenv("RADARR_API_KEY", "test_radarr_key")
    monkeypatch.setenv("SONARR_BASE_URL", "http://localhost:8989")
    monkeypatch.setenv("SONARR_API_KEY", "test_sonarr_key")

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
