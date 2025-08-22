"""
Configuration for integration tests that run against real Plex servers.

This file provides fixtures and configuration for testing against actual
Plex instances rather than mocked ones.
"""

import pytest
import os
from pathlib import Path
from dotenv import load_dotenv


def pytest_addoption(parser):
    """Add command line options for integration tests."""
    parser.addoption(
        "--plex-url",
        action="store",
        default=None,
        help="Plex server URL for integration tests (overrides .env)"
    )
    parser.addoption(
        "--plex-token",
        action="store",
        default=None,
        help="Plex server token for integration tests (overrides .env)"
    )
    parser.addoption(
        "--radarr-url",
        action="store",
        default=None,
        help="Radarr server URL for integration tests (overrides .env)"
    )
    parser.addoption(
        "--radarr-key",
        action="store",
        default=None,
        help="Radarr API key for integration tests (overrides .env)"
    )
    parser.addoption(
        "--sonarr-url",
        action="store",
        default=None,
        help="Sonarr server URL for integration tests (overrides .env)"
    )
    parser.addoption(
        "--sonarr-key",
        action="store",
        default=None,
        help="Sonarr API key for integration tests (overrides .env)"
    )


def pytest_collection_modifyitems(config, items):
    """Mark integration tests to be skipped unless integration marker is specified."""
    # Check if any integration tests are being run
    has_integration_marker = any(
        "integration" in item.keywords for item in items
    )
    
    if has_integration_marker:
        # If integration tests exist, check if they should be run
        # Integration tests will be selected by the -m integration marker
        pass
    else:
        # No integration tests in the collection, nothing to modify
        pass


def pytest_configure(config):
    """Load environment variables from .env file before tests run."""
    # Load .env file from project root
    project_root = Path(__file__).parent.parent
    env_file = project_root / ".env"
    
    if env_file.exists():
        load_dotenv(env_file)
        print(f"✅ Loaded environment from {env_file}")
    else:
        print(f"⚠️  No .env file found at {env_file}")


@pytest.fixture(scope="session")
def integration_config(request):
    """Get integration test configuration from .env file and command line options."""
    config = {
        "plex_url": None,
        "plex_token": None,
        "radarr_url": None,
        "radarr_key": None,
        "sonarr_url": None,
        "sonarr_key": None,
        "run_integration": True
    }

    # Command line options take precedence
    config["plex_url"] = request.config.getoption("--plex-url")
    config["plex_token"] = request.config.getoption("--plex-token")
    config["radarr_url"] = request.config.getoption("--radarr-url")
    config["radarr_key"] = request.config.getoption("--radarr-key")
    config["sonarr_url"] = request.config.getoption("--sonarr-url")
    config["sonarr_key"] = request.config.getoption("--sonarr-key")

    # Fall back to environment variables (loaded from .env)
    if not config["plex_url"]:
        config["plex_url"] = os.getenv("PLEX_BASE_URL")
    if not config["plex_token"]:
        config["plex_token"] = os.getenv("PLEX_TOKEN")
    if not config["radarr_url"]:
        config["radarr_url"] = os.getenv("RADARR_BASE_URL")
    if not config["radarr_key"]:
        config["radarr_key"] = os.getenv("RADARR_API_KEY")
    if not config["sonarr_url"]:
        config["sonarr_url"] = os.getenv("SONARR_BASE_URL")
    if not config["sonarr_key"]:
        config["sonarr_key"] = os.getenv("SONARR_API_KEY")

    return config


@pytest.fixture(scope="session")
def integration_requirements_met(integration_config):
    """Check if all requirements for integration tests are met."""
    if not integration_config["run_integration"]:
        pytest.skip("Integration tests not requested")
    
    if not integration_config["plex_url"]:
        pytest.skip("Plex URL not provided (check .env file or use --plex-url)")
    
    if not integration_config["plex_token"]:
        pytest.skip("Plex token not provided (check .env file or use --plex-token)")
    
    return True


@pytest.fixture(scope="session")
def test_environment():
    """Get information about the test environment."""
    return {
        "python_version": os.sys.version,
        "platform": os.sys.platform,
        "project_root": str(Path(__file__).parent.parent),
        "test_type": "integration",  # This fixture is only used in integration tests
        "env_file_loaded": bool(os.getenv("PLEX_BASE_URL") or os.getenv("PLEX_TOKEN"))
    }


@pytest.fixture(scope="session")
def radarr_config(integration_config):
    """Radarr connection config, skips if not provided."""
    if not integration_config.get("radarr_url") or not integration_config.get("radarr_key"):
        pytest.skip("Radarr URL or API key not provided (set RADARR_BASE_URL/RADARR_API_KEY or pass CLI options)")
    return {
        "url": integration_config["radarr_url"],
        "api_key": integration_config["radarr_key"],
    }


@pytest.fixture(scope="session")
def sonarr_config(integration_config):
    """Sonarr connection config, skips if not provided."""
    if not integration_config.get("sonarr_url") or not integration_config.get("sonarr_key"):
        pytest.skip("Sonarr URL or API key not provided (set SONARR_BASE_URL/SONARR_API_KEY or pass CLI options)")
    return {
        "url": integration_config["sonarr_url"],
        "api_key": integration_config["sonarr_key"],
    }
